from django import forms
import phonenumbers

from bookings.models import Booking, ContactInquiry
from bookings.forms import add_country_field, clean_international_phone


class BookingOperationsForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ("status",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


class ContactInquiryEditForm(forms.ModelForm):
    class Meta:
        model = ContactInquiry
        fields = ("name", "email", "phone", "topic", "subject", "status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prepare_fields()

    def _prepare_fields(self):
        add_country_field(self, "phone")
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"
        if self.instance.pk and self.instance.phone and not self.is_bound:
            try:
                parsed = phonenumbers.parse(self.instance.phone, None)
                region = phonenumbers.region_code_for_number(parsed)
                if region in dict(self.fields["phone_country"].choices):
                    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                    calling_code = str(parsed.country_code)
                    self.initial["phone_country"] = region
                    self.initial["phone"] = e164[len(calling_code) + 1:]
            except phonenumbers.NumberParseException:
                pass

    def clean_phone(self):
        return clean_international_phone(self, "phone")


class ContactInquiryCreateForm(ContactInquiryEditForm):
    class Meta(ContactInquiryEditForm.Meta):
        fields = ("name", "email", "phone", "topic", "subject", "message")

    def __init__(self, *args, **kwargs):
        super(ContactInquiryEditForm, self).__init__(*args, **kwargs)
        self._prepare_fields()
        self.fields["message"].widget.attrs.update({"rows": 7, "maxlength": 4000})
        self.fields["message"].widget.attrs["class"] = "input"


class ContactMessageForm(forms.Form):
    body = forms.CharField(max_length=4000, label="Message", widget=forms.Textarea(attrs={"rows": 6, "maxlength": 4000, "class": "input", "placeholder": "Write a reply or add a staff note…"}))
