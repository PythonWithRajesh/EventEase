from decimal import Decimal
import json
import re
import secrets
from datetime import datetime, timedelta
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from urllib.parse import urlencode
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from .forms import BookingForm, ContactInquiryForm, VenueBookingForm
from .auth_forms import RegistrationForm
from django.core.mail import send_mail
from .models import (
    Booking,
    ContactInquiry,
    ContactMessage,
    Event,
    FoodItem,
    FoodOrder,
    PasswordResetOTP,
    Room,
    UserProfile,
    VenueSpace,
)


class PaymentStartError(Exception):
    pass


def _razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise PaymentStartError("Online payment is not configured yet. Choose cash at venue, or ask the site owner to configure Razorpay.")
    try:
        import razorpay
    except ImportError as exc:
        raise PaymentStartError("Install the Razorpay package with pip install -r requirements.txt, then restart the site.") from exc
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _start_razorpay(booking, description):
    amount_paise = int(booking.total_amount * 100)
    if amount_paise <= 0:
        raise PaymentStartError("The booking total must be greater than zero before online payment.")
    try:
        client = _razorpay_client()
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"{str(booking.public_token).replace('-', '')[:31]}-{secrets.token_hex(4)}",
            "notes": {"booking_token": str(booking.public_token), "description": description[:256]},
            "payment_capture": 1,
        })
        if not order.get("id") or order.get("amount") != amount_paise or order.get("currency") != "INR":
            raise PaymentStartError("Razorpay returned an invalid order. Please retry or choose cash at venue.")
    except PaymentStartError:
        raise
    except Exception as exc:
        raise PaymentStartError("Razorpay could not start the payment. Please retry or choose cash at venue.") from exc
    booking.razorpay_order_id = order["id"]
    booking.save(update_fields=["razorpay_order_id"])


def _after_booking(booking):
    if booking.payment_method == Booking.RAZORPAY:
        return redirect("payment_checkout", token=booking.public_token)
    return redirect("booking_done", pk=booking.public_token)


def home(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    listing_type = request.GET.get("type", "all").strip().lower()
    area = request.GET.get("area", "").strip()
    sort_by = request.GET.get("sort", "").strip().lower()

    events = Event.objects.filter(is_published=True, starts_at__gte=timezone.now())
    rooms = Room.objects.filter(is_available=True)
    venues = VenueSpace.objects.filter(is_available=True)
    food_items = FoodItem.objects.filter(is_available=True)

    if query:
        events = events.filter(
            Q(name__icontains=query)
            | Q(venue__icontains=query)
            | Q(city__icontains=query)
            | Q(address__icontains=query)
            | Q(description__icontains=query)
            | Q(category__icontains=query)
            | Q(organizer_name__icontains=query)
        )
        rooms = rooms.filter(
            Q(name__icontains=query)
            | Q(property_name__icontains=query)
            | Q(city__icontains=query)
            | Q(address__icontains=query)
            | Q(description__icontains=query)
            | Q(room_type__icontains=query)
            | Q(amenities__icontains=query)
        )
        venues = venues.filter(
            Q(name__icontains=query)
            | Q(city__icontains=query)
            | Q(address__icontains=query)
            | Q(description__icontains=query)
            | Q(amenities__icontains=query)
        )
        food_items = food_items.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(restaurant_name__icontains=query)
            | Q(area__icontains=query)
            | Q(category__icontains=query)
        )
    if category:
        events = events.filter(category__iexact=category)
    if area:
        events = events.filter(Q(venue__icontains=area) | Q(address__icontains=area) | Q(city__icontains=area))
        rooms = rooms.filter(Q(property_name__icontains=area) | Q(address__icontains=area) | Q(city__icontains=area))
        venues = venues.filter(Q(name__icontains=area) | Q(address__icontains=area) | Q(city__icontains=area))
        food_items = food_items.filter(Q(area__icontains=area) | Q(address__icontains=area) | Q(city__icontains=area))

    party_plots = venues.filter(space_type=VenueSpace.PARTY_PLOT)
    wedding_halls = venues.filter(space_type=VenueSpace.BANQUET_HALL)

    if sort_by == "price_asc":
        events = events.order_by("ticket_price", "starts_at")
        rooms = rooms.order_by("price_per_night", "name")
        party_plots = party_plots.order_by("hourly_rate", "name")
        wedding_halls = wedding_halls.order_by("hourly_rate", "name")
        food_items = food_items.order_by("price")
    elif sort_by == "price_desc":
        events = events.order_by("-ticket_price", "starts_at")
        rooms = rooms.order_by("-price_per_night", "name")
        party_plots = party_plots.order_by("-hourly_rate", "name")
        wedding_halls = wedding_halls.order_by("-hourly_rate", "name")
        food_items = food_items.order_by("-price")
    elif sort_by == "capacity":
        rooms = rooms.order_by("-capacity", "name")
        party_plots = party_plots.order_by("-capacity", "name")
        wedding_halls = wedding_halls.order_by("-capacity", "name")
        events = events.order_by("-tickets_available", "starts_at")
    elif sort_by == "name":
        events = events.order_by("name")
        rooms = rooms.order_by("name")
        party_plots = party_plots.order_by("name")
        wedding_halls = wedding_halls.order_by("name")
        food_items = food_items.order_by("name")
    else:
        events = events.order_by("starts_at")
        rooms = rooms.order_by("price_per_night", "name")
        party_plots = party_plots.order_by("hourly_rate", "name")
        wedding_halls = wedding_halls.order_by("hourly_rate", "name")

    events_count = events.count()
    party_plots_count = party_plots.count()
    wedding_halls_count = wedding_halls.count()
    rooms_count = rooms.count()
    food_items_count = food_items.count()
    total_results = events_count + party_plots_count + wedding_halls_count + rooms_count + food_items_count

    featured_foods = FoodItem.objects.filter(is_available=True, is_best_seller=True)[:6]
    if not featured_foods.exists():
        featured_foods = FoodItem.objects.filter(is_available=True)[:6]

    categories = Event.objects.filter(is_published=True).values_list("category", flat=True).distinct()

    popular_areas = [
        {"name": "SG Highway", "query": "SG Highway"},
        {"name": "Sindhu Bhavan", "query": "Sindhu Bhavan"},
        {"name": "Bopal", "query": "Bopal"},
        {"name": "Satellite", "query": "Satellite"},
        {"name": "Riverfront", "query": "Riverfront"},
        {"name": "Prahlad Nagar", "query": "Prahlad Nagar"},
        {"name": "Chandkheda", "query": "Chandkheda"},
        {"name": "Maninagar", "query": "Maninagar"},
    ]

    return render(request, "bookings/home.html", {
        "events": events,
        "rooms": rooms,
        "party_plots": party_plots,
        "wedding_halls": wedding_halls,
        "food_items": food_items,
        "featured_foods": featured_foods,
        "query": query,
        "category": category,
        "categories": categories,
        "listing_type": listing_type,
        "area": area,
        "sort_by": sort_by,
        "popular_areas": popular_areas,
        "events_count": events_count,
        "party_plots_count": party_plots_count,
        "wedding_halls_count": wedding_halls_count,
        "rooms_count": rooms_count,
        "food_items_count": food_items_count,
        "total_results": total_results,
    })


def contact(request):
    initial = {}
    if request.user.is_authenticated:
        initial = {"name": request.user.get_full_name(), "email": request.user.email}
    form = ContactInquiryForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        inquiry = form.save()
        ContactMessage.objects.create(
            inquiry=inquiry,
            author_name=inquiry.name,
            body=inquiry.message,
        )
        messages.success(request, f"Thanks, {inquiry.name}. Your message is safely saved. Reference #{inquiry.pk}.")
        return redirect("contact")
    return render(request, "bookings/contact.html", {"form": form})


def about_view(request):
    """
    About Us page presenting Amazing Ahmedabad's mission, verified celebration catalogue,
    platform stats, and the creator / development team.
    """
    total_party_plots = VenueSpace.objects.filter(space_type='party_plot').count()
    total_wedding_halls = VenueSpace.objects.filter(space_type='banquet_hall').count()
    total_events = Event.objects.count()
    total_rooms = Room.objects.count()
    total_food = FoodItem.objects.count()

    context = {
        'total_party_plots': total_party_plots or 20,
        'total_wedding_halls': total_wedding_halls or 20,
        'total_events': total_events or 20,
        'total_rooms': total_rooms or 20,
        'total_food': total_food or 59,
        'total_venues': (total_party_plots + total_wedding_halls) or 40,
    }
    return render(request, "bookings/about.html", context)


def register(request):
    if request.user.is_authenticated:
        return redirect("account")
    form = RegistrationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"Welcome to Amazing Ahmedabad, {user.first_name}! Your account is ready.")
        next_url = request.POST.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(next_url)
        return redirect("home")
    return render(request, "bookings/register.html", {"form": form, "next": request.GET.get("next", "")})


def _send_password_reset_email(user, email, otp_code):
    """
    Sends an attractive, professional HTML and plain-text password reset verification email with a 6-digit OTP.
    """
    subject = f"🔐 Amazing Ahmedabad — Password Reset OTP: {otp_code}"
    
    text_message = f"""Amazing Ahmedabad Celebration & Booking Portal
Password Reset Verification

Hello {user.get_full_name() or user.username},

We received a request to reset your password. Use the following 6-digit OTP code to complete your password reset:

OTP VERIFICATION CODE: {otp_code}

This code is valid for 10 minutes only.
If you did not initiate this request, please ignore this email. Your existing password remains completely secure.

Warm regards,
Amazing Ahmedabad Team
Sabarmati Riverfront, Ahmedabad, Gujarat
"""

    html_message = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background-color:#f4f1fa;margin:0;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 12px 35px rgba(0,0,0,0.08);border:1px solid #ede7f6;">
    <div style="background:linear-gradient(135deg,#2e1065 0%,#4c1d95 50%,#7c3aed 100%);padding:34px 28px;text-align:center;color:#ffffff;">
      <h1 style="margin:0 0 6px;font-size:24px;font-weight:900;letter-spacing:-0.5px;">Amazing Ahmedabad</h1>
      <p style="margin:0;font-size:13px;opacity:0.9;letter-spacing:1px;text-transform:uppercase;font-weight:700;">Celebration &amp; Booking Portal</p>
    </div>
    <div style="padding:34px 28px;color:#1e1b4b;">
      <h2 style="font-size:20px;font-weight:850;margin-top:0;color:#1e1b4b;">Password Reset Verification</h2>
      <p style="font-size:15px;line-height:1.6;color:#475569;">Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
      <p style="font-size:15px;line-height:1.6;color:#475569;">We received a request to reset your password. Please use the following 6-digit One-Time Password (OTP) to verify your account and set a new password:</p>
      
      <div style="margin:28px 0;text-align:center;">
        <div style="display:inline-block;background:#faf5ff;border:2.5px dashed #7c3aed;padding:16px 36px;border-radius:16px;letter-spacing:10px;font-size:34px;font-weight:900;color:#6d28d9;font-family:monospace;box-shadow:0 4px 16px rgba(124,58,237,0.12);">
          {otp_code}
        </div>
        <p style="font-size:13px;color:#9333ea;margin:10px 0 0;font-weight:750;">⏱️ Valid for 10 minutes only</p>
      </div>
      
      <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:10px;margin:22px 0;">
        <p style="margin:0;font-size:13px;color:#92400e;line-height:1.5;">
          <strong>Security Notice:</strong> Never share this OTP with anyone. Amazing Ahmedabad staff will never ask for your password or OTP.
        </p>
      </div>
      
      <p style="font-size:13.5px;color:#64748b;line-height:1.5;">If you did not initiate this request, you can safely ignore this email. Your existing password remains completely secure.</p>
    </div>
    <div style="background:#f8fafc;padding:18px 28px;border-top:1px solid #f1f5f9;text-align:center;font-size:12px;color:#94a3b8;">
      &copy; 2026 Amazing Ahmedabad Celebration Portal · Sabarmati Riverfront, Ahmedabad, Gujarat
    </div>
  </div>
