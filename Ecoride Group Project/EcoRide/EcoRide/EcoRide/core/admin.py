from django.contrib import admin

from .models import Bicycle, Payment, Rental, Station


class BicycleInline(admin.TabularInline):
    model = Bicycle
    extra = 0


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "capacity", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "address")
    inlines = [BicycleInline]


@admin.register(Bicycle)
class BicycleAdmin(admin.ModelAdmin):
    list_display = ("code", "station", "status", "is_electric", "battery_level")
    list_filter = ("status", "is_electric", "station")
    search_fields = ("code",)


@admin.register(Rental)
class RentalAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "bicycle", "status", "start_station", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "bicycle__code")
    readonly_fields = (
        "user",
        "bicycle",
        "start_station",
        "end_station",
        "status",
        "started_at",
        "ended_at",
        "created_at",
        "amount_minor_units",
        "currency",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("rental", "status", "amount_minor_units", "currency", "created_at", "paid_at")
    list_filter = ("status",)
    readonly_fields = (
        "rental",
        "gateway_order_id",
        "gateway_payment_id",
        "status",
        "amount_minor_units",
        "currency",
        "created_at",
        "paid_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
