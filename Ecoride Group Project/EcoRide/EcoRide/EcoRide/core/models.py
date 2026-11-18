from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q


class Station(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    capacity = models.PositiveIntegerField(default=12)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def available_bike_count(self):
        return self.bicycles.filter(status=Bicycle.Status.AVAILABLE).count()


class Bicycle(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Reserved"
        RENTED = "rented", "Rented"
        MAINTENANCE = "maintenance", "Maintenance"

    station = models.ForeignKey(
        Station, related_name="bicycles", on_delete=models.PROTECT
    )
    code = models.CharField(max_length=30, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE
    )
    is_electric = models.BooleanField(default=False)
    battery_level = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(battery_level__lte=100), name="bike_battery_at_most_100"
            )
        ]

    def __str__(self):
        return self.code


class Rental(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Awaiting payment"
        ACTIVE = "active", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELED = "canceled", "Canceled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="rentals", on_delete=models.PROTECT
    )
    bicycle = models.ForeignKey(
        Bicycle, related_name="rentals", on_delete=models.PROTECT
    )
    start_station = models.ForeignKey(
        Station, related_name="rentals_started", on_delete=models.PROTECT
    )
    end_station = models.ForeignKey(
        Station,
        related_name="rentals_returned",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    amount_minor_units = models.PositiveIntegerField(default=5000)
    currency = models.CharField(max_length=3, default="INR")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status__in=["pending_payment", "active"]),
                name="one_open_rental_per_user",
            ),
            models.UniqueConstraint(
                fields=["bicycle"],
                condition=Q(status__in=["pending_payment", "active"]),
                name="one_open_rental_per_bicycle",
            ),
        ]

    def __str__(self):
        return f"{self.user} · {self.bicycle} · {self.get_status_display()}"

    @property
    def amount_display(self):
        return Decimal(self.amount_minor_units) / Decimal("100")


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    rental = models.OneToOneField(
        Rental, related_name="payment", on_delete=models.PROTECT
    )
    gateway_order_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    gateway_payment_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    amount_minor_units = models.PositiveIntegerField(default=5000)
    currency = models.CharField(max_length=3, default="INR")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payment for rental {self.rental_id}: {self.get_status_display()}"

    @property
    def amount_display(self):
        return Decimal(self.amount_minor_units) / Decimal("100")