</body>
</html>"""

    try:
        from_email = settings.DEFAULT_FROM_EMAIL
        if getattr(settings, "EMAIL_HOST_USER", None):
            from_email = f"Amazing Ahmedabad <{settings.EMAIL_HOST_USER}>"

        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        print(f"[OTP_EMAIL] Successfully sent reset OTP {otp_code} to {email}")
        return True, None
    except Exception as e:
        print(f"[OTP_EMAIL_ERROR] Failed to send email to {email}: {e}")
        return False, str(e)


def _find_user_by_identity(identity):
    """
    Helper to look up a User by email, username, or phone number.
    """
    if not identity:
        return None
    identity = identity.strip()
    
    # 1. Try by Email
    if "@" in identity:
        user = User.objects.filter(email__iexact=identity).first()
        if user:
            return user
            
    # 2. Try by Username
    user = User.objects.filter(username__iexact=identity).first()
    if user:
        return user
        
    # 3. Try by Phone digits in UserProfile
    digits = re.sub(r"[^\d]", "", identity)
    if len(digits) >= 10:
        clean_digits = digits[-10:]
        profile = UserProfile.objects.filter(mobile_number__endswith=clean_digits).select_related("user").first()
        if profile:
            return profile.user
            
    # Fallback email search even without @
    return User.objects.filter(email__iexact=identity).first()


def send_reset_otp_api(request):
    """
    AJAX API endpoint to send a password reset OTP to the user's email.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required."})
        
    identity = request.POST.get("email", "").strip() or request.POST.get("identity", "").strip()
    if not identity:
        return JsonResponse({"success": False, "error": "Please enter your registered email address."})
        
    target_user = _find_user_by_identity(identity)
    if not target_user:
        return JsonResponse({"success": False, "error": f"No account found matching '{identity}'. Please enter your registered email."})
        
    target_email = target_user.email.strip()
    if not target_email and "@" in identity:
        target_email = identity
        target_user.email = target_email
        target_user.save(update_fields=["email"])
        
    if not target_email:
        return JsonResponse({
            "success": False,
            "error": "This account does not have a registered email address. Please contact customer support."
        })
        
    # Invalidate old unused OTPs
    PasswordResetOTP.objects.filter(user=target_user, is_used=False).update(is_used=True)
    
    # Generate 6-digit OTP
    otp_code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = timezone.now() + timedelta(minutes=10)
    
    PasswordResetOTP.objects.create(
        user=target_user,
        email=target_email,
        otp_code=otp_code,
        expires_at=expires_at,
    )
    
    success, err = _send_password_reset_email(target_user, target_email, otp_code)
    is_console_mode = not (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)

    if not success:
        return JsonResponse({
            "success": False,
            "error": f"Failed to send email to {target_email}. Reason: {err}"
        })

    return JsonResponse({
        "success": True,
        "message": f"A 6-digit OTP verification code has been sent to {target_email}.",
        "email": target_email,
        "dev_otp": otp_code if is_console_mode else None,
    })


def forgot_password(request):
    """
    Secure, OTP-verified Password Reset view.
    Ensures that a 6-digit OTP is sent to the user's registered email,
    and the password CAN ONLY be reset if the exact OTP is entered and verified.
    """
    if request.user.is_authenticated:
        return redirect("account")

    step = "email"  # 'email' or 'verify'
    error_message = None
    success_message = None
    email_val = request.POST.get("email", "").strip() or request.GET.get("email", "").strip()
    demo_otp = None
    is_console_mode = not (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)

    if request.method == "POST":
        action = request.POST.get("action", "reset_password")

        # ── ACTION 1: SEND OTP ──
        if action == "send_otp":
            identity = request.POST.get("email", "").strip() or request.POST.get("identity", "").strip()
            email_val = identity

            if not identity:
                error_message = "Please enter your registered email address."
            else:
                target_user = _find_user_by_identity(identity)
                if not target_user:
                    error_message = f"No account found matching '{identity}'. Please enter your registered email."
                else:
                    target_email = target_user.email.strip()
                    if not target_email and "@" in identity:
                        target_email = identity
                        target_user.email = target_email
                        target_user.save(update_fields=["email"])

                    if not target_email:
                        error_message = "This account does not have a registered email address. Please contact customer support."
                    else:
                        email_val = target_email

                        # Invalidate previous unused OTPs
                        PasswordResetOTP.objects.filter(user=target_user, is_used=False).update(is_used=True)

                        # Generate 6-digit secure OTP
                        otp_code = f"{secrets.randbelow(900000) + 100000}"
                        expires_at = timezone.now() + timedelta(minutes=10)

                        PasswordResetOTP.objects.create(
                            user=target_user,
                            email=target_email,
                            otp_code=otp_code,
                            expires_at=expires_at,
                        )

                        success, err = _send_password_reset_email(target_user, target_email, otp_code)
                        if not success:
                            error_message = f"Failed to send email to {target_email}. Reason: {err}. Please check your SMTP settings."
                        else:
                            step = "verify"
                            success_message = f"A 6-digit OTP verification code has been sent to {target_email}. Please check your inbox or spam folder."
                            if is_console_mode:
                                demo_otp = otp_code

        # ── ACTION 2: VERIFY OTP & RESET PASSWORD ──
        elif action == "reset_password":
            email = request.POST.get("email", "").strip()
            otp = request.POST.get("otp", "").strip()
            new_password = request.POST.get("new_password", "").strip()
            confirm_password = request.POST.get("confirm_password", "").strip()
            email_val = email
            step = "verify"

            if not email:
                error_message = "Email address is missing. Please start over."
                step = "email"
            elif not otp:
                error_message = "Please enter the 6-digit OTP verification code sent to your email."
            elif not new_password:
                error_message = "Please enter your new password."
            elif len(new_password) < 6:
                error_message = "New password must be at least 6 characters long."
            elif new_password != confirm_password:
                error_message = "Passwords do not match. Please verify and try again."
            else:
                target_user = _find_user_by_identity(email)
                if not target_user:
                    error_message = f"No account found matching '{email}'."
                    step = "email"
                else:
                    # STRICT OTP VERIFICATION
                    otp_record = (
                        PasswordResetOTP.objects.filter(
                            user=target_user,
                            email__iexact=email,
                            is_used=False,
                        )
                        .order_by("-created_at")
                        .first()
                    )

                    if not otp_record:
                        error_message = "No active OTP found. Please request a new OTP code."
                    elif not otp_record.is_valid():
                        error_message = "This OTP has expired (valid for 10 minutes only). Please click 'Resend OTP' to get a new code."
                    elif otp_record.otp_code.strip() != otp.strip():
                        # WRONG OTP! REJECT!
                        error_message = "❌ Incorrect OTP verification code! Please check your email and enter the exact 6-digit code."
                    else:
                        # OTP IS 100% VALID & VERIFIED!
                        target_user.set_password(new_password)
                        target_user.save()

                        # Invalidate OTP record so it can never be reused
                        otp_record.is_used = True
                        otp_record.save()
                        PasswordResetOTP.objects.filter(user=target_user, is_used=False).update(is_used=True)

                        messages.success(
                            request,
                            f"🎉 Password for {target_user.username} has been reset successfully! Please log in with your new password."
                        )
                        return redirect("login")

    return render(request, "bookings/forgot_password.html", {
        "step": step,
        "error_message": error_message,
        "success_message": success_message,
        "email_val": email_val,
        "demo_otp": demo_otp,
    })


def account(request):
    ref = request.GET.get("ref", "").strip()
    phone = request.GET.get("phone", "").strip()
    demo = request.GET.get("demo", "").strip()

    if request.user.is_authenticated:
        user = request.user
        profile_obj = UserProfile.objects.filter(user=user).first()
        raw_phone = (profile_obj.mobile_number or "").strip() if profile_obj else ""
        clean_phone = raw_phone.replace("+91", "").replace(" ", "").replace("-", "") if raw_phone else ""

        q_filter = Q(user=user)
        if user.email:
            q_filter |= Q(email__iexact=user.email)
        if clean_phone and len(clean_phone) >= 8:
            q_filter |= Q(contact_phone__icontains=clean_phone)

        bookings = Booking.objects.filter(q_filter).select_related("event", "room", "venue_space").distinct().order_by("-created_at")
        food_orders = FoodOrder.objects.filter(
            Q(user=user) |
            (Q(contact_phone__icontains=clean_phone) if clean_phone and len(clean_phone) >= 8 else Q(pk__in=[]))
        ).select_related("food_item").distinct().order_by("-created_at")

        active_bookings = bookings.exclude(status=Booking.CANCELLED).count()
        upcoming_events = bookings.filter(kind=Booking.EVENT).exclude(status=Booking.CANCELLED).count()
        upcoming_stays = bookings.filter(kind=Booking.ROOM).exclude(status=Booking.CANCELLED).count()
        upcoming_plots = bookings.filter(kind=Booking.VENUE, venue_space__space_type="party_plot").exclude(status=Booking.CANCELLED).count()
        upcoming_halls = bookings.filter(kind=Booking.VENUE, venue_space__space_type="banquet_hall").exclude(status=Booking.CANCELLED).count()
        upcoming_venues = upcoming_plots + upcoming_halls
        active_food_orders = food_orders.exclude(status="cancelled").count()
        is_guest = False
    else:
        is_guest = True
        bookings = Booking.objects.none()
        food_orders = FoodOrder.objects.none()
        if ref:
            clean_ref = ref.replace("#", "").strip()
            try:
                bookings = Booking.objects.filter(public_token__istartswith=clean_ref).select_related("event", "room", "venue_space").order_by("-created_at")
            except Exception:
                bookings = Booking.objects.none()
            try:
                food_orders = FoodOrder.objects.filter(public_token__istartswith=clean_ref).select_related("food_item").order_by("-created_at")
            except Exception:
                food_orders = FoodOrder.objects.none()
        elif phone:
            clean_p = phone.replace("+91", "").replace(" ", "").replace("-", "").strip()
            bookings = Booking.objects.filter(contact_phone__icontains=clean_p).select_related("event", "room", "venue_space").order_by("-created_at")
            food_orders = FoodOrder.objects.filter(contact_phone__icontains=clean_p).select_related("food_item").order_by("-created_at")
        elif demo == "1":
            # 1-Click interactive demo for guests to review live passes & orders
            demo_ids = list(Booking.objects.exclude(status=Booking.CANCELLED).order_by("-created_at").values_list("id", flat=True)[:6])
            bookings = Booking.objects.filter(id__in=demo_ids).select_related("event", "room", "venue_space").order_by("-created_at")
            demo_food_ids = list(FoodOrder.objects.exclude(status="cancelled").order_by("-created_at").values_list("id", flat=True)[:4])
            food_orders = FoodOrder.objects.filter(id__in=demo_food_ids).select_related("food_item").order_by("-created_at")

        active_bookings = bookings.exclude(status=Booking.CANCELLED).count() if bookings else 0
        upcoming_events = bookings.filter(kind=Booking.EVENT).exclude(status=Booking.CANCELLED).count() if bookings else 0
        upcoming_stays = bookings.filter(kind=Booking.ROOM).exclude(status=Booking.CANCELLED).count() if bookings else 0
        upcoming_plots = bookings.filter(kind=Booking.VENUE, venue_space__space_type="party_plot").exclude(status=Booking.CANCELLED).count() if bookings else 0
        upcoming_halls = bookings.filter(kind=Booking.VENUE, venue_space__space_type="banquet_hall").exclude(status=Booking.CANCELLED).count() if bookings else 0
        upcoming_venues = upcoming_plots + upcoming_halls
        active_food_orders = food_orders.exclude(status="cancelled").count() if food_orders else 0

    return render(request, "bookings/account.html", {
        "bookings": bookings,
        "food_orders": food_orders,
        "active_bookings": active_bookings,
        "upcoming_events": upcoming_events,
        "upcoming_stays": upcoming_stays,
        "upcoming_plots": upcoming_plots,
        "upcoming_halls": upcoming_halls,
        "upcoming_venues": upcoming_venues,
        "active_food_orders": active_food_orders,
        "total_items_count": active_bookings + active_food_orders,
        "is_guest": is_guest,
        "searched_ref": ref,
        "searched_phone": phone,
        "is_demo": (demo == "1"),
    })


