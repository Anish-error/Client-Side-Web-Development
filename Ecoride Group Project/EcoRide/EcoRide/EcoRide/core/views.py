import hashlib
import hmac
import json
import logging

import razorpay
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from .models import Bicycle, Payment, Rental, Station

logger = logging.getLogger(__name__)
RENTAL_PRICE_PAISE = 2000
RAZORPAY_API_ERRORS = (
    razorpay.errors.BadRequestError,
    razorpay.errors.GatewayError,
    razorpay.errors.ServerError,
    requests.exceptions.RequestException,
)


def _razorpay_client():
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def home(request):
    stations = Station.objects.filter(is_active=True).annotate(
        available_count=Count(
            "bicycles", filter=Q(bicycles__status=Bicycle.Status.AVAILABLE)
        )
    )[:3]
    return render(
        request,
        "core/home.html",
        {
            "stations": stations,
            "station_count": Station.objects.filter(is_active=True).count(),
            "bike_count": Bicycle.objects.count(),
            "available_count": Bicycle.objects.filter(
                status=Bicycle.Status.AVAILABLE,
                station__is_active=True,
            ).count(),
        },
    )


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your EcoRide account is ready.")
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    rentals = request.user.rentals.select_related(
        "bicycle", "start_station", "end_station"
    )[:10]
    open_rental = request.user.rentals.filter(
        status__in=[Rental.Status.PENDING_PAYMENT, Rental.Status.ACTIVE]
    ).first()
    return render(
        request,
        "core/dashboard.html",
        {"rentals": rentals, "open_rental": open_rental},
    )


def station_list(request):
    stations = Station.objects.filter(is_active=True).annotate(
        available_count=Count(
            "bicycles",
            filter=Q(bicycles__status=Bicycle.Status.AVAILABLE),
            distinct=True,
        ),
        docked_count=Count(
            "bicycles",
            filter=~Q(bicycles__status=Bicycle.Status.RENTED),
            distinct=True,
        ),
    )
    station_map_data = [
        {
            "id": station.pk,
            "name": station.name,
            "latitude": float(station.latitude),
            "longitude": float(station.longitude),
            "available_count": station.available_count,
            "address": station.address,
            "url": reverse("station_detail", args=[station.pk]),
        }
        for station in stations
    ]
    return render(
        request,
        "core/stations.html",
        {"stations": stations, "station_map_data": station_map_data},
    )

def station_map_data(request):
    stations = Station.objects.filter(is_active=True).annotate(
        available_count=Count(
            "bicycles",
            filter=Q(bicycles__status=Bicycle.Status.AVAILABLE),
            distinct=True,
        )
    )

    data = [
        {
            "id": station.pk,
            "name": station.name,
            "latitude": float(station.latitude),
            "longitude": float(station.longitude),
            "available_count": station.available_count,
            "address": station.address,
            "url": reverse("station_detail", args=[station.pk]),
        }
        for station in stations
    ]

    return JsonResponse(data, safe=False)


def station_detail(request, station_id):
    station = get_object_or_404(Station, pk=station_id, is_active=True)
    bicycles = station.bicycles.exclude(status=Bicycle.Status.MAINTENANCE)
    return render(
        request,
        "core/station_detail.html",
        {
            "station": station,
            "bicycles": bicycles,
            "docked_count": station.bicycles.exclude(
                status=Bicycle.Status.RENTED
            ).count(),
        },
    )


@login_required
def start_ride(request, station_id):
    station = get_object_or_404(
        Station,
        pk=station_id,
        is_active=True,
    )

    bicycles = station.bicycles.filter(
        status=Bicycle.Status.AVAILABLE
    ).order_by("code")

    return render(
        request,
        "core/start_ride.html",
        {
            "station": station,
            "bicycles": bicycles,
        },
    )


