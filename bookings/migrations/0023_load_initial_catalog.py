from pathlib import Path
from django.db import migrations
from django.core.management import call_command


def load_initial_catalog(apps, schema_editor):
    FoodItem = apps.get_model("bookings", "FoodItem")
    # If no FoodItem records exist (e.g. fresh production deployment on Render), load the catalog
    if FoodItem.objects.count() == 0:
        fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "initial_catalog.json"
        if fixture_path.exists():
            call_command("loaddata", str(fixture_path), verbosity=1)


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0022_passwordresetotp"),
    ]

    operations = [
        migrations.RunPython(load_initial_catalog, reverse_code=migrations.RunPython.noop),
    ]