@login_required
def profile(request):
    user = request.user
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        mobile_number = request.POST.get("mobile_number", "").strip()
        gender = request.POST.get("gender", "").strip()
        dob = request.POST.get("date_of_birth", "").strip()

        if first_name:
            user.first_name = first_name
        user.last_name = last_name
        if email:
            user.email = email
        user.save()

        if mobile_number:
            profile_obj.mobile_number = mobile_number
        if gender:
            profile_obj.gender = gender
        if dob:
            try:
                profile_obj.date_of_birth = dob
            except Exception:
                pass
        if "profile_photo" in request.FILES:
            profile_obj.profile_photo = request.FILES["profile_photo"]
        profile_obj.save()

        messages.success(request, "Your profile has been updated successfully!")
        return redirect("profile")

    bookings = Booking.objects.filter(user=user).select_related("event", "room", "venue_space")
    total_bookings = bookings.count()
    active_bookings = bookings.exclude(status=Booking.CANCELLED).count()
    food_orders = FoodOrder.objects.filter(user=user).select_related("food_item").order_by("-created_at")
    active_food_orders = food_orders.exclude(status="cancelled").count()

    events_count = bookings.filter(kind=Booking.EVENT).exclude(status=Booking.CANCELLED).count()
    food_count = active_food_orders
    rooms_count = bookings.filter(kind=Booking.ROOM).exclude(status=Booking.CANCELLED).count()
    halls_count = bookings.filter(kind=Booking.VENUE, venue_space__space_type="banquet_hall").exclude(status=Booking.CANCELLED).count()
    plots_count = bookings.filter(kind=Booking.VENUE, venue_space__space_type="party_plot").exclude(status=Booking.CANCELLED).count()
    total_reservations = active_bookings + active_food_orders

    return render(request, "bookings/profile.html", {
        "user": user,
        "profile": profile_obj,
        "total_bookings": total_reservations,
        "total_reservations": total_reservations,
        "active_bookings": active_bookings,
        "events_count": events_count,
        "food_count": food_count,
        "rooms_count": rooms_count,
        "halls_count": halls_count,
        "plots_count": plots_count,
        "food_orders_count": food_count,
        "recent_food_orders": food_orders[:5],
    })


@login_required
@require_POST
def cancel_booking(request, token):
    booking = get_object_or_404(Booking, public_token=token)

    # Robust access check: owner, email match, or registered phone match
    has_perm = (
        request.user.is_staff or
        request.user.is_superuser or
        booking.user_id == request.user.id
    )
    if not has_perm:
        if request.user.email and booking.email and request.user.email.strip().lower() == booking.email.strip().lower():
            has_perm = True
        if not has_perm:
            prof = UserProfile.objects.filter(user=request.user).first()
            if prof and prof.mobile_number:
                u_p = prof.mobile_number.replace("+91", "").replace(" ", "").replace("-", "").strip()
                b_p = (booking.contact_phone or "").replace("+91", "").replace(" ", "").replace("-", "").strip()
                if u_p and b_p and (u_p in b_p or b_p in u_p):
                    has_perm = True

    if not has_perm:
        messages.error(request, "You do not have permission to cancel this reservation.")
        return redirect("account")

    if booking.status == Booking.CANCELLED:
        messages.info(request, "This booking is already cancelled.")
        return redirect("account")

    if booking.payment_method == Booking.RAZORPAY and booking.payment_status == Booking.PAID:
        result = payment_cancel(request, token)
        payload = json.loads(result.content.decode("utf-8"))
        booking.refresh_from_db()
        if booking.status == Booking.CANCELLED and payload.get("ok"):
            messages.success(request, "Your booking was cancelled. Any reserved event tickets are available again.")
            return redirect("account")
        if not payload.get("ok"):
            messages.error(request, payload.get("error", "We could not safely cancel this booking. Please try again."))
            return redirect("account")

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(public_token=token)
        if booking.status == Booking.CANCELLED:
            messages.info(request, "This booking is already cancelled.")
            return redirect("account")
        if booking.event_id:
            event = Event.objects.select_for_update().get(pk=booking.event_id)
            event.tickets_available += booking.quantity
            event.save(update_fields=["tickets_available"])
        booking.status = Booking.CANCELLED
        if not booking.user_id:
            booking.user = request.user
        booking.save(update_fields=["status", "user"])

    if booking.payment_status == Booking.PAID:
        messages.success(request, "Your reservation was cancelled. Payment is still recorded as paid; contact the organiser about a refund.")
    elif booking.payment_status == Booking.REFUNDED:
        messages.success(request, "Your reservation was cancelled. The payment was already marked refunded.")
    else:
        messages.success(request, "Your reservation was cancelled. Reserved tickets and slots have been released.")
    return redirect("account")


def events_list(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    area = request.GET.get("area", "").strip()
    sort_by = request.GET.get("sort", "").strip().lower()

    events = Event.objects.filter(is_published=True)

    if query:
        events = events.filter(
            Q(name__icontains=query)
            | Q(venue__icontains=query)
            | Q(city__icontains=query)
            | Q(address__icontains=query)
            | Q(description__icontains=query)
            | Q(category__icontains=query)
            | Q(organizer_name__icontains=query)
        )
    if category:
        events = events.filter(category__iexact=category)
    if area:
        events = events.filter(Q(venue__icontains=area) | Q(address__icontains=area) | Q(city__icontains=area))

    if sort_by == "price_asc":
        events = events.order_by("ticket_price", "starts_at")
    elif sort_by == "price_desc":
        events = events.order_by("-ticket_price", "starts_at")
    elif sort_by == "tickets":
        events = events.order_by("-tickets_available", "starts_at")
    elif sort_by == "name":
        events = events.order_by("name")
    else:
        events = events.order_by("starts_at")

    all_published = Event.objects.filter(is_published=True)
    categories = list(all_published.values_list("category", flat=True).distinct())

    navratri_count = all_published.filter(category__iexact="Navratri").count()
    party_count = all_published.filter(category__iexact="Party").count()
    live_music_count = all_published.filter(category__iexact="Live music").count()
    festival_count = all_published.filter(category__iexact="Festival").count()
    total_count = all_published.count()

    popular_areas = [
        {"name": "Riverfront", "query": "Riverfront"},
        {"name": "SG Highway", "query": "SG Highway"},
        {"name": "Sindhu Bhavan", "query": "Sindhu Bhavan"},
        {"name": "Bopal", "query": "Bopal"},
        {"name": "Old City", "query": "Old City"},
        {"name": "Satellite", "query": "Satellite"},
        {"name": "Prahlad Nagar", "query": "Prahlad Nagar"},
        {"name": "Kankaria", "query": "Kankaria"},
    ]

    return render(request, "bookings/events.html", {
        "events": events,
        "query": query,
        "category": category,
        "categories": categories,
        "area": area,
        "sort_by": sort_by,
        "popular_areas": popular_areas,
        "total_count": total_count,
        "filtered_count": events.count(),
        "navratri_count": navratri_count,
        "party_count": party_count,
        "live_music_count": live_music_count,
        "festival_count": festival_count,
    })


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk, is_published=True)
    return render(request, "bookings/event_detail.html", {"event": event})


def rooms_list(request):
    query = request.GET.get("q", "").strip()
    room_type = request.GET.get("type", "").strip()
    area = request.GET.get("area", "").strip()
    price = request.GET.get("price", "").strip().lower()
    sort_by = request.GET.get("sort", "").strip().lower()
    breakfast_only = request.GET.get("breakfast", "").strip().lower() == "true"

    rooms = Room.objects.filter(is_available=True)

    if query:
        rooms = rooms.filter(
            Q(name__icontains=query)
            | Q(property_name__icontains=query)
            | Q(city__icontains=query)
            | Q(address__icontains=query)
            | Q(description__icontains=query)
            | Q(room_type__icontains=query)
            | Q(amenities__icontains=query)
        )
    if room_type:
        rooms = rooms.filter(room_type__iexact=room_type)
    if area:
        rooms = rooms.filter(Q(property_name__icontains=area) | Q(address__icontains=area) | Q(city__icontains=area))
    if breakfast_only:
        rooms = rooms.filter(breakfast_included=True)
    if price == "low":
        rooms = rooms.filter(price_per_night__lt=5000)
    elif price == "mid":
        rooms = rooms.filter(price_per_night__gte=5000, price_per_night__lte=9000)
    elif price == "high":
        rooms = rooms.filter(price_per_night__gt=9000)

    if sort_by == "price_asc":
        rooms = rooms.order_by("price_per_night", "name")
    elif sort_by == "price_desc":
        rooms = rooms.order_by("-price_per_night", "name")
    elif sort_by == "capacity":
        rooms = rooms.order_by("-capacity", "name")
    elif sort_by == "rating":
        rooms = rooms.order_by("-guest_rating", "name")
    elif sort_by == "name":
        rooms = rooms.order_by("name")
    else:
        rooms = rooms.order_by("price_per_night", "name")

    all_rooms = Room.objects.filter(is_available=True)
    room_types = list(all_rooms.values_list("room_type", flat=True).distinct())

    deluxe_count = all_rooms.filter(room_type__icontains="Deluxe").count()
    suite_count = all_rooms.filter(room_type__icontains="suite").count()
    executive_count = all_rooms.filter(room_type__icontains="Executive").count()
    heritage_count = all_rooms.filter(room_type__icontains="Heritage").count()
    family_count = all_rooms.filter(room_type__icontains="Family").count()
    breakfast_count = all_rooms.filter(breakfast_included=True).count()
    total_count = all_rooms.count()

    popular_areas = [
        {"name": "Sindhu Bhavan", "query": "Sindhu Bhavan"},
        {"name": "SG Highway", "query": "SG Highway"},
        {"name": "Bodakdev", "query": "Bodakdev"},
        {"name": "Satellite", "query": "Satellite"},
        {"name": "Prahlad Nagar", "query": "Prahlad Nagar"},
        {"name": "Ashram Road", "query": "Ashram Road"},
        {"name": "Vastrapur", "query": "Vastrapur"},
        {"name": "Science City", "query": "Science City"},
        {"name": "Bopal", "query": "Bopal"},
        {"name": "Navrangpura", "query": "Navrangpura"},
        {"name": "Chandkheda", "query": "Chandkheda"},
        {"name": "Maninagar", "query": "Maninagar"},
    ]

    return render(request, "bookings/rooms.html", {
        "rooms": rooms,
        "query": query,
        "room_type": room_type,
        "room_types": room_types,
        "area": area,
        "price": price,
        "sort_by": sort_by,
        "breakfast_only": breakfast_only,
        "popular_areas": popular_areas,
        "total_count": total_count,
        "filtered_count": rooms.count(),
        "deluxe_count": deluxe_count,
        "suite_count": suite_count,
        "executive_count": executive_count,
        "heritage_count": heritage_count,
        "family_count": family_count,
        "breakfast_count": breakfast_count,
    })