@login_required
@require_POST
def verify_bicycle_qr(request, station_id):
    code = request.POST.get("code", "").strip()

    if not code:
        return JsonResponse(
            {"ok": False, "message": "No bicycle QR code was provided."},
            status=400,
        )

    try:
        bicycle = Bicycle.objects.select_related("station").get(
            code=code,
            station_id=station_id,
        )
    except Bicycle.DoesNotExist:
        return JsonResponse(
            {
                "ok": False,
                "message": "This QR code does not belong to a bicycle at this station.",
            },
            status=404,
        )

    if not bicycle.station.is_active:
        return JsonResponse(
            {"ok": False, "message": "This station is not currently active."},
            status=400,
        )

    if bicycle.status != Bicycle.Status.AVAILABLE:
        return JsonResponse(
            {
                "ok": False,
                "message": "This bicycle is not available. Please scan another bicycle.",
            },
            status=409,
        )

    return JsonResponse(
        {
            "ok": True,
            "bicycle": {
                "id": bicycle.id,
                "code": bicycle.code,
                "is_electric": bicycle.is_electric,
                "battery_level": bicycle.battery_level,
                "station": bicycle.station.name,
            },
            "message": "Bicycle verified. Review the details before starting your ride.",
        }
    )

@login_required
@require_POST
def start_rental(request, bicycle_id):
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        if settings.DEBUG:
            return _start_mock_rental(request, bicycle_id)

        messages.error(
            request,
            "Online checkout is not configured yet.",
        )
        return redirect("stations")

    try:
        with transaction.atomic():
            bicycle = get_object_or_404(
                Bicycle.objects.select_for_update().select_related("station"),
                pk=bicycle_id,
                status=Bicycle.Status.AVAILABLE,
                station__is_active=True,
            )
            rental = Rental.objects.create(
                user=request.user,
              
                bicycle=bicycle,
                start_station=bicycle.station,
                amount_minor_units=RENTAL_PRICE_PAISE,
                currency="INR",
            )
            bicycle.status = Bicycle.Status.RESERVED
            bicycle.save(update_fields=["status"])
            payment = Payment.objects.create(
                rental=rental,
                amount_minor_units=RENTAL_PRICE_PAISE,
                currency="INR",
            )
    except IntegrityError:
        messages.error(
            request,
            "You already have an active rental, or that bicycle was just reserved.",
        )
        return redirect("dashboard")

    try:
        order = _razorpay_client().order.create(
            data={
                "amount": payment.amount_minor_units,
                "currency": payment.currency,
                "receipt": f"ecoride-rental-{rental.pk}",
                "notes": {"rental_id": str(rental.pk)},
            }
        )
    except RAZORPAY_API_ERRORS:
        _release_unpaid_rental(rental.pk)
        logger.exception("Razorpay could not create rental order %s", rental.pk)
        messages.error(request, "Checkout could not be started. Please try again.")
        return redirect("stations")

    order_id = order.get("id")
    if not order_id:
        _release_unpaid_rental(rental.pk)
        logger.error("Razorpay returned no order ID for rental %s", rental.pk)
        messages.error(request, "Checkout could not be started. Please try again.")
        return redirect("stations")

    payment.gateway_order_id = order_id
    payment.save(update_fields=["gateway_order_id"])
    return _render_razorpay_checkout(request, rental, payment, order_id)


def _start_mock_rental(request, bicycle_id):
    try:
        with transaction.atomic():
            bicycle = get_object_or_404(
                Bicycle.objects.select_for_update().select_related("station"),
                pk=bicycle_id,
                status=Bicycle.Status.AVAILABLE,
                station__is_active=True,
            )

            rental = Rental.objects.create(
                user=request.user,
                bicycle=bicycle,
                start_station=bicycle.station,
                amount_minor_units=RENTAL_PRICE_PAISE,
                currency="INR",
            )

            bicycle.status = Bicycle.Status.RESERVED
            bicycle.save(update_fields=["status"])

            payment = Payment.objects.create(
                rental=rental,
                amount_minor_units=RENTAL_PRICE_PAISE,
                currency="INR",
            )

    except IntegrityError:
        messages.error(
            request,
            "You already have an active rental, or that bicycle was just reserved.",
        )
        return redirect("dashboard")

    return redirect("mock_checkout", rental_id=rental.pk)


