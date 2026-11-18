
from django import forms
from django.contrib.auth import get_user_model

from .models import Station, Bicycle


User = get_user_model()


class StationForm(forms.ModelForm):
    class Meta:
        model = Station
        fields = [
            "name",
            "address",
            "latitude",
            "longitude",
            "capacity",
            "is_active",
        ]


class BicycleForm(forms.ModelForm):
    class Meta:
        model = Bicycle
        fields = [
            "station",
            "code",
            "status",
            "is_electric",
            "battery_level",
        ]