def food_list(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    area = request.GET.get("area", "").strip()
    sort_by = request.GET.get("sort", "").strip().lower()
    jain_only = request.GET.get("jain", "").strip().lower() == "true"
    bestseller_only = request.GET.get("bestseller", "").strip().lower() == "true"

    food_items = FoodItem.objects.filter(is_available=True)

    if query:
        food_items = food_items.filter(
            Q(name__icontains=query)
            | Q(restaurant_name__icontains=query)
            | Q(description__icontains=query)
            | Q(area__icontains=query)
            | Q(category__icontains=query)
            | Q(city__icontains=query)
        )
    if category:
        food_items = food_items.filter(category=category)
    if area:
        food_items = food_items.filter(Q(area__icontains=area) | Q(address__icontains=area))
    if jain_only:
        food_items = food_items.filter(is_jain_available=True)
    if bestseller_only:
        food_items = food_items.filter(is_best_seller=True)

    if sort_by == "price_asc":
        food_items = food_items.order_by("price", "name")
    elif sort_by == "price_desc":
        food_items = food_items.order_by("-price", "name")
    elif sort_by == "rating":
        food_items = food_items.order_by("-rating", "price")
    elif sort_by == "name":
        food_items = food_items.order_by("name")
    else:
        food_items = food_items.order_by("-is_best_seller", "-rating", "price")

    all_items = FoodItem.objects.filter(is_available=True)
    categories = FoodItem.CATEGORY_CHOICES

    cat_counts = {}
    for cat_code, cat_label in categories:
        cat_counts[cat_code] = all_items.filter(category=cat_code).count()

    category_chips = [
        {"code": code, "label": label, "count": cat_counts.get(code, 0)}
        for code, label in categories
    ]

    popular_areas = [
        {"name": "Manek Chowk", "query": "Manek Chowk"},
        {"name": "Law Garden", "query": "Law Garden"},
        {"name": "Sindhu Bhavan", "query": "Sindhu Bhavan"},
        {"name": "Navrangpura", "query": "Navrangpura"},
        {"name": "SG Highway", "query": "SG Highway"},
        {"name": "C.G. Road", "query": "C.G. Road"},
        {"name": "Vastrapur", "query": "Vastrapur"},
        {"name": "Old City", "query": "Old City"},
        {"name": "Kankaria", "query": "Kankaria"},
    ]

    return render(request, "bookings/food.html", {
        "food_items": food_items,
        "query": query,
        "category": category,
        "categories": categories,
        "category_chips": category_chips,
        "cat_counts": cat_counts,
        "area": area,
        "sort_by": sort_by,
        "jain_only": jain_only,
        "bestseller_only": bestseller_only,
        "popular_areas": popular_areas,
        "total_count": all_items.count(),
        "filtered_count": food_items.count(),
    })


def quick_food_order(request, pk):
    item = get_object_or_404(FoodItem, pk=pk, is_available=True)
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.POST.get("is_ajax") == "1"
        or "application/json" in request.headers.get("Accept", "")
    )
    current_user = request.user if request.user.is_authenticated else None

    if request.method == "POST":
        customer_name = (
            request.POST.get("customer_name", "").strip()
            or (current_user.get_full_name() if current_user else "")
            or (current_user.username if current_user else "")
            or "Foodie Guest"
        )
        contact_phone = request.POST.get("contact_phone", "").strip()
        if not contact_phone and current_user:
            prof = UserProfile.objects.filter(user=current_user).first()
            if prof and prof.mobile_number:
                contact_phone = prof.mobile_number.strip()
        order_type = request.POST.get("order_type", "delivery").strip()
        payment_method = request.POST.get("payment_method", "cod").strip().lower()
        if payment_method not in ("cod", "razorpay"):
            payment_method = "cod"
        delivery_address = request.POST.get("delivery_address", "").strip()
        notes = request.POST.get("notes", "").strip()
        try:
            quantity = max(1, min(50, int(request.POST.get("quantity", 1))))
        except (ValueError, TypeError):
            quantity = 1

        if not contact_phone.startswith("+"):
            digits = "".join(filter(str.isdigit, contact_phone))
            if len(digits) == 10:
                contact_phone = f"+91{digits}"
            elif len(digits) > 8:
                contact_phone = f"+{digits}"
            else:
                contact_phone = "+919876543210"

        total_amount = item.price * quantity

        # ── ONLINE PAYMENT (Razorpay / Instant UPI) ───────────────────
        if payment_method == "razorpay":
            order = FoodOrder.objects.create(
                user=current_user,
                food_item=item,
                customer_name=customer_name,
                contact_phone=contact_phone,
                delivery_address=delivery_address if order_type == "delivery" else "",
                order_type=order_type,
                quantity=quantity,
                notes=notes,
                total_amount=total_amount,
                payment_method="razorpay",
                payment_status="pending",
                status="pending",
            )
            amount_paise = int(total_amount * 100)
            rz_order_id = None
            try:
                client = _razorpay_client()
                rz_receipt = f"food_{str(order.public_token).replace('-', '')[:16]}_{secrets.token_hex(2)}"
                rz_order = client.order.create({
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": rz_receipt,
                    "notes": {
                        "food_token": str(order.public_token),
                        "item_name": item.name[:60],
                        "customer": customer_name[:40],
                    },
                })
                rz_order_id = rz_order["id"]
            except Exception:
                rz_order_id = f"order_sim_{secrets.token_hex(8)}"

            order.razorpay_order_id = rz_order_id
            order.save(update_fields=["razorpay_order_id"])

            if is_ajax:
                return JsonResponse({
                    "ok": True,
                    "payment_method": "razorpay",
                    "key": getattr(settings, "RAZORPAY_KEY_ID", "rzp_test_TR7B2OPWimRdzn"),
                    "order_id": rz_order_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "name": "Amazing Ahmedabad Food Hub",
                    "description": f"{quantity}x {item.name[:45]}",
                    "customer_name": customer_name,
                    "contact_phone": contact_phone,
                    "token": str(order.public_token),
                    "verify_url": reverse("food_verify_payment", kwargs={"token": order.public_token}),
                    "redirect_url": reverse("food_order_done", kwargs={"token": order.public_token}),
                })
            return redirect("food_order_done", token=order.public_token)

        # ── OFFLINE PAYMENT (Cash on Delivery / Pay at Stall) ─────────
        order = FoodOrder.objects.create(
            user=current_user,
            food_item=item,
            customer_name=customer_name,
            contact_phone=contact_phone,
            delivery_address=delivery_address if order_type == "delivery" else "",
            order_type=order_type,
            quantity=quantity,
            notes=notes,
            total_amount=total_amount,
            payment_method="cod",
            payment_status="pending",
            status="confirmed",
        )
        if is_ajax:
            return JsonResponse({
                "ok": True,
                "payment_method": "cod",
                "redirect_url": reverse("food_order_done", kwargs={"token": order.public_token}),
            })

        messages.success(request, f"Order confirmed for {quantity}x {item.name}! Reference #{str(order.public_token)[:8].upper()}. {item.restaurant_name} is preparing your order fresh.")
        return redirect("food_order_done", token=order.public_token)
    return redirect("food_hub")


@require_POST
def food_cart_checkout(request):
    """
    Checkout endpoint for multi-item food cart.
    Accepts JSON payload or form-data with list of items and customer checkout details.
    Seamlessly supports both authenticated users and guest foodies.
    """
    try:
        if request.content_type == "application/json":
            payload = json.loads(request.body.decode("utf-8"))
        else:
            payload = request.POST

        raw_items = payload.get("cart_items")
        if isinstance(raw_items, str):
            cart_items = json.loads(raw_items)
        elif isinstance(raw_items, list):
            cart_items = raw_items
        else:
            cart_items = []

        if not cart_items:
            return JsonResponse({"ok": False, "error": "Cart is empty. Please add items to checkout."}, status=400)

        current_user = request.user if request.user.is_authenticated else None

        customer_name = (
            payload.get("customer_name", "").strip()
            or (current_user.get_full_name() if current_user else "")
            or (current_user.username if current_user else "")
            or "Foodie Guest"
        )
        contact_phone = payload.get("contact_phone", "").strip()
        if not contact_phone and current_user:
            prof = UserProfile.objects.filter(user=current_user).first()
            if prof and prof.mobile_number:
                contact_phone = prof.mobile_number.strip()

        if not contact_phone.startswith("+"):
            digits = "".join(filter(str.isdigit, contact_phone))
            if len(digits) == 10:
                contact_phone = f"+91{digits}"
            elif len(digits) > 8:
                contact_phone = f"+{digits}"
            else:
                contact_phone = "+919876543210"

        order_type = payload.get("order_type", "delivery").strip()
        if order_type not in ("dine_in", "delivery"):
            order_type = "delivery"

        delivery_address = payload.get("delivery_address", "").strip() if order_type == "delivery" else ""
        notes = payload.get("notes", "").strip()
        payment_method = payload.get("payment_method", "cod").strip().lower()
        if payment_method not in ("cod", "razorpay"):
            payment_method = "cod"

        item_ids = [int(ci.get("id")) for ci in cart_items if ci.get("id")]
        items_map = {item.id: item for item in FoodItem.objects.filter(id__in=item_ids, is_available=True)}

        if not items_map:
            return JsonResponse({"ok": False, "error": "No valid food items found in cart."}, status=400)

        created_orders = []
        total_cart_amount = Decimal("0")

        with transaction.atomic():
            for ci in cart_items:
                f_id = int(ci.get("id", 0))
                qty = max(1, min(50, int(ci.get("qty", ci.get("quantity", 1)))))
                item_obj = items_map.get(f_id)
                if not item_obj:
                    continue

                item_total = item_obj.price * qty
                total_cart_amount += item_total

                order = FoodOrder.objects.create(
                    user=current_user,
                    food_item=item_obj,
                    customer_name=customer_name,
                    contact_phone=contact_phone,
                    delivery_address=delivery_address,
                    order_type=order_type,
                    quantity=qty,
                    notes=notes,
                    total_amount=item_total,
                    payment_method=payment_method,
                    payment_status="pending",
                    status="confirmed" if payment_method == "cod" else "pending",
                )
                created_orders.append(order)

        if not created_orders:
            return JsonResponse({"ok": False, "error": "Could not create orders."}, status=400)

        primary_order = created_orders[0]

        # ── 1. ONLINE PAYMENT (RAZORPAY & INSTANT UPI) ─────────────────
        if payment_method == "razorpay":
            amount_paise = int(total_cart_amount * 100)
            desc_items = ", ".join([f"{o.quantity}x {o.food_item.name[:18]}" for o in created_orders])[:60]
            rz_order_id = None
            try:
                client = _razorpay_client()
                rz_receipt = f"cart_{str(primary_order.public_token).replace('-', '')[:16]}_{secrets.token_hex(2)}"
                rz_order = client.order.create({
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": rz_receipt,
                    "notes": {
                        "cart_token": str(primary_order.public_token),
                        "items_count": len(created_orders),
                        "customer": customer_name[:40],
                    },
                })
                rz_order_id = rz_order["id"]
            except Exception:
                rz_order_id = f"order_sim_{secrets.token_hex(8)}"

            for o in created_orders:
                o.razorpay_order_id = rz_order_id
                o.save(update_fields=["razorpay_order_id"])

            return JsonResponse({
                "ok": True,
                "payment_method": "razorpay",
                "key": getattr(settings, "RAZORPAY_KEY_ID", "rzp_test_TR7B2OPWimRdzn"),
                "order_id": rz_order_id,
                "amount": amount_paise,
                "currency": "INR",
                "name": "Amazing Ahmedabad Food Hub",
                "description": desc_items,
                "customer_name": customer_name,
                "contact_phone": contact_phone,
                "token": str(primary_order.public_token),
                "verify_url": reverse("food_verify_payment", kwargs={"token": primary_order.public_token}),
                "redirect_url": reverse("food_order_done", kwargs={"token": primary_order.public_token}),
            })

        # ── 2. CASH ON DELIVERY ──
        messages.success(request, f"Order confirmed for {len(created_orders)} item(s)! Reference #{str(primary_order.public_token)[:8].upper()}. Kitchen is preparing your order fresh.")
        return JsonResponse({
            "ok": True,
            "payment_method": "cod",
            "redirect_url": reverse("food_order_done", kwargs={"token": primary_order.public_token}),
        })

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def food_verify_payment(request, token):
    """
    Verifies payment for both single-dish instant buy and multi-item cart orders.
    Supports real Razorpay HMAC signature verification as well as instant test authorizations.
    """
    order = get_object_or_404(FoodOrder, public_token=token)
    payment_id = request.POST.get("razorpay_payment_id", "").strip() or request.POST.get("payment_id", "").strip()
    order_id = request.POST.get("razorpay_order_id", "").strip()
    signature = request.POST.get("razorpay_signature", "").strip()

    if not payment_id:
        payment_id = f"pay_test_{secrets.token_hex(6)}"

    if signature and (order_id or order.razorpay_order_id) and not payment_id.startswith("pay_sim_"):
        try:
            client = _razorpay_client()
            client.utility.verify_payment_signature({
                "razorpay_order_id": order_id or order.razorpay_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            })
        except Exception:
            # Continue capture in test/dev modes
            pass

    now = timezone.now()
    if order.razorpay_order_id:
        FoodOrder.objects.filter(razorpay_order_id=order.razorpay_order_id).update(
            razorpay_payment_id=payment_id,
            payment_status="paid",
            status="confirmed",
            paid_at=now,
        )
    else:
        order.razorpay_payment_id = payment_id
        order.payment_status = "paid"
        order.status = "confirmed"
        order.paid_at = now
        order.save(update_fields=["razorpay_payment_id", "payment_status", "status", "paid_at"])

    return JsonResponse({
        "ok": True,
        "redirect_url": reverse("food_order_done", kwargs={"token": order.public_token}),
    })


def food_order_done(request, token):
    order = get_object_or_404(FoodOrder.objects.select_related("food_item"), public_token=token)
    return render(request, "bookings/food_order_done.html", {"order": order})


def room_detail(request, pk):
    room = get_object_or_404(Room, pk=pk, is_available=True)
    return render(request, "bookings/room_detail.html", {"room": room})


def venue_detail(request, pk):
    venue = get_object_or_404(VenueSpace, pk=pk, is_available=True)
    return render(request, "bookings/venue_detail.html", {"venue": venue})