def _render_razorpay_checkout(request, rental, payment, order_id):
    return render(
        request,
        "core/checkout.html",
        {
            "rental": rental,
            "payment": payment,
            "razorpay_order_id": order_id,
            "checkout_options": {
                "key": settings.RAZORPAY_KEY_ID,
                "amount": payment.amount_minor_units,
                "currency": payment.currency,
                "name": "EcoRide Pune",
                "description": f"Bicycle rental · {rental.bicycle.code}",
                "image": (
                    f"{settings.APP_BASE_URL}/static/core/integrated/"
                    "cycle-removebg-preview.png"
                ),
                "order_id": order_id,
                "prefill": {
                    "name": request.user.get_full_name(),
                    "email": request.user.email,
                },
                "theme": {"color": "#0bb985"},
            },
        },
    )


@login_required
def retry_checkout(request, rental_id):
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        messages.error(request, "Razorpay checkout is not configured.")
        return redirect("rental_detail", rental_id=rental_id)
    payment = get_object_or_404(
        Payment.objects.select_related("rental", "rental__bicycle", "rental__start_station"),
        rental_id=rental_id,
        rental__user=request.user,
        rental__status=Rental.Status.PENDING_PAYMENT,
        status=Payment.Status.PENDING,
    )
    if not payment.gateway_order_id:
        messages.error(request, "This checkout order is unavailable. Please contact support.")
        return redirect("rental_detail", rental_id=rental_id)
    return _render_razorpay_checkout(
        request, payment.rental, payment, payment.gateway_order_id
    )


@login_required
def rental_detail(request, rental_id):
    rental = get_object_or_404(
        Rental.objects.select_related("bicycle", "start_station", "end_station"),
        pk=rental_id,
        user=request.user,
    )
    return render(
        request,
        "core/rental_detail.html",
        {
            "rental": rental,
            "active_stations": Station.objects.filter(is_active=True),
        },
    )


def _release_unpaid_rental(rental_id):
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(
            rental_id=rental_id
        ).first()
        rental = Rental.objects.select_for_update().filter(
            pk=rental_id,
            status=Rental.Status.PENDING_PAYMENT,
        ).first()
        if not rental:
            return
        rental.status = Rental.Status.CANCELED
        rental.save(update_fields=["status"])
        if payment and payment.status == Payment.Status.PENDING:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
        Bicycle.objects.filter(
            pk=rental.bicycle_id, status=Bicycle.Status.RESERVED
        ).update(status=Bicycle.Status.AVAILABLE)


def _confirm_razorpay_payment(payment, gateway_payment_id, gateway_order_id):
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == Payment.Status.PAID:
            return payment.rental
        if payment.gateway_order_id != gateway_order_id:
            raise ValueError("Payment does not match the rental order.")

        rental = Rental.objects.select_for_update().get(pk=payment.rental_id)
        if rental.status != Rental.Status.PENDING_PAYMENT:
            raise ValueError("Rental is no longer waiting for payment.")
        bicycle = Bicycle.objects.select_for_update().get(pk=rental.bicycle_id)
        if bicycle.status != Bicycle.Status.RESERVED:
            raise ValueError("The bicycle is no longer reserved for this rental.")

        payment.gateway_payment_id = gateway_payment_id
        payment.status = Payment.Status.PAID
        payment.paid_at = timezone.now()
        payment.save(
            update_fields=["gateway_payment_id", "status", "paid_at"]
        )
        rental.status = Rental.Status.ACTIVE
        rental.started_at = timezone.now()
        rental.save(update_fields=["status", "started_at"])
        bicycle.status = Bicycle.Status.RENTED
        bicycle.save(update_fields=["status"])
        return rental

