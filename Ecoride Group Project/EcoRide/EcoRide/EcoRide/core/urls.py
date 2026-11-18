from django.urls import include, path

from . import views

urlpatterns = [
    path("accounts/", include("django.contrib.auth.urls")),
    path("", views.home, name="home"),
    path("accounts/signup/", views.signup, name="signup"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("stations/", views.station_list, name="stations"),
    path("stations/<int:station_id>/", views.station_detail, name="station_detail"),
    path("bicycles/<int:bicycle_id>/rent/", views.start_rental, name="start_rental"),
    path("rentals/<int:rental_id>/", views.rental_detail, name="rental_detail"),
    path("rentals/<int:rental_id>/checkout/", views.retry_checkout, name="retry_checkout"),
    path("rentals/<int:rental_id>/return/", views.return_bicycle, name="return_bicycle"),
    path("rentals/<int:rental_id>/cancel-checkout/", views.cancel_checkout, name="cancel_checkout"),
    path("staff/", views.staff_dashboard, name="staff_dashboard"),
    path("payments/razorpay/verify/", views.verify_payment, name="verify_payment"),
    path("payments/razorpay/webhook/", views.razorpay_webhook, name="razorpay_webhook"),
    path("rentals/<int:rental_id>/mock-checkout/",views.mock_checkout, name="mock_checkout",),
    path("stations/<int:station_id>/start-ride/",views.start_ride,name="start_ride",),
    path("stations/<int:station_id>/verify-bicycle/",views.verify_bicycle_qr,name="verify_bicycle_qr",),
    path("staff/stations/", views.manage_stations, name="manage_stations"),
    path("staff/bicycles/", views.manage_bicycles, name="manage_bicycles"),
    path("staff/stations/<int:station_id>/edit/",views.edit_station,name="edit_station"),
    path("staff/stations/<int:station_id>/deactivate/",views.deactivate_station,name="deactivate_station"),
    path("staff/stations/<int:station_id>/reactivate/",views.reactivate_station,name="reactivate_station"),
    path("staff/bicycles/<int:bicycle_id>/edit/",views.edit_bicycle,name="edit_bicycle"),
    path("staff/bicycles/<int:bicycle_id>/deactivate/",views.deactivate_bicycle,name="deactivate_bicycle",),
    path("staff/bicycles/<int:bicycle_id>/reactivate/",views.reactivate_bicycle,name="reactivate_bicycle",),
    path("api/stations/map-data/",views.station_map_data,name="station_map_data",),
]
