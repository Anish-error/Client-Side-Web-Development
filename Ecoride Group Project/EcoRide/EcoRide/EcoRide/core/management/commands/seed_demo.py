from django.core.management.base import BaseCommand

from core.models import Bicycle, Station


class Command(BaseCommand):
    help = "Create sample Pune stations and bicycles for local development."

    def handle(self, *args, **options):
        legacy_station_names = {
            "Cubbon Park": "Swargate",
            "MG Road": "Shivajinagar",
            "Indiranagar": "Pune Railway Station",
        }
        for old_name, new_name in legacy_station_names.items():
            if not Station.objects.filter(name=new_name).exists():
                Station.objects.filter(name=old_name).update(name=new_name)

        samples = [
            {
                "name": "Swargate",
                "address": "Swargate Bus Station, Pune",
                "latitude": 18.5012,
                "longitude": 73.8636,
            },
            {
                "name": "Shivajinagar",
                "address": "Shivajinagar Railway Station, Pune",
                "latitude": 18.5308,
                "longitude": 73.8475,
            },
            {
                "name": "Pune Railway Station",
                "address": "Sasoon Road, Pune",
                "latitude": 18.5289,
                "longitude": 73.8744,
            },
            {
                "name": "Deccan Gymkhana",
                "address": "Deccan Gymkhana, Pune",
                "latitude": 18.5165,
                "longitude": 73.8415,
            },
            {
                "name": "Kothrud Depot",
                "address": "Kothrud Bus Depot, Pune",
                "latitude": 18.5075,
                "longitude": 73.8077,
            },
            {
                "name": "Viman Nagar",
                "address": "Viman Nagar, Pune",
                "latitude": 18.5679,
                "longitude": 73.9143,
            },
        ]
        for sample in samples:
            station, _ = Station.objects.update_or_create(
                name=sample["name"],
                defaults={
                    **sample,
                    "capacity": 16,
                    "is_active": True,
                },
            )
            for number in range(1, 4):
                Bicycle.objects.get_or_create(
                    code=f"ER-{station.pk:02d}-{number:02d}",
                    defaults={
                        "station": station,
                        "is_electric": number == 3,
                        "battery_level": 92 if number == 3 else 100,
                    },
                )
            self.stdout.write(self.style.SUCCESS(f"Ready: {station.name}"))