@login_required
def mock_checkout(request, rental_id):
    if not settings.DEBUG:
        from django.http import Http404
        raise Http404("Page not found")

    rental = get_object_or_404(
        Rental,
        pk=rental_id,
        user=request.user,
    )
    payment = get_object_or_404(Payment, rental=rental)

    if request.method == "POST":
        if rental.status != Rental.Status.PENDING_PAYMENT:
            return redirect("rental_detail", rental_id=rental.pk)

        action = request.POST.get("action")

        if action == "cancel":
            return redirect("cancel_checkout", rental_id=rental.pk)

        if action == "fail":
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            messages.warning(
                request,
                "Mock payment failed. You can retry checkout.",
            )
            return redirect("mock_checkout", rental_id=rental.pk)

        if action == "success":
            # Reuse the existing, transaction-safe rental activation logic.
            payment.gateway_order_id = f"mock_order_{payment.pk}"
            payment.save(update_fields=["gateway_order_id"])

            try:
                rental = _confirm_mock_payment(payment)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("rental_detail", rental_id=rental.pk)

            messages.success(
                request,
                "Mock payment successful! Your ride is ready.",
            )
            return redirect("rental_detail", rental_id=rental.pk)

    return render(
        request,
        "core/mock_checkout.html",
        {
            "rental": rental,
            "payment": payment,
        },
    )

def _confirm_mock_payment(payment):
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        rental = Rental.objects.select_for_update().get(pk=payment.rental_id)

        if rental.status != Rental.Status.PENDING_PAYMENT:
            raise ValueError("This rental is no longer awaiting payment.")

        if payment.status not in (
            Payment.Status.PENDING,
            Payment.Status.FAILED,
        ):
            raise ValueError("This payment cannot be completed.")

        bicycle = Bicycle.objects.select_for_update().get(
            pk=rental.bicycle_id
        )

        if bicycle.status != Bicycle.Status.RESERVED:
            raise ValueError("This bicycle is no longer reserved.")

        payment.status = Payment.Status.PAID
        payment.paid_at = timezone.now()
        payment.gateway_payment_id = f"mock_payment_{payment.pk}"
        payment.save(
            update_fields=[
                "status",
                "paid_at",
                "gateway_payment_id",
            ]
        )

        rental.status = Rental.Status.ACTIVE
        rental.started_at = timezone.now()
        rental.save(update_fields=["status", "started_at"])

        bicycle.status = Bicycle.Status.RENTED
        bicycle.save(update_fields=["status"])

        return rental


@login_required
@require_POST
def cancel_checkout(request, rental_id):
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(
            rental_id=rental_id,
            rental__user=request.user,
        ).first()
        rental = get_object_or_404(
            Rental.objects.select_for_update(),
            pk=rental_id,
            user=request.user,
            status=Rental.Status.PENDING_PAYMENT,
        )
        if payment and payment.status == Payment.Status.PENDING:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
        rental.status = Rental.Status.CANCELED
        rental.save(update_fields=["status"])
        Bicycle.objects.filter(
            pk=rental.bicycle_id,
            status=Bicycle.Status.RESERVED,
        ).update(status=Bicycle.Status.AVAILABLE)
    messages.info(request, "Reservation canceled. The bicycle is available again.")
    return redirect("station_detail", station_id=rental.start_station_id)


