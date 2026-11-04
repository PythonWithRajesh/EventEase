from datetime import datetime
import json

from django import forms
from django.conf import settings
from django.utils import timezone
import phonenumbers
from babel import Locale
from babel.core import UnknownLocaleError

from .models import Booking, ContactInquiry, VenueSpace


def _country_choices():
    locale = Locale("en")
    choices = []
    regions = {region for group in phonenumbers.COUNTRY_CODE_TO_REGION_CODE.values() for region in group if region != "001"}
    for region in regions:
        try:
            name = locale.territories[region]
        except (KeyError, UnknownLocaleError):
            continue
        code = phonenumbers.country_code_for_region(region)
        if code:
            choices.append((region, f"{name} (+{code})"))
    return sorted(choices, key=lambda choice: choice[1].casefold())


COUNTRY_CHOICES = _country_choices()


def phone_lengths(region):
    metadata = phonenumbers.PhoneMetadata.metadata_for_region(region)
    mobile_lengths = set(metadata.mobile.possible_length) if metadata and metadata.mobile else set()
    if (
        not mobile_lengths
        and metadata
        and getattr(metadata, "same_mobile_and_fixed_line_pattern", False)
    ):
        fixed_line = getattr(metadata, "fixed_line", None)
        if fixed_line:
            mobile_lengths.update(fixed_line.possible_length)
    lengths = sorted(length for length in mobile_lengths if 4 <= length <= 15)
    if not lengths and metadata and metadata.general_desc:
        lengths = sorted(length for length in metadata.general_desc.possible_length if 4 <= length <= 15)
    return lengths or list(range(7, 16))


