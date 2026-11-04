import re
from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import UserProfile


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Email, Mobile or Username",
        widget=forms.TextInput(attrs={
            "autofocus": True,
            "autocomplete": "username",
            "placeholder": "you@example.com or mobile number",
        }),
    )

    def clean(self):
        identity = self.cleaned_data.get("username", "").strip()
        if "@" in identity:
            matching_user = User.objects.filter(email__iexact=identity).first()
            if matching_user:
                self.cleaned_data["username"] = matching_user.get_username()
        elif identity:
            # Check if entered identity matches a mobile number
            digits = re.sub(r"[^\d]", "", identity)
            if len(digits) == 10:
                profile = UserProfile.objects.filter(mobile_number=digits).select_related("user").first()
                if profile:
                    self.cleaned_data["username"] = profile.user.get_username()
        return super().clean()


class RegistrationForm(forms.Form):
    GENDER_CHOICES = [
        ("", "Select Gender (Optional)"),
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]

    full_name = forms.CharField(
        label="Full Name",
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            "placeholder": "e.g. Hardik Patel",
            "autocomplete": "name",
            "class": "auth-input",
        }),
    )

    email = forms.EmailField(
        label="Email Address",
        required=True,
        widget=forms.EmailInput(attrs={
            "placeholder": "e.g. hardik@example.com",
            "autocomplete": "email",
            "class": "auth-input",
        }),
    )

    mobile_number = forms.CharField(
        label="Mobile Number",
        max_length=15,
        required=True,
        widget=forms.TextInput(attrs={
            "placeholder": "10-digit mobile number",
            "autocomplete": "tel",
            "class": "auth-input",
            "inputmode": "numeric",
        }),
    )

    password = forms.CharField(
        label="Password",
        required=True,
        widget=forms.PasswordInput(attrs={
            "placeholder": "At least 8 characters",
            "autocomplete": "new-password",
            "class": "auth-input",
        }),
    )

    confirm_password = forms.CharField(
        label="Confirm Password",
        required=True,
        widget=forms.PasswordInput(attrs={
            "placeholder": "Re-enter your password",
            "autocomplete": "new-password",
            "class": "auth-input",
        }),
    )

    profile_photo = forms.ImageField(
        label="Profile Photo",
        required=False,
        widget=forms.FileInput(attrs={
            "accept": "image/*",
            "class": "auth-file-input",
            "id": "id_profile_photo",
        }),
    )

    date_of_birth = forms.DateField(
        label="Date of Birth",
        required=False,
        widget=forms.DateInput(attrs={
            "type": "date",
            "class": "auth-input",
        }),
    )

    gender = forms.ChoiceField(
        label="Gender",
        choices=GENDER_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            "class": "auth-select",
        }),
    )

    def clean_full_name(self):
        name = self.cleaned_data.get("full_name", "").strip()
        if len(name) < 2:
            raise ValidationError("Please enter your full name (at least 2 characters).")
        return name

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists. Please log in.")
        return email

    def clean_mobile_number(self):
        raw = self.cleaned_data.get("mobile_number", "").strip()
        digits = re.sub(r"[^\d]", "", raw)
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if len(digits) != 10 or digits[0] not in "6789":
            raise ValidationError("Please enter a valid 10-digit Indian mobile number (e.g. 9898123456).")
        if UserProfile.objects.filter(mobile_number=digits).exists():
            raise ValidationError("This mobile number is already registered with another account.")
        return digits

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            today = timezone.localdate()
            if dob > today:
                raise ValidationError("Date of birth cannot be in the future.")
            if today.year - dob.year > 120:
                raise ValidationError("Please enter a valid date of birth.")
        return dob

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if photo and hasattr(photo, "size"):
            if photo.size > 5 * 1024 * 1024:
                raise ValidationError("Profile photo size should not exceed 5MB.")
        return photo

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("confirm_password")

        if p1 and p2:
            if p1 != p2:
                self.add_error("confirm_password", "Passwords do not match. Please re-enter carefully.")
            else:
                try:
                    password_validation.validate_password(p1)
                except ValidationError as error:
                    self.add_error("password", error)
        return cleaned_data

    def save(self):
        full_name = self.cleaned_data["full_name"]
        email = self.cleaned_data["email"]
        mobile = self.cleaned_data["mobile_number"]
        password = self.cleaned_data["password"]
        photo = self.cleaned_data.get("profile_photo")
        dob = self.cleaned_data.get("date_of_birth")
        gender = self.cleaned_data.get("gender") or ""

        parts = full_name.split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        base_username = re.sub(r"[^a-zA-Z0-9_]", "", email.split("@")[0])[:25]
        if not base_username:
            base_username = "user"
        username = base_username
        suffix = 1
        while User.objects.filter(username__iexact=username).exists():
            username = f"{base_username}_{suffix}"
            suffix += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        UserProfile.objects.create(
            user=user,
            mobile_number=mobile,
            profile_photo=photo,
            date_of_birth=dob,
            gender=gender,
        )

        return user