@login_required
@require_POST
def verify_payment(request):
    order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")
    payment = get_object_or_404(
        Payment.objects.select_related("rental"),
        gateway_order_id=order_id,
        rental__user=request.user,
    )
    try:
        _razorpay_client().utility.verify_payment_signature(
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
        gateway_payment = _razorpay_client().payment.fetch(payment_id)
    except razorpay.errors.SignatureVerificationError:
        return HttpResponseBadRequest("Invalid payment signature.")
    except RAZORPAY_API_ERRORS:
        logger.exception("Could not verify Razorpay payment for rental %s", payment.rental_id)
        messages.error(request, "We could not confirm payment yet. Please refresh shortly.")
        return redirect("rental_detail", rental_id=payment.rental_id)

    if (
        gateway_payment.get("order_id") != order_id
        or gateway_payment.get("amount") != payment.amount_minor_units
        or gateway_payment.get("currency") != payment.currency
        or gateway_payment.get("status") != "captured"
    ):
        logger.warning("Razorpay payment did not match expected rental %s", payment.rental_id)
        messages.error(
            request,
            "Payment is not captured yet. Please retry checkout or contact support.",
        )
        return redirect("rental_detail", rental_id=payment.rental_id)

    rental = _confirm_razorpay_payment(payment, payment_id, order_id)
    messages.success(request, "Payment confirmed. Your ride is ready!")
    return redirect("rental_detail", rental_id=rental.pk)


@login_required
@require_POST
def return_bicycle(request, rental_id):
    with transaction.atomic():
        rental = get_object_or_404(
            Rental.objects.select_for_update().select_related("bicycle"),
            pk=rental_id,
            user=request.user,
            status=Rental.Status.ACTIVE,
        )
        station = get_object_or_404(
            Station.objects.select_for_update(),
            pk=request.POST.get("station_id"),
            is_active=True,
        )
        docked_bikes = station.bicycles.exclude(status=Bicycle.Status.RENTED).count()
        if docked_bikes >= station.capacity:
            messages.error(request, "That station is full. Please choose another station.")
            return redirect("rental_detail", rental_id=rental.pk)

        bicycle = Bicycle.objects.select_for_update().get(pk=rental.bicycle_id)
        bicycle.station = station
        bicycle.status = Bicycle.Status.AVAILABLE
        bicycle.save(update_fields=["station", "status"])
        rental.end_station = station
        rental.ended_at = timezone.now()
        rental.status = Rental.Status.COMPLETED
        rental.save(update_fields=["end_station", "ended_at", "status"])

    messages.success(request, f"{bicycle.code} returned to {station.name}.")
    return redirect("rental_detail", rental_id=rental.pk)


@login_required
def staff_dashboard(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not authorized to access this page.")

    User = get_user_model()

    context = {
        "users": User.objects.all().order_by("-date_joined"),
        "bicycles": Bicycle.objects.select_related("station").all(),
        "stations": Station.objects.all(),
        "rentals": Rental.objects.select_related(
            "user", "bicycle", "start_station", "end_station"
        ).all(),
        "payments": Payment.objects.select_related("rental", "rental__user").all(),
        "total_users": User.objects.count(),
        "total_bicycles": Bicycle.objects.count(),
        "total_stations": Station.objects.count(),
        "active_rentals": Rental.objects.filter(
            status=Rental.Status.ACTIVE
        ).count(),
    }

    return render(request, "core/staff_dashboard.html", context)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        logger.error("Razorpay webhook received but RAZORPAY_WEBHOOK_SECRET is not configured")
        return HttpResponse(status=503)
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected_signature = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return HttpResponseBadRequest("Invalid Razorpay webhook signature.")

    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid Razorpay webhook payload.")

    if event.get("event") == "payment.captured":
        gateway_payment = (
            event.get("payload", {}).get("payment", {}).get("entity", {})
        )
        order_id = gateway_payment.get("order_id")
        if not order_id:
            return HttpResponseBadRequest("Payment event is missing its order.")
        payment = Payment.objects.filter(gateway_order_id=order_id).first()
        if not payment:
            logger.warning("Ignoring unmatched Razorpay order %s", order_id)
            return HttpResponse(status=200)
        if (
            gateway_payment.get("status") != "captured"
            or gateway_payment.get("amount") != payment.amount_minor_units
            or gateway_payment.get("currency") != payment.currency
        ):
            return HttpResponseBadRequest("Razorpay payment does not match the order.")
        try:
            _confirm_razorpay_payment(
                payment, gateway_payment.get("id", ""), order_id
            )
        except ValueError:
            logger.exception("Could not activate rental for Razorpay order %s", order_id)
            return HttpResponse(status=409)
    return HttpResponse(status=200)

from .forms import StationForm, BicycleForm


@login_required
def manage_stations(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not authorized.")

    if request.method == "POST":
        form = StationForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                station = form.save()

                bicycles = [
                    Bicycle(
                        station=station,
                        code=f"ER-{station.pk}-{number:03d}",
                        status=Bicycle.Status.AVAILABLE,
                    )
                    for number in range(1, station.capacity + 1)
                ]

                Bicycle.objects.bulk_create(bicycles)

            messages.success(
                request,
                f"Station added successfully with {station.capacity} bicycles!"
            )
            return redirect("manage_stations")
    else:
        form = StationForm()

    stations = Station.objects.all()

    return render(request, "core/manage_stations.html", {
        "form": form,
        "stations": stations,
    })

@login_required
def deactivate_station(request, station_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not authorized.")

    if request.method == "POST":
        station = get_object_or_404(Station, id=station_id)
        station.is_active = False
        station.save(update_fields=["is_active"])

        messages.success(request, "Station deactivated successfully!")

    return redirect("manage_stations")

@login_required
def reactivate_station(request, station_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not authorized.")

    if request.method == "POST":
        station = get_object_or_404(Station, id=station_id)
        station.is_active = True
        station.save(update_fields=["is_active"])

        messages.success(request, "Station reactivated successfully!")

    return redirect("manage_stations")

@login_required
def edit_bicycle(request, bicycle_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not authorized.")

    bicycle = get_object_or_404(Bicycle, id=bicycle_id)

    if request.method == "POST":
        form = BicycleForm(request.POST, instance=bicycle)

        if form.is_valid():
            form.save()
            messages.success(request, "Bicycle updated successfully!")
            return redirect("manage_bicycles")
    else:
        form = BicycleForm(instance=bicycle)

    return render(request, "core/edit_bicycle.html", {
        "form": form,
        "bicycle": bicycle,
    })

@login_required
def deactivate_bicycle(request, bicycle_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not authorized.")

    if request.method == "POST":
        bicycle = get_object_or_404(Bicycle, id=bicycle_id)

        if bicycle.status in [
            Bicycle.Status.AVAILABLE,
            Bicycle.Status.MAINTENANCE,
        ]:
            bicycle.status = Bicycle.Status.MAINTENANCE
            bicycle.save(update_fields=["status"])

            messages.success(
                request,
                "Bicycle moved to maintenance successfully!"
            )

    return redirect("manage_bicycles")

@login_required
def reactivate_bicycle(request, bicycle_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not authorized.")

    if request.method == "POST":
        bicycle = get_object_or_404(Bicycle, id=bicycle_id)

        if bicycle.status == Bicycle.Status.MAINTENANCE:
            bicycle.status = Bicycle.Status.AVAILABLE
            bicycle.save(update_fields=["status"])

            messages.success(
                request,
                "Bicycle reactivated successfully!"
            )

    return redirect("manage_bicycles")

@login_required
def manage_bicycles(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not authorized.")

    if request.method == "POST":
        form = BicycleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Bicycle added successfully!")
            return redirect("manage_bicycles")
    else:
        form = BicycleForm()

    bicycles = Bicycle.objects.select_related("station").all()

    return render(request, "core/manage_bicycles.html", {
        "form": form,
        "bicycles": bicycles,
    })

@login_required
def edit_station(request, station_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not authorized.")

    station = get_object_or_404(Station, id=station_id)

    if request.method == "POST":
        form = StationForm(request.POST, instance=station)

        if form.is_valid():
            form.save()
            messages.success(request, "Station updated successfully!")
            return redirect("manage_stations")
    else:
        form = StationForm(instance=station)

    return render(request, "core/edit_station.html", {
        "form": form,
        "station": station,
    })