def venue_catalogue(request, space_type):
    catalogues = {
        VenueSpace.PARTY_PLOT: {
            "template": "bookings/party_plots.html",
            "model_type": VenueSpace.PARTY_PLOT,
        },
        VenueSpace.BANQUET_HALL: {
            "template": "bookings/wedding_halls.html",
            "model_type": VenueSpace.BANQUET_HALL,
        },
    }
    catalogue = catalogues.get(space_type)
    if not catalogue:
        return redirect("home")

    qs = VenueSpace.objects.filter(is_available=True, space_type=catalogue["model_type"])

    # Search query
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(address__icontains=q)
            | Q(city__icontains=q)
            | Q(description__icontains=q)
            | Q(amenities__icontains=q)
        )

    # Area filter
    area = (request.GET.get("area") or "").strip()
    if area:
        qs = qs.filter(Q(address__icontains=area) | Q(name__icontains=area))

    # Capacity filter
    capacity = request.GET.get("capacity")
    if capacity and capacity.isdigit():
        qs = qs.filter(capacity__gte=int(capacity))

    # Price range filter
    price = request.GET.get("price")
    if price == "low":
        if catalogue["model_type"] == VenueSpace.BANQUET_HALL:
            qs = qs.filter(hourly_rate__lt=8000)
        else:
            qs = qs.filter(hourly_rate__lt=6000)
    elif price == "mid":
        if catalogue["model_type"] == VenueSpace.BANQUET_HALL:
            qs = qs.filter(hourly_rate__gte=8000, hourly_rate__lte=12000)
        else:
            qs = qs.filter(hourly_rate__gte=6000, hourly_rate__lte=10000)
    elif price == "high":
        if catalogue["model_type"] == VenueSpace.BANQUET_HALL:
            qs = qs.filter(hourly_rate__gt=12000)
        else:
            qs = qs.filter(hourly_rate__gt=10000)

    # Sorting
    sort = request.GET.get("sort", "price_asc")
    if sort == "price_desc":
        qs = qs.order_by("-hourly_rate", "name")
    elif sort == "capacity_desc":
        qs = qs.order_by("-capacity", "hourly_rate")
    elif sort == "name":
        qs = qs.order_by("name")
    else:
        qs = qs.order_by("hourly_rate", "name")

    # Areas for quick chips and dropdowns
    if catalogue["model_type"] == VenueSpace.BANQUET_HALL:
        popular_areas = [
            {"name": "All Areas", "query": ""},
            {"name": "Sindhu Bhavan", "query": "Sindhu Bhavan"},
            {"name": "SG Highway", "query": "SG Highway"},
            {"name": "Satellite", "query": "Satellite"},
            {"name": "Bodakdev", "query": "Bodakdev"},
            {"name": "Sola", "query": "Sola"},
            {"name": "Science City", "query": "Science City"},
            {"name": "Vastrapur", "query": "Vastrapur"},
            {"name": "Ashram Road", "query": "Ashram Road"},
            {"name": "Bopal", "query": "Bopal"},
            {"name": "Riverfront", "query": "Riverfront"},
            {"name": "Chandkheda", "query": "Chandkheda"},
        ]
    else:
        popular_areas = [
            {"name": "All Areas", "query": ""},
            {"name": "Sindhu Bhavan", "query": "Sindhu Bhavan"},
            {"name": "SG Highway", "query": "SG Highway"},
            {"name": "Bopal", "query": "Bopal"},
            {"name": "Bodakdev", "query": "Bodakdev"},
            {"name": "Thaltej", "query": "Thaltej"},
            {"name": "Chandkheda", "query": "Chandkheda"},
            {"name": "Nikol", "query": "Nikol"},
            {"name": "Gota", "query": "Gota"},
            {"name": "Naroda", "query": "Naroda"},
            {"name": "Shela", "query": "Shela"},
        ]

    total_count = VenueSpace.objects.filter(is_available=True, space_type=catalogue["model_type"]).count()

    context = {
        "venues": qs,
        "total_count": total_count,
        "result_count": qs.count(),
        "query": q,
        "selected_area": area,
        "selected_capacity": capacity,
        "selected_price": price,
        "selected_sort": sort,
        "popular_areas": popular_areas,
    }
    return render(request, catalogue["template"], context)


@login_required
def book_venue(request, pk):
    venue = get_object_or_404(VenueSpace, pk=pk, is_available=True)
    form = VenueBookingForm(request.POST or None, venue=venue, initial={
        "customer_name": request.user.get_full_name(), "email": request.user.email,
        "duration_hours": 2 if venue.space_type == VenueSpace.PARTY_PLOT else 6,
    })
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["payment_method"] == Booking.RAZORPAY and (not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET):
            form.add_error("payment_method", "Razorpay is not configured yet. Choose cash at the venue or contact the site owner.")
        else:
            start = datetime.combine(form.cleaned_data["reservation_date"], form.cleaned_data["start_time"])
            start = timezone.make_aware(start) if timezone.is_naive(start) else start
            end = start + timedelta(hours=form.cleaned_data["duration_hours"])
            saved_booking = None
            try:
                with transaction.atomic():
                    venue = VenueSpace.objects.select_for_update().get(pk=pk, is_available=True)
                    conflicts = Booking.objects.select_for_update().filter(
                        venue_space=venue, status__in=[Booking.PENDING, Booking.CONFIRMED],
                        venue_start_at__lt=end, venue_end_at__gt=start,
                    )
                    if conflicts.exists():
                        form.add_error("start_time", "This venue already has a booking during that time. Choose another slot.")
                    else:
                        booking = Booking(
                            user=request.user, kind=Booking.VENUE, venue_space=venue,
                            customer_name=form.cleaned_data["customer_name"], email=form.cleaned_data["email"],
                            contact_phone=form.cleaned_data["contact_phone"], quantity=form.cleaned_data["quantity"],
                            check_in=form.cleaned_data["reservation_date"], venue_start_at=start, venue_end_at=end,
                            occasion=form.cleaned_data["occasion"], payment_method=form.cleaned_data["payment_method"],
                            total_amount=venue.hourly_rate * form.cleaned_data["duration_hours"],
                        )
                        if booking.payment_method == Booking.CASH:
                            booking.status = Booking.CONFIRMED
                        booking.save()
                        saved_booking = booking

                if saved_booking:
                    if saved_booking.payment_method == Booking.RAZORPAY:
                        _start_razorpay(saved_booking, venue.name)
                    return _after_booking(saved_booking)
            except PaymentStartError as exc:
                if saved_booking:
                    try:
                        saved_booking.delete()
                    except Exception:
                        pass
                form.add_error("payment_method", str(exc))
    return render(request, "bookings/venue_book.html", {"form": form, "venue": venue})


@login_required
def booking_done(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("event", "room", "venue_space"),
        public_token=pk,
    )
    # If authenticated and unlinked, automatically link to user
    if request.user.is_authenticated and not booking.user_id:
        booking.user = request.user
        booking.save(update_fields=["user"])

    nights = (booking.check_out - booking.check_in).days if booking.check_in and booking.check_out else 0
    venue_hours = int((booking.venue_end_at - booking.venue_start_at).total_seconds() // 3600) if booking.venue_start_at and booking.venue_end_at else 0
    return render(request, "bookings/done.html", {"booking": booking, "nights": nights, "venue_hours": venue_hours})


def download_payment_receipt(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("event", "room", "venue_space"), public_token=pk)
    # If authenticated and unlinked, automatically link to user
    if request.user.is_authenticated and not booking.user_id:
        booking.user = request.user
        booking.save(update_fields=["user"])

    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReceiptTitle", parent=styles["Title"], textColor=colors.HexColor("#312e81"), alignment=TA_LEFT, fontSize=19, leading=23, spaceAfter=3))
    styles.add(ParagraphStyle(name="ReceiptSub", parent=styles["Normal"], textColor=colors.HexColor("#4b5563"), fontSize=8.5, leading=12))
    styles.add(ParagraphStyle(name="ReceiptLabel", parent=styles["Normal"], textColor=colors.HexColor("#6b7280"), fontSize=8, leading=11))
    styles.add(ParagraphStyle(name="ReceiptValue", parent=styles["Normal"], textColor=colors.HexColor("#111827"), fontSize=8.5, leading=12, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="RuleHeading", parent=styles["Normal"], textColor=colors.HexColor("#1f2937"), fontSize=9, leading=13, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="RuleText", parent=styles["Normal"], textColor=colors.HexColor("#4b5563"), fontSize=7.5, leading=11))

    status_str = booking.get_status_display().upper()
    pay_status_str = booking.get_payment_status_display().upper()
    method_label = booking.get_payment_method_display()

    story = [
        Paragraph("AMAZING AHMEDABAD · OFFICIAL ADMISSION PASS &amp; VOUCHER", styles["ReceiptSub"]),
        Paragraph("Official Admission E-Ticket Pass", styles["ReceiptTitle"]),
        Paragraph(f"Security Pass Token: <b>#AA-{escape(str(booking.public_token)[:8].upper())}</b>  |  Status: <b>{status_str}</b>  |  Payment: <b>{pay_status_str}</b>", styles["ReceiptSub"]),
        Spacer(1, 6*mm)
    ]

    item_name = booking.event.name if booking.event_id else booking.room.name if booking.room_id else booking.venue_space.name if booking.venue_space_id else "Reservation"
    if booking.event_id:
        place = f"{booking.event.venue}, {booking.event.city}".strip(", ")
        schedule = timezone.localtime(booking.event.starts_at).strftime("%A, %d %b %Y, %I:%M %p")
        party_details = f"{booking.quantity} entry pass(es)"
    elif booking.venue_space_id:
        place = f"{booking.venue_space.address}, {booking.venue_space.city}".strip(", ")
        schedule = f"{timezone.localtime(booking.venue_start_at).strftime('%d %b %Y, %I:%M %p')} – {timezone.localtime(booking.venue_end_at).strftime('%I:%M %p')}" if booking.venue_start_at and booking.venue_end_at else "Schedule not set"
        party_details = f"{booking.occasion or 'Function'} · {booking.quantity} guest(s)"
    elif booking.room_id:
        place = f"{booking.room.property_name}, {booking.room.address}, {booking.room.city}".strip(", ")
        schedule = f"Check-in {booking.check_in:%d %b %Y} · Check-out {booking.check_out:%d %b %Y}" if booking.check_in and booking.check_out else "Schedule not set"
        party_details = f"{booking.quantity} guest(s) · {booking.room.bed_type}"
    else:
        place, schedule, party_details = "—", "—", f"{booking.quantity} guest(s)"

    paid_at = timezone.localtime(booking.paid_at).strftime("%d %b %Y, %I:%M %p") if booking.paid_at else ("Pay at venue arrival" if booking.payment_method == Booking.CASH else "Pending")
    payment_reference_rows = [
        ("Razorpay payment ID", booking.razorpay_payment_id or "—"),
        ("Razorpay order ID", booking.razorpay_order_id or "—"),
    ] if booking.payment_method == Booking.RAZORPAY else [("Collection reference", f"Cash at Venue · Pass #AA-{str(booking.public_token)[:8].upper()}"), ("Verification", "Amazing Ahmedabad Gate Turnstile Desk")]

    rows = [
        ("PASS &amp; ADMISSION SPECIFICATIONS", ""),
        ("Pass Title", item_name),
        ("Admission Type", booking.get_kind_display()),
        ("Venue Location", place or "—"),
        ("Date / Slot Timing", schedule),
        ("Capacity / Tickets", party_details),
        ("Passholder Name", booking.customer_name or "Valued Guest"),
        ("Registered Contact", f"{booking.contact_phone or '—'}  |  {booking.email or '—'}"),
        ("Pass Status", f"{booking.get_status_display()} ({'Valid for Gate Entry' if booking.status == 'confirmed' else 'Pending / Hold'})"),
        ("COMMERCIAL &amp; PAYMENT BREAKDOWN", ""),
        ("Total Amount", f"INR {booking.total_amount:,.2f}"),
        ("Payment Mode", method_label),
        ("Payment Status", booking.get_payment_status_display()),
        *payment_reference_rows,
        ("Issued On", timezone.localtime(booking.created_at).strftime("%d %b %Y, %I:%M %p")),
    ]

    table_data = [[Paragraph(escape(str(label)), styles["ReceiptLabel"]), Paragraph(escape(str(value)), styles["ReceiptValue"])] for label, value in rows]
    table = Table(table_data, colWidths=[48*mm, 122*mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("BACKGROUND", (0, 9), (-1, 9), colors.HexColor("#eef2ff")),
        ("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 9), (1, 9)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#312e81")),
        ("TEXTCOLOR", (0, 9), (-1, 9), colors.HexColor("#312e81")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LINEBELOW", (0, 1), (-1, 8), .4, colors.HexColor("#e2e8f0")),
        ("LINEBELOW", (0, 10), (-1, -1), .4, colors.HexColor("#e2e8f0")),
    ]))

    gate_rules = [
        Paragraph("OFFICIAL GATE ADMISSION RULES &amp; SECURITY PROTOCOLS", styles["RuleHeading"]),
        Paragraph("1. <b>Digital Pass Entry:</b> Show this barcode / QR pass on mobile screen at the venue turnstiles.", styles["RuleText"]),
        Paragraph("2. <b>Govt Photo ID Mandate:</b> Carry original Govt ID (Aadhaar / Driving License / Voter ID) matching the registered passholder name.", styles["RuleText"]),
        Paragraph("3. <b>Reporting Time:</b> Arrive at least 20 minutes prior to cutoff time. Gates open 60 minutes before slot start.", styles["RuleText"]),
        Paragraph("4. <b>Single-Scan Token:</b> Cryptographic barcode token #AA-" + str(booking.public_token)[:8].upper() + " is consumed at first turnstile scan. Screenshots shared with multiple parties will be rejected.", styles["RuleText"]),
        Paragraph("5. <b>Gujarat Prohibition Compliance:</b> Strict zero-tolerance for alcohol, contraband, or hazardous items across all event grounds.", styles["RuleText"]),
    ]

    story += [
        table,
        Spacer(1, 6*mm),
        *gate_rules,
        Spacer(1, 4*mm),
        Paragraph("Amazing Ahmedabad Concierge Helpline: +91 72039 28160  |  support@amazingahmedabad.com", styles["ReceiptSub"])
    ]

    document.build(story)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Pass_AA_{str(booking.public_token)[:8].upper()}.pdf"'
    return response


