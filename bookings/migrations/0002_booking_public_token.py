import uuid

from django.db import migrations, models


def assign_tokens(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    for booking in Booking.objects.filter(public_token__isnull=True).iterator():
        booking.public_token = uuid.uuid4()
        booking.save(update_fields=["public_token"])


class Migration(migrations.Migration):
    dependencies = [("bookings", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="public_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(assign_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="booking",
            name="public_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