def normalize_phone(region, raw):
    raw = raw or ""
    if not raw:
        return ""
    allowed_lengths = phone_lengths(region)
    if not raw.isascii() or not raw.isdigit():
        raise forms.ValidationError("Use digits only. Do not enter spaces, +, brackets or dashes.")
    if len(raw) not in allowed_lengths:
        lengths = ", ".join(str(length) for length in allowed_lengths)
        raise forms.ValidationError(f"For the selected country, enter a number with {lengths} digits.")
    try:
        parsed = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        raise forms.ValidationError("Enter a valid phone number for the selected country.")
    if not phonenumbers.is_valid_number(parsed):
        raise forms.ValidationError("Enter a valid phone number for the selected country.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def add_country_field(form, phone_name):
    form.fields["phone_country"] = forms.ChoiceField(choices=[("", "Select country") , *COUNTRY_CHOICES], initial="IN", required=False, label="Country / calling code", widget=forms.Select(attrs={"autocomplete": "country"}))
    lengths_by_country = {region: phone_lengths(region) for region, _ in COUNTRY_CHOICES}
    longest = max((max(lengths) for lengths in lengths_by_country.values()), default=15)
    form.fields[phone_name].widget.attrs.update({
        "type": "tel", "inputmode": "numeric", "autocomplete": "tel-national",
        "placeholder": "10-digit mobile number", "maxlength": 10, "pattern": "[0-9]{10}",
        "data-phone-lengths": json.dumps(lengths_by_country, separators=(",", ":")),
    })
    form.fields[phone_name].help_text = "Digits only; choose the country above and enter the local number without its calling code."
    form.fields[phone_name].strip = False
    order = list(form.fields)
    order.remove("phone_country")
    order.insert(order.index(phone_name), "phone_country")
    form.order_fields(order)


def clean_international_phone(form, phone_name):
    return normalize_phone(form.cleaned_data.get("phone_country") or "IN", form.cleaned_data.get(phone_name, ""))


class ContactInquiryForm(forms.ModelForm):
    class Meta:
        model = ContactInquiry
        fields = ["name", "email", "phone", "topic", "subject", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name", "placeholder": "Your full name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
            "phone": forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "tel-national", "placeholder": "Enter your mobile number", "maxlength": 20}),
            "subject": forms.TextInput(attrs={"placeholder": "What can we help with?", "maxlength": 140}),
            "message": forms.Textarea(attrs={"rows": 6, "placeholder": "Share a few details so our team can help…", "maxlength": 4000}),
        }
        labels = {"phone": "Phone (optional)", "topic": "What is this about?", "message": "How can we help?"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["website"] = forms.CharField(required=False, widget=forms.HiddenInput())
        add_country_field(self, "phone")

    def clean_website(self):
        website = self.cleaned_data.get("website", "")
        if website:
            raise forms.ValidationError("Unable to submit this message.")
        return website

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("phone"):
            try:
                cleaned["phone"] = clean_international_phone(self, "phone")
            except forms.ValidationError as error:
                self.add_error("phone", error)
        return cleaned


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["customer_name", "email", "contact_phone", "quantity", "check_in", "check_out", "payment_method"]
        widgets = {
            "check_in": forms.DateInput(attrs={"type": "date"}),
            "check_out": forms.DateInput(attrs={"type": "date"}),
            "payment_method": forms.RadioSelect,
        }

    def __init__(self, *args, kind=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        self.fields["quantity"].label = "Guests" if kind == Booking.ROOM else "Tickets"
        self.fields["quantity"].widget.attrs.update({"min": 1})
        self.fields["payment_method"].label = "How would you like to pay?"
        cash_label = "Cash at check-in" if kind == Booking.ROOM else "Cash at the venue"
        self.fields["payment_method"].choices = [
            (value, cash_label if value == Booking.CASH else label)
            for value, label in self.fields["payment_method"].choices
        ]
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            self.fields["payment_method"].help_text = "Razorpay needs the site owner's payment keys. Cash at the venue or check-in is available now."
        self.fields["contact_phone"].label = "Mobile number"
        add_country_field(self, "contact_phone")
        if kind == Booking.EVENT:
            self.fields.pop("check_in")
            self.fields.pop("check_out")
        elif kind == Booking.ROOM:
            today = timezone.localdate().isoformat()
            for field in ("check_in", "check_out"):
                self.fields[field].required = True
                self.fields[field].widget.attrs.update({"min": today})

    def clean_contact_phone(self):
        try:
            return clean_international_phone(self, "contact_phone")
        except forms.ValidationError as error:
            raise error

    def clean(self):
        cleaned = super().clean()
        check_in, check_out = cleaned.get("check_in"), cleaned.get("check_out")
        if self.kind == Booking.ROOM and check_in and check_in < timezone.localdate():
            self.add_error("check_in", "Check-in date cannot be in the past.")
        if self.kind == Booking.ROOM and check_in and check_out and check_out <= check_in:
            self.add_error("check_out", "Check-out must be after check-in.")
        if cleaned.get("quantity", 0) < 1:
            self.add_error("quantity", "Quantity must be at least 1.")
        return cleaned


class VenueBookingForm(forms.Form):
    PARTY_OCCASIONS = [(value, value) for value in ("Birthday party", "Engagement", "Anniversary", "Family function", "Kids party", "Other")]
    WEDDING_OCCASIONS = [(value, value) for value in ("Wedding ceremony", "Wedding reception", "Engagement", "Sangeet", "Mehndi", "Family function", "Other")]
    DURATION_CHOICES = [(value, f"{value} hour" + ("s" if value != 1 else "")) for value in range(1, 13)]

    customer_name = forms.CharField(max_length=120, label="Your name", widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    contact_phone = forms.CharField(max_length=20, label="Mobile number", widget=forms.TextInput(attrs={"type": "tel", "inputmode": "numeric", "autocomplete": "tel-national", "placeholder": "10-digit mobile number", "maxlength": 10, "pattern": "[0-9]{10}"}))
    occasion = forms.ChoiceField(choices=PARTY_OCCASIONS, label="What are you celebrating?")
    reservation_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    duration_hours = forms.TypedChoiceField(choices=DURATION_CHOICES, coerce=int, label="Booking duration")
    quantity = forms.IntegerField(min_value=1, label="Expected guests", widget=forms.NumberInput(attrs={"min": 1}))
    payment_method = forms.ChoiceField(choices=Booking.PAYMENT_METHOD_CHOICES, widget=forms.RadioSelect, label="How would you like to pay?")

    def __init__(self, *args, venue=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.venue = venue
        add_country_field(self, "contact_phone")
        if venue and venue.space_type == VenueSpace.PARTY_PLOT:
            hours = range(1, 7)
            self.fields["occasion"].choices = self.PARTY_OCCASIONS
        else:
            hours = range(2, 13)
            self.fields["occasion"].choices = self.WEDDING_OCCASIONS
        self.fields["duration_hours"].choices = [(value, f"{value} hour" + ("s" if value != 1 else "")) for value in hours]
        if venue:
            self.fields["quantity"].widget.attrs["max"] = venue.capacity
            self.fields["quantity"].help_text = f"Maximum capacity: {venue.capacity} guests."
        self.fields["payment_method"].choices = [
            (value, "Cash at the venue" if value == Booking.CASH else label)
            for value, label in self.fields["payment_method"].choices
        ]
        self.fields["reservation_date"].widget.attrs["min"] = timezone.localdate().isoformat()
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            self.fields["payment_method"].help_text = "Online Razorpay requires the site owner's payment keys. Cash at the venue is available now."

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("contact_phone"):
            try:
                cleaned["contact_phone"] = clean_international_phone(self, "contact_phone")
            except forms.ValidationError as error:
                self.add_error("contact_phone", error)
        date, start_time = cleaned.get("reservation_date"), cleaned.get("start_time")
        guests = cleaned.get("quantity")
        if date and date < timezone.localdate():
            self.add_error("reservation_date", "Choose today or a future date.")
        if guests and self.venue and guests > self.venue.capacity:
            self.add_error("quantity", f"This venue can accommodate up to {self.venue.capacity} guests.")
        if date and start_time:
            start = datetime.combine(date, start_time)
            aware_start = timezone.make_aware(start) if timezone.is_naive(start) else start
            if aware_start <= timezone.now():
                self.add_error("start_time", "Choose a future start time.")
        return cleaned