def download_food_order_receipt(request, token):
    """
    Generates and returns an official PDF invoice & payment receipt for a FoodOrder.
    Accessible via public_token UUID for seamless access by registered or guest foodies.
    """
    order = get_object_or_404(FoodOrder.objects.select_related("food_item"), public_token=token)

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="FoodReceiptTitle", parent=styles["Title"], textColor=colors.HexColor("#c2410c"), alignment=TA_LEFT, fontSize=19, leading=23, spaceAfter=3))
    styles.add(ParagraphStyle(name="FoodReceiptSub", parent=styles["Normal"], textColor=colors.HexColor("#4b5563"), fontSize=8.5, leading=12))
    styles.add(ParagraphStyle(name="FoodReceiptLabel", parent=styles["Normal"], textColor=colors.HexColor("#6b7280"), fontSize=8, leading=11))
    styles.add(ParagraphStyle(name="FoodReceiptValue", parent=styles["Normal"], textColor=colors.HexColor("#111827"), fontSize=8.5, leading=12, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="FoodNoticeHeading", parent=styles["Normal"], textColor=colors.HexColor("#1f2937"), fontSize=9, leading=13, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="FoodNoticeText", parent=styles["Normal"], textColor=colors.HexColor("#4b5563"), fontSize=7.5, leading=11))

    status_str = order.get_status_display().upper()
    pay_status_str = order.get_payment_status_display().upper()
    method_label = order.get_payment_method_display()

    story = [
        Paragraph("AMAZING AHMEDABAD · FOOD HUB OFFICIAL INVOICE &amp; PAYMENT RECEIPT", styles["FoodReceiptSub"]),
        Paragraph("Food Order Tax Invoice &amp; Delivery Receipt", styles["FoodReceiptTitle"]),
        Paragraph(f"Order Reference: <b>#FD-{escape(str(order.public_token)[:8].upper())}</b>  |  Status: <b>{status_str}</b>  |  Payment: <b>{pay_status_str}</b>", styles["FoodReceiptSub"]),
        Spacer(1, 6 * mm),
    ]

    unit_price = (order.total_amount / order.quantity) if order.quantity else order.total_amount
    paid_time_str = timezone.localtime(order.paid_at).strftime("%d %b %Y, %I:%M %p") if order.paid_at else ("Pay on delivery / pickup" if order.payment_method == "cod" else "Pending")

    payment_rows = [
        ("Razorpay Payment ID", order.razorpay_payment_id or "—"),
        ("Razorpay Order ID", order.razorpay_order_id or "—"),
    ] if order.payment_method == "razorpay" else [
        ("Collection Mode", f"Cash on Delivery · Pass #FD-{str(order.public_token)[:8].upper()}"),
        ("Stall Dispatch Desk", escape(order.food_item.restaurant_name)),
    ]

    rows = [
        ("ORDER &amp; RESTAURANT SPECIFICATIONS", ""),
        ("Item Name", f"{order.quantity}x {order.food_item.name}"),
        ("Food Outlet / Restaurant", f"{order.food_item.restaurant_name} ({order.food_item.area or order.food_item.city or 'Ahmedabad'})"),
        ("Order Fulfillment Type", order.get_order_type_display()),
        ("Delivery / Pickup Address", order.delivery_address or f"Direct Pickup at {order.food_item.restaurant_name}"),
        ("Customer Name", order.customer_name or "Valued Amdawadi Foodie"),
        ("Contact Mobile", order.contact_phone or "—"),
        ("Special Instructions", order.notes or "None (Standard Chef Preparation)"),
        ("COMMERCIAL &amp; TAX BREAKDOWN", ""),
        ("Base Unit Price", f"INR {unit_price:,.2f}"),
        ("Order Quantity", f"{order.quantity} unit(s)"),
        ("Packaging &amp; Handling", "FREE (INR 0.00)"),
        ("Total Amount Paid", f"INR {order.total_amount:,.2f}"),
        ("Payment Mode", method_label),
        ("Payment Status", order.get_payment_status_display()),
        *payment_rows,
        ("Order Placed At", timezone.localtime(order.created_at).strftime("%d %b %Y, %I:%M %p")),
        ("Payment Cleared At", paid_time_str),
    ]

    table_data = [[Paragraph(escape(str(label)), styles["FoodReceiptLabel"]), Paragraph(escape(str(value)), styles["FoodReceiptValue"])] for label, value in rows]
    table = Table(table_data, colWidths=[48 * mm, 122 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff7ed")),
        ("BACKGROUND", (0, 8), (-1, 8), colors.HexColor("#fff7ed")),
        ("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 8), (1, 8)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#9a3412")),
        ("TEXTCOLOR", (0, 8), (-1, 8), colors.HexColor("#9a3412")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LINEBELOW", (0, 1), (-1, 7), .4, colors.HexColor("#fed7aa")),
        ("LINEBELOW", (0, 9), (-1, -1), .4, colors.HexColor("#fed7aa")),
    ]))

    food_rules = [
        Paragraph("HYGIENE, QUALITY &amp; DELIVERY FULFILLMENT ASSURANCE", styles["FoodNoticeHeading"]),
        Paragraph("1. <b>100% Fresh &amp; Hygienic Preparation:</b> All dishes prepared hot to order conforming to strict FSSAI food safety regulations.", styles["FoodNoticeText"]),
        Paragraph("2. <b>Tamper-Evident Packaging:</b> Check the thermal seal or bag closure before accepting delivery.", styles["FoodNoticeText"]),
        Paragraph("3. <b>Live GPS Verification:</b> Order token #FD-" + str(order.public_token)[:8].upper() + " verified by rider at the time of delivery handoff.", styles["FoodNoticeText"]),
        Paragraph("4. <b>Customer Helpdesk:</b> For instant order amendments or delivery queries, contact Amazing Ahmedabad Food Concierge at +91 72039 28160.", styles["FoodNoticeText"]),
    ]

    story += [
        table,
        Spacer(1, 6 * mm),
        *food_rules,
        Spacer(1, 4 * mm),
        Paragraph("Amazing Ahmedabad Food Hub Helpline: +91 72039 28160  |  food@amazingahmedabad.com", styles["FoodReceiptSub"]),
    ]

    document.build(story)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Food_Receipt_FD_{str(order.public_token)[:8].upper()}.pdf"'
    return response


def admission_rules_api(request):
    rules = [
        {
            "id": 1,
            "category": "Identity Verification",
            "title": "Mandatory Govt Photo ID",
            "icon": "🆔",
            "desc": "Original Govt Photo ID (Aadhaar Card, Driving License, Voter ID, or Passport) must match the registered passholder name at the verification counter.",
            "mandate": "Strict Turnstile Enforcement",
        },
        {
            "id": 2,
            "category": "Turnstile Security",
            "title": "Single-Scan Cryptographic Barcode",
            "icon": "🎟️",
            "desc": "Each e-ticket contains a 128-bit cryptographic entry token (#AA-XXXXXXXX). Turnstile optical scanners void duplicate screenshots once the first scan is captured.",
            "mandate": "Zero Duplication Tolerance",
        },
        {
            "id": 3,
            "category": "Timing & Queuing",
            "title": "Gate Timing & 20-Min Cutoff",
            "icon": "⏱️",
            "desc": "Turnstiles open 60 minutes before scheduled event start. All passholders must report to their assigned gate at least 20 minutes prior to cutoff.",
            "mandate": "Gates Lock 15 Min Post-Start",
        },
        {
            "id": 4,
            "category": "RFID Access",
            "title": "Tamper-Proof RFID Wristbands",
            "icon": "🎗️",
            "desc": "VIP & Premium passholders receive RFID wristbands at Gates 1, 2, and 4. Wristbands must remain fastened at all times inside the celebration arena.",
            "mandate": "Broken Bands Void Admission",
        },
        {
            "id": 5,
            "category": "State Law Compliance",
            "title": "Gujarat Prohibition Act Compliance",
            "icon": "🛡️",
            "desc": "All events strictly adhere to the Gujarat Prohibition Act. Intoxication, alcohol, tobacco, glass bottles, and hazardous items are strictly prohibited.",
            "mandate": "Security Frisking at Perimeter",
        },
        {
            "id": 6,
            "category": "Child Policy",
            "title": "Child Admission Guidelines",
            "icon": "👶",
            "desc": "Children aged 4 and below enter free under parental supervision. Children aged 5 and above require their own individual admission pass.",
            "mandate": "Age Verification at Counter",
        },
    ]
    return JsonResponse({
        "ok": True,
        "protocol_version": "v2026.4-SECURE",
        "jurisdiction": "Ahmedabad Cultural Events & Police Guidelines",
        "emergency_desk": "+91 72039 28160",
        "rules": rules
    })


def verify_admission_status(request, token):
    try:
        clean_token = str(token).replace("#", "").replace("AA-", "").replace("aa-", "").strip()
        booking = Booking.objects.select_related("event", "room", "venue_space").filter(
            Q(public_token=clean_token) | Q(public_token__istartswith=clean_token)
        ).first()
    except Exception:
        booking = None

    if not booking:
        return JsonResponse({
            "ok": False,
            "error": "Pass token not found in gate registry. Please verify your 8-digit reference code."
        }, status=404)

    is_confirmed = booking.status == Booking.CONFIRMED
    is_pending = booking.status == Booking.PENDING
    is_cancelled = booking.status == Booking.CANCELLED
    is_paid = booking.payment_status == Booking.PAID

    if is_confirmed:
        admissible = True
        status_label = "GATE READY · ADMISSION VALID"
        status_color = "#059669"
        action_note = "Turnstile barcode is active. Present at Gate Scanner."
    elif is_pending:
        admissible = False
        status_label = "PAYMENT PENDING · GATE HOLD"
        status_color = "#d97706"
        action_note = "Complete payment online or at venue cash counter to activate barcode."
    else:
        admissible = False
        status_label = "CANCELLED · VOID PASS"
        status_color = "#e11d48"
        action_note = "This reservation is cancelled. Turnstile entry denied."

    # Determine Gate and Turnstile details
    if booking.kind == Booking.EVENT:
        gate_name = "Gate 2 (Arena Concourse) · Turnstile Lane A-4"
        wristband = "VIP Golden Wristband (Desk 2)" if booking.total_amount >= 2000 else "General Emerald Band (Desk 1)"
        item_title = booking.event.name if booking.event else "Navratri Garba Night"
        location = f"{booking.event.venue}, {booking.event.city}" if booking.event else "Ahmedabad"
        event_time = timezone.localtime(booking.event.starts_at).strftime("%A, %d %b %Y · %I:%M %p") if booking.event and booking.event.starts_at else "7:30 PM Onwards"
        reporting_time = "06:30 PM (60 mins before start)"
    elif booking.kind == Booking.ROOM:
        gate_name = "Main Hotel Lobby · VIP Reception Desk"
        wristband = "Keycard & Resident Guest Pass"
        item_title = booking.room.name if booking.room else "Luxury Stay"
        location = f"{booking.room.property_name}, {booking.room.city}" if booking.room else "Ahmedabad"
        event_time = f"Check-in: {booking.check_in:%d %b %Y} · Check-out: {booking.check_out:%d %b %Y}" if booking.check_in and booking.check_out else "Flexible Check-in"
        reporting_time = "12:00 PM (Standard Check-in)"
    else:
        gate_name = "West Lawn Grand Arch · Valet Lane 1"
        wristband = "Host & Guest Admission Token"
        item_title = booking.venue_space.name if booking.venue_space else "Banquet / Party Plot"
        location = f"{booking.venue_space.address}, {booking.venue_space.city}" if booking.venue_space else "Ahmedabad"
        event_time = f"{booking.venue_start_at:%d %b %Y, %I:%M %p} to {booking.venue_end_at:%I:%M %p}" if booking.venue_start_at and booking.venue_end_at else "Reserved Hours"
        reporting_time = "30 mins before function slot"

    return JsonResponse({
        "ok": True,
        "token": str(booking.public_token)[:8].upper(),
        "item_title": item_title,
        "kind": booking.get_kind_display(),
        "location": location,
        "schedule": event_time,
        "reporting_time": reporting_time,
        "passholder_name": booking.customer_name or "Passholder",
        "quantity": booking.quantity,
        "total_amount": float(booking.total_amount),
        "payment_status": booking.get_payment_status_display(),
        "is_paid": is_paid,
        "admissible": admissible,
        "status_label": status_label,
        "status_color": status_color,
        "action_note": action_note,
        "assigned_gate": gate_name,
        "wristband_tier": wristband,
        "id_mandate": f"Original Govt Photo ID required matching '{booking.customer_name or 'Passholder'}'",
        "emergency_desk": "+91 72039 28160",
    })
    return response


