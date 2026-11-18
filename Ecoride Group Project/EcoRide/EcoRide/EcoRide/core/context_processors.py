from django.conf import settings


def site_settings(request):
    return {
        "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "payments_enabled": bool(
            settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET
        ),
    }
