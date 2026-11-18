import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Bicycle, Payment, Rental, Station


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class EcoRideFlowTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Swargate",
            address="Swargate Bus Station, Pune",
            latitude=18.5012,
            longitude=73.8636,
            capacity=8,
        )
        self.bicycle = Bicycle.objects.create(station=self.station, code="ER-TEST-01")
        self.user = User.objects.create_user(username="rider", password="SafePass123!")

    def test_home_and_station_map_render(self):
        home_response = self.client.get(reverse("home"))
        stations_response = self.client.get(reverse("stations"))

        self.assertEqual(home_response.status_code, 200)
        self.assertContains(home_response, "Now riding in Pune")
        self.assertEqual(stations_response.status_code, 200)
        self.assertContains(stations_response, "station-data")
        self.assertContains(stations_response, "Swargate Bus Station, Pune")
        self.assertContains(stations_response, "www.google.com/maps/dir")

    def test_signup_creates_and_authenticates_user(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "newrider",
                "password1": "StrongPassword!123",
                "password2": "StrongPassword!123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="newrider").exists())
        self.assertEqual(str(response.url), reverse("dashboard"))

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_rental_checkout_requires_razorpay_configuration(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("start_rental", args=[self.bicycle.pk])
        )

        self.assertRedirects(response, reverse("stations"), fetch_redirect_response=False)
        self.bicycle.refresh_from_db()
        self.assertEqual(self.bicycle.status, Bicycle.Status.AVAILABLE)
        self.assertFalse(Rental.objects.exists())

    @override_settings(RAZORPAY_KEY_ID="rzp_test_id", RAZORPAY_KEY_SECRET="test_secret")
    @patch("core.views._razorpay_client")
    def test_rental_reserves_bike_and_creates_inr_order(self, client_factory):
        client = client_factory.return_value
        client.order.create.return_value = {"id": "order_test_123"}
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("start_rental", args=[self.bicycle.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/checkout.html")
        client.order.create.assert_called_once_with(
            data={
                "amount": 5000,
                "currency": "INR",
                "receipt": "ecoride-rental-1",
                "notes": {"rental_id": "1"},
            }
        )
        rental = Rental.objects.get(user=self.user)
        payment = Payment.objects.get(rental=rental)
        self.bicycle.refresh_from_db()
        self.assertEqual(rental.amount_minor_units, 5000)
        self.assertEqual(rental.currency, "INR")
        self.assertEqual(payment.gateway_order_id, "order_test_123")
        self.assertEqual(self.bicycle.status, Bicycle.Status.RESERVED)

    @override_settings(RAZORPAY_KEY_ID="rzp_test_id", RAZORPAY_KEY_SECRET="test_secret")
    @patch("core.views._razorpay_client")
    def test_verified_captured_payment_activates_reserved_bike(self, client_factory):
        rental = Rental.objects.create(
            user=self.user,
            bicycle=self.bicycle,
            start_station=self.station,
        )
        payment = Payment.objects.create(
            rental=rental,
            gateway_order_id="order_test_123",
        )
        self.bicycle.status = Bicycle.Status.RESERVED
        self.bicycle.save(update_fields=["status"])
        client = client_factory.return_value
        client.payment.fetch.return_value = {
            "id": "pay_test_123",
            "order_id": "order_test_123",
            "amount": 5000,
            "currency": "INR",
            "status": "captured",
        }
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("verify_payment"),
            {
                "razorpay_order_id": "order_test_123",
                "razorpay_payment_id": "pay_test_123",
                "razorpay_signature": "valid-signature",
            },
        )

        self.assertRedirects(
            response,
            reverse("rental_detail", args=[rental.pk]),
            fetch_redirect_response=False,
        )
        client.utility.verify_payment_signature.assert_called_once()
        rental.refresh_from_db()
        payment.refresh_from_db()
        self.bicycle.refresh_from_db()
        self.assertEqual(rental.status, Rental.Status.ACTIVE)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.gateway_payment_id, "pay_test_123")
        self.assertEqual(self.bicycle.status, Bicycle.Status.RENTED)
        self.assertIsNotNone(rental.started_at)

    def test_rental_details_are_private_to_the_rider(self):
        rental = Rental.objects.create(
            user=self.user,
            bicycle=self.bicycle,
            start_station=self.station,
        )
        other_user = User.objects.create_user(
            username="other", password="OtherPass123!"
        )
        self.client.force_login(other_user)

        response = self.client.get(reverse("rental_detail", args=[rental.pk]))

        self.assertEqual(response.status_code, 404)

    def test_returning_a_rented_bike_updates_inventory_and_history(self):
        rental = Rental.objects.create(
            user=self.user,
            bicycle=self.bicycle,
            start_station=self.station,
            status=Rental.Status.ACTIVE,
        )
        self.bicycle.status = Bicycle.Status.RENTED
        self.bicycle.save(update_fields=["status"])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("return_bicycle", args=[rental.pk]),
            {"station_id": self.station.pk},
        )

        self.assertRedirects(
            response,
            reverse("rental_detail", args=[rental.pk]),
            fetch_redirect_response=False,
        )
        rental.refresh_from_db()
        self.bicycle.refresh_from_db()
        self.assertEqual(rental.status, Rental.Status.COMPLETED)
        self.assertEqual(rental.end_station, self.station)
        self.assertEqual(self.bicycle.status, Bicycle.Status.AVAILABLE)
        self.assertIsNotNone(rental.ended_at)

    def test_non_staff_cannot_open_operations_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("staff_dashboard"))

        self.assertEqual(response.status_code, 403)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook_secret")
    def test_signed_payment_webhook_activates_rental(self):
        rental = Rental.objects.create(
            user=self.user,
            bicycle=self.bicycle,
            start_station=self.station,
        )
        Payment.objects.create(
            rental=rental,
            gateway_order_id="order_test_123",
        )
        self.bicycle.status = Bicycle.Status.RESERVED
        self.bicycle.save(update_fields=["status"])
        payload = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_test_123",
                            "order_id": "order_test_123",
                            "amount": 5000,
                            "currency": "INR",
                            "status": "captured",
                        }
                    }
                },
            }
        ).encode()
        signature = hmac.new(
            b"webhook_secret", payload, hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            reverse("razorpay_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        rental.refresh_from_db()
        self.bicycle.refresh_from_db()
        self.assertEqual(rental.status, Rental.Status.ACTIVE)
        self.assertEqual(self.bicycle.status, Bicycle.Status.RENTED)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook_secret")
    def test_invalid_razorpay_webhook_is_rejected(self):
        response = self.client.post(
            reverse("razorpay_webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="invalid",
        )

        self.assertEqual(response.status_code, 400)