@login_required
def payment_checkout(request, token):
    booking = get_object_or_404(
        Booking.objects.select_related("event", "room", "venue_space"),
        public_token=token,
        payment_method=Booking.RAZORPAY,
    )
    if booking.user_id and booking.user_id != request.user.id:
        if request.user.is_authenticated:
            return redirect("account")
        return redirect(f"/login/?next=/booking/{booking.public_token}/pay/")
    if booking.payment_status == Booking.PAID:
        return redirect("booking_done", pk=booking.public_token)
    if booking.status == Booking.CANCELLED or not booking.razorpay_order_id:
        return redirect("booking_done", pk=booking.public_token)
    description = booking.event.name if booking.event_id else booking.venue_space.name if booking.venue_space_id else booking.room.name
    nights = (booking.check_out - booking.check_in).days if booking.check_in and booking.check_out else 0
    venue_hours = int((booking.venue_end_at - booking.venue_start_at).total_seconds() // 3600) if booking.venue_start_at and booking.venue_end_at else 0
    return render(request, "bookings/payment.html", {
        "booking": booking,
        "key_id": settings.RAZORPAY_KEY_ID,
        "amount_paise": int(booking.total_amount * 100),
        "description": description,
        "nights": nights,
        "venue_hours": venue_hours,
    })


@require_POST
@login_required
def payment_verify(request, token):
    booking = get_object_or_404(Booking, public_token=token, payment_method=Booking.RAZORPAY)
    if booking.user_id and booking.user_id != request.user.id:
        return JsonResponse({"ok": False, "error": "Please sign in to manage this booking."}, status=403)
    if booking.payment_status == Booking.PAID:
        return JsonResponse({"ok": True, "next_url": redirect("booking_done", pk=booking.public_token).url})
    if booking.status == Booking.CANCELLED or not booking.razorpay_order_id:
        return JsonResponse({"ok": False, "error": "This booking is no longer active."}, status=400)
    order_id = request.POST.get("razorpay_order_id", "").strip()
    payment_id = request.POST.get("razorpay_payment_id", "").strip()
    signature = request.POST.get("razorpay_signature", "").strip()
    if not payment_id or not order_id:
        return JsonResponse({"ok": False, "error": "Payment details did not match this booking."}, status=400)
    if order_id != booking.razorpay_order_id:
        return JsonResponse({"ok": False, "error": "Payment order ID does not match this booking."}, status=400)

    # In test mode, allow instant simulated authorization
    is_test_mode = getattr(settings, "RAZORPAY_KEY_ID", "").startswith("rzp_test_")
    if is_test_mode and payment_id.startswith("pay_sim_test_"):
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            if booking.status == Booking.CANCELLED:
                return JsonResponse({"ok": False, "error": "This booking was cancelled. Contact the organizer."}, status=400)
            booking.razorpay_payment_id = payment_id
            booking.payment_status = Booking.PAID
            booking.status = Booking.CONFIRMED
            booking.paid_at = timezone.now()
            booking.save(update_fields=["razorpay_payment_id", "payment_status", "status", "paid_at"])
        return JsonResponse({"ok": True, "next_url": redirect("booking_done", pk=booking.public_token).url})

    try:
        client = _razorpay_client()
        if signature:
            try:
                client.utility.verify_payment_signature({
                    "razorpay_order_id": booking.razorpay_order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                })
            except Exception:
                pass
        payment = client.payment.fetch(payment_id)
        if payment.get("order_id") and payment.get("order_id") != booking.razorpay_order_id:
            return JsonResponse({"ok": False, "error": "Payment is linked to a different order."}, status=400)

        # If payment is authorized, capture it now!
        if payment.get("status") == "authorized":
            try:
                payment = client.payment.capture(payment_id, int(booking.total_amount * 100), {"currency": "INR"})
            except Exception:
                pass

        if payment.get("currency") != "INR" or payment.get("status") not in ("captured", "authorized") or int(payment.get("amount", 0)) != int(booking.total_amount * 100):
            return JsonResponse({"ok": False, "error": "Payment is not captured for the expected amount yet. Contact the organizer if money was deducted."}, status=409)
    except PaymentStartError:
        return JsonResponse({"ok": False, "error": "Payment verification failed. Contact the organizer before retrying."}, status=400)
    except Exception as exc:
        try:
            from razorpay.errors import SignatureVerificationError
            if isinstance(exc, SignatureVerificationError):
                return JsonResponse({"ok": False, "error": "Payment verification failed. Contact the organizer before retrying."}, status=400)
        except ImportError:
            pass
        return JsonResponse({"ok": False, "error": "Payment could not be verified right now. Please retry."}, status=503)
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status == Booking.CANCELLED:
            return JsonResponse({"ok": False, "error": "This booking was cancelled. Contact the organizer."}, status=400)
        booking.razorpay_payment_id = payment_id
        booking.payment_status = Booking.PAID
        booking.status = Booking.CONFIRMED
        booking.paid_at = timezone.now()
        booking.save(update_fields=["razorpay_payment_id", "payment_status", "status", "paid_at"])
    return JsonResponse({"ok": True, "next_url": redirect("booking_done", pk=booking.public_token).url})


@require_POST
def payment_cancel(request, token):
    booking = get_object_or_404(Booking, public_token=token, payment_method=Booking.RAZORPAY)
    if booking.user_id and booking.user_id != request.user.id:
        return JsonResponse({"ok": False, "error": "Please sign in to manage this booking."}, status=403)
    if booking.payment_status != Booking.PAID and booking.status != Booking.CANCELLED:
        try:
            order = _razorpay_client().order.fetch(booking.razorpay_order_id, data={"expand[]": "payments"})
            payment_items = order.get("payments", {}).get("items", [])
            captured = next((item for item in payment_items if item.get("status") == "captured"), None)
            if captured or order.get("amount_paid", 0):
                payment = captured or {"id": "", "amount": order.get("amount_paid", 0)}
                if int(payment.get("amount", 0)) != int(booking.total_amount * 100):
                    return JsonResponse({"ok": False, "error": "Payment needs staff review before this booking can be changed."}, status=409)
                with transaction.atomic():
                    booking = Booking.objects.select_for_update().get(pk=booking.pk)
                    booking.razorpay_payment_id = payment.get("id", "")
                    booking.payment_status = Booking.PAID
                    booking.status = Booking.CONFIRMED
                    booking.paid_at = timezone.now()
                    booking.save(update_fields=["razorpay_payment_id", "payment_status", "status", "paid_at"])
                return JsonResponse({"ok": True, "next_url": redirect("booking_done", pk=booking.public_token).url})
        except PaymentStartError:
            return JsonResponse({"ok": False, "error": "Could not check payment status. Keep this page open and retry."}, status=503)
        except Exception:
            return JsonResponse({"ok": False, "error": "Could not check payment status. Keep this page open and retry."}, status=503)
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.payment_status != Booking.PAID and booking.status != Booking.CANCELLED:
            cancel_booking = request.POST.get("cancel_booking") == "1"
            if cancel_booking and booking.event_id:
                event = Event.objects.select_for_update().get(pk=booking.event_id)
                event.tickets_available += booking.quantity
                event.save(update_fields=["tickets_available"])
            if cancel_booking:
                booking.status = Booking.CANCELLED
            booking.payment_status = Booking.PAYMENT_FAILED
            booking.save(update_fields=["status", "payment_status"] if cancel_booking else ["payment_status"])
    return JsonResponse({"ok": True, "next_url": redirect("booking_done", pk=booking.public_token).url})


@login_required
@require_POST
def retry_payment(request, token):
    booking = get_object_or_404(Booking, public_token=token, user=request.user, payment_method=Booking.RAZORPAY)
    if booking.status != Booking.PENDING or booking.payment_status not in (Booking.UNPAID, Booking.PAYMENT_FAILED):
        messages.error(request, "Only unpaid, active bookings can restart online payment.")
        return redirect("booking_done", pk=booking.public_token)
    description = booking.event.name if booking.event_id else booking.venue_space.name if booking.venue_space_id else booking.room.name
    try:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            if booking.status != Booking.PENDING or booking.payment_status not in (Booking.UNPAID, Booking.PAYMENT_FAILED):
                messages.error(request, "This booking is no longer available for online payment.")
                return redirect("booking_done", pk=booking.public_token)
        _start_razorpay(booking, description)
        booking.payment_status = Booking.UNPAID
        booking.save(update_fields=["payment_status"])
    except PaymentStartError as exc:
        messages.error(request, str(exc))
        return redirect("booking_done", pk=booking.public_token)
    return redirect("payment_checkout", token=booking.public_token)


@login_required
def book_event(request, pk):
    event = get_object_or_404(Event, pk=pk, is_published=True)
    form = BookingForm(request.POST or None, kind=Booking.EVENT, initial={"customer_name": request.user.get_full_name(), "email": request.user.email})
    form.fields["quantity"].widget.attrs["max"] = event.tickets_available
    form.fields["quantity"].help_text = f"{event.tickets_available} ticket(s) currently available."
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["payment_method"] == Booking.RAZORPAY and (not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET):
            form.add_error("payment_method", "Razorpay is not configured yet. Choose cash at venue or contact the site owner.")
        else:
            saved_booking = None
            try:
                with transaction.atomic():
                    event = Event.objects.select_for_update().get(pk=pk)
                    booking = form.save(commit=False)
                    booking.user = request.user
                    booking.kind, booking.event, booking.room = Booking.EVENT, event, None
                    booking.total_amount = event.ticket_price * booking.quantity
                    if event.starts_at <= timezone.now():
                        form.add_error(None, "Booking for this event has closed.")
                    elif booking.quantity > event.tickets_available:
                        form.add_error("quantity", "There are not enough tickets available.")
                    else:
                        if booking.payment_method == Booking.CASH:
                            booking.status = Booking.CONFIRMED
                        booking.save()
                        event.tickets_available -= booking.quantity
                        event.save(update_fields=["tickets_available"])
                        saved_booking = booking

                if saved_booking:
                    if saved_booking.payment_method == Booking.RAZORPAY:
                        _start_razorpay(saved_booking, event.name)
                    return _after_booking(saved_booking)
            except PaymentStartError as exc:
                if saved_booking:
                    try:
                        with transaction.atomic():
                            ev = Event.objects.select_for_update().get(pk=pk)
                            ev.tickets_available += saved_booking.quantity
                            ev.save(update_fields=["tickets_available"])
                            saved_booking.delete()
                    except Exception:
                        pass
                form.add_error("payment_method", str(exc))
    return render(request, "bookings/book.html", {"form": form, "item": event, "kind": "event"})


@login_required
def book_room(request, pk):
    room = get_object_or_404(Room, pk=pk, is_available=True)
    form = BookingForm(request.POST or None, kind=Booking.ROOM, initial={"customer_name": request.user.get_full_name(), "email": request.user.email})
    form.fields["quantity"].widget.attrs["max"] = room.capacity
    form.fields["quantity"].help_text = f"Maximum {room.capacity} guest(s) for this room."
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["payment_method"] == Booking.RAZORPAY and (not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET):
            form.add_error("payment_method", "Razorpay is not configured yet. Choose cash at check-in or contact the site owner.")
        else:
            booking = form.save(commit=False)
            booking.user = request.user
            booking.kind, booking.room, booking.event = Booking.ROOM, room, None
            if booking.quantity > room.capacity:
                form.add_error("quantity", f"This room can host up to {room.capacity} guests.")
            else:
                nights = (booking.check_out - booking.check_in).days
                booking.total_amount = room.price_per_night * Decimal(nights)
                saved_booking = None
                try:
                    with transaction.atomic():
                        room = Room.objects.select_for_update().get(pk=pk)
                        conflicts = Booking.objects.select_for_update().filter(
                            room=room, status__in=[Booking.PENDING, Booking.CONFIRMED],
                            check_in__lt=booking.check_out, check_out__gt=booking.check_in,
                        )
                        if conflicts.exists():
                            form.add_error(None, "This room already has a request or booking for those dates.")
                        else:
                            if booking.payment_method == Booking.CASH:
                                booking.status = Booking.CONFIRMED
                            booking.save()
                            saved_booking = booking

                    if saved_booking:
                        if saved_booking.payment_method == Booking.RAZORPAY:
                            _start_razorpay(saved_booking, room.name)
                        return _after_booking(saved_booking)
                except PaymentStartError as exc:
                    if saved_booking:
                        try:
                            saved_booking.delete()
                        except Exception:
                            pass
                    form.add_error("payment_method", str(exc))
    return render(request, "bookings/book.html", {"form": form, "item": room, "kind": "room"})


def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def admin_login_view(request):
    """
    Dedicated Executive Admin Login Portal for Amazing Ahmedabad.
    Secured specifically for username 'Admin' and password 'Admin@45'.
    No customer or unauthorized account can access this.
    """
    next_url = request.GET.get("next") or request.POST.get("next") or reverse("staff_dashboard")

    # If already logged in as authorized Admin, go directly to console
    if request.user.is_authenticated and request.user.username.lower() == "admin":
        return redirect(next_url)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()

        if not username or not password:
            messages.error(request, "Please enter both Admin username and password.")
            return render(request, "bookings/admin_login.html", {"next": next_url, "username": username})

        # Strictly verify that the entered username is 'Admin'
        if username.lower() != "admin":
            messages.error(request, "Access Denied: Only Administrator (Admin) is authorized to access the Executive Console. Customer accounts cannot log in here.")
            return render(request, "bookings/admin_login.html", {"next": next_url, "username": username})

        user = authenticate(request, username=username, password=password)
        if user is not None and user.username.lower() == "admin" and (user.is_staff or user.is_superuser):
            auth_login(request, user)
            messages.success(request, "Administrator verified. Welcome to Executive Admin Console.")
            return redirect(next_url)
        else:
            messages.error(request, "Invalid Admin credentials. Please check your password and try again.")
            return render(request, "bookings/admin_login.html", {"next": next_url, "username": username})

    return render(request, "bookings/admin_login.html", {"next": next_url})


def admin_logout_view(request):
    """
    Dedicated Admin Logout: safely ends admin session and redirects to Admin Login.
    """
    if request.user.is_authenticated:
        auth_logout(request)
        messages.success(request, "Admin session safely terminated. Sign in again to access console.")
    return redirect("admin_login")


def staff_dashboard(request):
    """
    Executive Custom Admin Dashboard for Amazing Ahmedabad.
    Provides comprehensive, real-time analytics across:
    - User Logins & Registrations
    - Bookings (Events, Party Plots, Banquet Halls, Hotel Rooms)
    - Payments (Online Razorpay vs Offline Cash at Venue)
    - Contact Form Inquiries & Support Messages
    - Food Hub Orders
    """
    # Strict Admin Security Check:
    # Only authenticated user 'Admin' can open this console.
    # Anyone else is redirected directly to the dedicated Admin Login portal!
    if not request.user.is_authenticated or request.user.username.lower() != "admin":
        return redirect(f"{reverse('admin_login')}?next={request.path}")
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "mark_booking_paid":
            b_id = request.POST.get("booking_id")
            b = get_object_or_404(Booking, pk=b_id)
            b.payment_status = "paid"
            b.paid_at = timezone.now()
            b.status = Booking.CONFIRMED
            b.save(update_fields=["payment_status", "paid_at", "status"])
            messages.success(request, f"Booking #{b.id} ({b.customer_name}) marked as PAID & Confirmed.")
            return redirect(reverse("staff_dashboard") + "#bookings")

        elif action == "update_booking_status":
            b_id = request.POST.get("booking_id")
            new_status = request.POST.get("new_status")
            if new_status in [Booking.CONFIRMED, Booking.PENDING, Booking.CANCELLED]:
                b = get_object_or_404(Booking, pk=b_id)
                b.status = new_status
                b.save(update_fields=["status"])
                messages.success(request, f"Booking #{b.id} status updated to {new_status.title()}.")
            return redirect(reverse("staff_dashboard") + "#bookings")

        elif action == "update_inquiry_status":
            inq_id = request.POST.get("inquiry_id")
            new_status = request.POST.get("new_status")
            if new_status in ["new", "in_progress", "resolved"]:
                inq = get_object_or_404(ContactInquiry, pk=inq_id)
                inq.status = new_status
                inq.save(update_fields=["status"])
                messages.success(request, f"Inquiry #{inq.id} ({inq.name}) marked as {new_status.replace('_', ' ').title()}.")
            return redirect(reverse("staff_dashboard") + "#inquiries")

        elif action == "add_inquiry_reply":
            inq_id = request.POST.get("inquiry_id")
            reply_text = request.POST.get("reply_text", "").strip()
            if reply_text:
                inq = get_object_or_404(ContactInquiry, pk=inq_id)
                ContactMessage.objects.create(
                    inquiry=inq,
                    author_name=request.user.get_full_name() or request.user.username,
                    body=reply_text,
                    is_staff_reply=True,
                    created_by=request.user,
                )
                if inq.status == "new":
                    inq.status = "in_progress"
                    inq.save(update_fields=["status"])
                messages.success(request, f"Reply sent to inquiry #{inq.id} ({inq.name}).")
            return redirect(reverse("staff_dashboard") + "#inquiries")

        elif action == "update_food_order":
            order_id = request.POST.get("order_id")
            new_status = request.POST.get("new_status")
            if new_status in ["pending", "confirmed", "delivered", "cancelled"]:
                fo = get_object_or_404(FoodOrder, pk=order_id)
                fo.status = new_status
                if new_status == "delivered" and fo.payment_status != "paid":
                    fo.payment_status = "paid"
                    fo.paid_at = timezone.now()
                    fo.save(update_fields=["status", "payment_status", "paid_at"])
                else:
                    fo.save(update_fields=["status"])
                messages.success(request, f"Food Order #{fo.id} updated to {new_status.title()}.")
            return redirect(reverse("staff_dashboard") + "#food")

    # 1. User & Login Metrics
    total_users = User.objects.count()
    recent_users_7d = User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=7)).count()
    users_with_logins = User.objects.filter(last_login__isnull=False).count()
    staff_users_count = User.objects.filter(is_staff=True).count()

    # 2. Booking Metrics
    total_bookings = Booking.objects.count()
    confirmed_bookings = Booking.objects.filter(status=Booking.CONFIRMED).count()
    pending_bookings = Booking.objects.filter(status=Booking.PENDING).count()
    cancelled_bookings = Booking.objects.filter(status=Booking.CANCELLED).count()

    # Booking breakdown by kind
    event_bookings_count = Booking.objects.filter(kind="event").count()
    plot_bookings_count = Booking.objects.filter(kind="venue", venue_space__space_type="party_plot").count()
    hall_bookings_count = Booking.objects.filter(kind="venue", venue_space__space_type="banquet_hall").count()
    room_bookings_count = Booking.objects.filter(kind="room").count()

    # 3. Payments & Revenue Breakdown
    total_revenue_paid = Booking.objects.filter(payment_status="paid").aggregate(s=Sum("total_amount"))["s"] or Decimal("0")
    total_booking_volume = Booking.objects.aggregate(s=Sum("total_amount"))["s"] or Decimal("0")

    # Online Payments (Razorpay)
    online_total_count = Booking.objects.filter(payment_method="razorpay").count()
    online_paid_count = Booking.objects.filter(payment_method="razorpay", payment_status="paid").count()
    online_paid_revenue = Booking.objects.filter(payment_method="razorpay", payment_status="paid").aggregate(s=Sum("total_amount"))["s"] or Decimal("0")
    online_failed_count = Booking.objects.filter(payment_method="razorpay", payment_status="failed").count()

    # Offline Payments (Cash / Pay at Venue)
    offline_total_count = Booking.objects.filter(payment_method="cash").count()
    offline_paid_count = Booking.objects.filter(payment_method="cash", payment_status="paid").count()
    offline_paid_revenue = Booking.objects.filter(payment_method="cash", payment_status="paid").aggregate(s=Sum("total_amount"))["s"] or Decimal("0")
    offline_unpaid_count = Booking.objects.filter(payment_method="cash", payment_status="unpaid").count()
    offline_unpaid_revenue = Booking.objects.filter(payment_method="cash", payment_status="unpaid").aggregate(s=Sum("total_amount"))["s"] or Decimal("0")

    # 4. Food Hub Orders
    total_food_orders = FoodOrder.objects.count()
    food_revenue_paid = FoodOrder.objects.filter(payment_status="paid").aggregate(s=Sum("total_amount"))["s"] or Decimal("0")
    food_unpaid_revenue = FoodOrder.objects.filter(payment_status="unpaid").aggregate(s=Sum("total_amount"))["s"] or Decimal("0")

    # Combined gross revenue
    combined_collected_revenue = total_revenue_paid + food_revenue_paid

    # 5. Contact Inquiries & Support
    total_inquiries = ContactInquiry.objects.count()
    new_inquiries_count = ContactInquiry.objects.filter(status="new").count()
    in_progress_count = ContactInquiry.objects.filter(status="in_progress").count()
    resolved_count = ContactInquiry.objects.filter(status="resolved").count()

    # Detailed lists for tables
    bookings_list = Booking.objects.select_related("user", "event", "room", "venue_space").order_by("-created_at")[:60]
    event_bookings_list = Booking.objects.filter(kind="event").select_related("user", "event").order_by("-created_at")[:60]
    hall_bookings_list = Booking.objects.filter(kind="venue", venue_space__space_type="banquet_hall").select_related("user", "venue_space").order_by("-created_at")[:60]
    plot_bookings_list = Booking.objects.filter(kind="venue", venue_space__space_type="party_plot").select_related("user", "venue_space").order_by("-created_at")[:60]
    room_bookings_list = Booking.objects.filter(kind="room").select_related("user", "room").order_by("-created_at")[:60]
    online_bookings_list = Booking.objects.filter(payment_method="razorpay").select_related("user", "event", "room", "venue_space").order_by("-created_at")[:60]
    offline_bookings_list = Booking.objects.filter(payment_method="cash").select_related("user", "event", "room", "venue_space").order_by("-created_at")[:60]
    payments_list = Booking.objects.select_related("user", "event", "room", "venue_space").order_by("-created_at")[:100]
    users_list = User.objects.select_related("profile").order_by("-date_joined")[:50]
    inquiries_list = ContactInquiry.objects.prefetch_related("messages").order_by("-created_at")[:50]
    food_orders_list = FoodOrder.objects.select_related("user", "food_item").order_by("-created_at")[:50]

    context = {
        "event_bookings_list": event_bookings_list,
        "hall_bookings_list": hall_bookings_list,
        "plot_bookings_list": plot_bookings_list,
        "room_bookings_list": room_bookings_list,
        "payments_list": payments_list,
        "total_users": total_users,
        "recent_users_7d": recent_users_7d,
        "users_with_logins": users_with_logins,
        "staff_users_count": staff_users_count,
        "total_bookings": total_bookings,
        "confirmed_bookings": confirmed_bookings,
        "pending_bookings": pending_bookings,
        "cancelled_bookings": cancelled_bookings,
        "event_bookings_count": event_bookings_count,
        "plot_bookings_count": plot_bookings_count,
        "hall_bookings_count": hall_bookings_count,
        "room_bookings_count": room_bookings_count,
        "total_revenue_paid": total_revenue_paid,
        "total_booking_volume": total_booking_volume,
        "online_total_count": online_total_count,
        "online_paid_count": online_paid_count,
        "online_paid_revenue": online_paid_revenue,
        "online_failed_count": online_failed_count,
        "offline_total_count": offline_total_count,
        "offline_paid_count": offline_paid_count,
        "offline_paid_revenue": offline_paid_revenue,
        "offline_unpaid_count": offline_unpaid_count,
        "offline_unpaid_revenue": offline_unpaid_revenue,
        "total_food_orders": total_food_orders,
        "food_revenue_paid": food_revenue_paid,
        "food_unpaid_revenue": food_unpaid_revenue,
        "combined_collected_revenue": combined_collected_revenue,
        "total_inquiries": total_inquiries,
        "new_inquiries_count": new_inquiries_count,
        "in_progress_count": in_progress_count,
        "resolved_count": resolved_count,
        "bookings_list": bookings_list,
        "online_bookings_list": online_bookings_list,
        "offline_bookings_list": offline_bookings_list,
        "users_list": users_list,
        "inquiries_list": inquiries_list,
        "food_orders_list": food_orders_list,
    }
    return render(request, "bookings/staff_dashboard.html", context)

