from django.db import migrations, models
from django.core.validators import RegexValidator


def normalize_existing_indian_numbers(apps, schema_editor):
    for model_name, field_name in (
        ("Event", "contact_phone"), ("Room", "contact_phone"),
        ("VenueSpace", "contact_phone"), ("Booking", "contact_phone"),
        ("ContactInquiry", "phone"),
    ):
        model = apps.get_model("bookings", model_name)
        for record in model.objects.exclude(**{f"{field_name}__exact": ""}).iterator():
            value = getattr(record, field_name)
            if value.isdigit() and len(value) == 10 and value[0] in "6789":
                setattr(record, field_name, f"+91{value}")
                record.save(update_fields=[field_name])


def restore_existing_indian_numbers(apps, schema_editor):
    for model_name, field_name in (
        ("Event", "contact_phone"), ("Room", "contact_phone"),
        ("VenueSpace", "contact_phone"), ("Booking", "contact_phone"),
        ("ContactInquiry", "phone"),
    ):
        model = apps.get_model("bookings", model_name)
        for record in model.objects.filter(**{f"{field_name}__startswith": "+91"}).iterator():
            value = getattr(record, field_name)
            if len(value) == 13 and value[3:].isdigit():
                setattr(record, field_name, value[3:])
                record.save(update_fields=[field_name])


international_phone_validator = RegexValidator(
    regex=r"^\+[1-9][0-9]{7,14}$",
    message="Enter a valid international number with country calling code, for example +919876543210.",
)


class Migration(migrations.Migration):
    dependencies = [("bookings", "0015_alter_booking_contact_phone_and_more")]

    operations = [
        migrations.RunPython(normalize_existing_indian_numbers, restore_existing_indian_numbers),
        migrations.AlterField(model_name="event", name="contact_phone", field=models.CharField(blank=True, max_length=20, validators=[international_phone_validator])),
        migrations.AlterField(model_name="room", name="contact_phone", field=models.CharField(blank=True, max_length=20, validators=[international_phone_validator])),
        migrations.AlterField(model_name="venuespace", name="contact_phone", field=models.CharField(blank=True, max_length=20, validators=[international_phone_validator])),
        migrations.AlterField(model_name="booking", name="contact_phone", field=models.CharField(default="", max_length=20, validators=[international_phone_validator])),
        migrations.AlterField(model_name="contactinquiry", name="phone", field=models.CharField(blank=True, max_length=20, validators=[international_phone_validator])),
    ]
