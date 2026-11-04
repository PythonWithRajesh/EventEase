from decimal import Decimal
from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from .forms import BookingForm, ContactInquiryForm, VenueBookingForm
from .models import Booking, ContactInquiry, ContactMessage, Event, Room, VenueSpace
from .views import _start_razorpay


class RazorpayFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="razorpay-test-user", password="test-password")
        self.client.force_login(self.user)
        self.event = Event.objects.create(
            name="Test Navratri", venue="Test Ground", starts_at=timezone.now() + timedelta(days=4),
            ticket_price=Decimal("1250.50"), tickets_available=20,
        )
        self.booking = Booking.objects.create(
            kind=Booking.EVENT,
            user=self.user,
            event=self.event,
            customer_name="Test Guest",
            email="guest@example.com",
            contact_phone="+919876543210",
            payment_method=Booking.RAZORPAY,
            payment_status=Booking.UNPAID,
            total_amount=Decimal("1250.50"),
            razorpay_order_id="order_test_123",
        )

    @patch("bookings.views._razorpay_client")
    def test_creates_inr_order_in_paise_and_saves_order_id(self, client_factory):
        gateway = Mock()
        gateway.order.create.return_value = {
            "id": "order_test_456", "amount": 125050, "currency": "INR",
        }
        client_factory.return_value = gateway

        _start_razorpay(self.booking, "Navratri night")

        payload = gateway.order.create.call_args.args[0]
        self.assertEqual(payload["amount"], 125050)
        self.assertEqual(payload["currency"], "INR")
        self.assertEqual(len(payload["receipt"]), 40)
        self.assertEqual(payload["notes"]["booking_token"], str(self.booking.public_token))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.razorpay_order_id, "order_test_456")

    @patch("bookings.views._razorpay_client")
    def test_valid_signed_captured_payment_confirms_booking(self, client_factory):
        gateway = Mock()
        gateway.payment.fetch.return_value = {
            "id": "pay_test_123", "order_id": "order_test_123", "status": "captured",
            "amount": 125050, "currency": "INR",
        }
        client_factory.return_value = gateway

        response = self.client.post(reverse("payment_verify", args=[self.booking.public_token]), {
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": "valid-test-signature",
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, Booking.PAID)
        self.assertEqual(self.booking.status, Booking.CONFIRMED)
        self.assertEqual(self.booking.razorpay_payment_id, "pay_test_123")
        self.assertIsNotNone(self.booking.paid_at)
        gateway.utility.verify_payment_signature.assert_called_once()

    @patch("bookings.views._razorpay_client")
    def test_uncaptured_or_wrong_amount_payment_is_not_marked_paid(self, client_factory):
        gateway = Mock()
        gateway.payment.fetch.return_value = {
            "id": "pay_test_123", "order_id": "order_test_123", "status": "captured",
            "amount": 125049, "currency": "INR",
        }
        client_factory.return_value = gateway

        response = self.client.post(reverse("payment_verify", args=[self.booking.public_token]), {
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": "valid-test-signature",
        })

        self.assertEqual(response.status_code, 409)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, Booking.UNPAID)
        self.assertEqual(self.booking.status, Booking.PENDING)
        self.assertIsNone(self.booking.paid_at)

    @patch("bookings.views._razorpay_client")
    def test_dismissed_checkout_keeps_booking_pending_and_retry_creates_new_order(self, client_factory):
        gateway = Mock()
        gateway.order.fetch.return_value = {"payments": {"items": []}, "amount_paid": 0}
        gateway.order.create.return_value = {"id": "order_retry_456", "amount": 125050, "currency": "INR"}
        client_factory.return_value = gateway

        cancelled_response = self.client.post(reverse("payment_cancel", args=[self.booking.public_token]))
        self.assertEqual(cancelled_response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.PENDING)
        self.assertEqual(self.booking.payment_status, Booking.PAYMENT_FAILED)

        retry_response = self.client.post(reverse("retry_payment", args=[self.booking.public_token]))
        self.assertRedirects(retry_response, reverse("payment_checkout", args=[self.booking.public_token]), fetch_redirect_response=False)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.razorpay_order_id, "order_retry_456")
        self.assertEqual(self.booking.payment_status, Booking.UNPAID)

    def test_checkout_requires_an_order_matching_the_booking(self):
        response = self.client.post(reverse("payment_verify", args=[self.booking.public_token]), {
            "razorpay_order_id": "order_someone_elses",
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": "forged",
        })

        self.assertEqual(response.status_code, 400)

    def test_pdf_receipt_download_is_only_available_after_online_payment(self):
        pending = self.client.get(reverse("booking_receipt_pdf", args=[self.booking.public_token]))
        self.assertRedirects(pending, reverse("booking_done", args=[self.booking.public_token]), fetch_redirect_response=False)

        self.booking.payment_status = Booking.PAID
        self.booking.razorpay_payment_id = "pay_pdf_test"
        self.booking.paid_at = timezone.now()
        self.booking.save(update_fields=["payment_status", "razorpay_payment_id", "paid_at"])
        response = self.client.get(reverse("booking_receipt_pdf", args=[self.booking.public_token]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))


class ContactPageTests(TestCase):
    def test_contact_page_renders_essential_contact_form(self):
        response = self.client.get(reverse("contact"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send a message")
        self.assertContains(response, "Country / calling code")
        self.assertNotContains(response, "Helpful answers")

    def test_contact_page_accepts_and_saves_valid_inquiry(self):
        response = self.client.post(reverse("contact"), {
            "name": "Asha Patel", "email": "asha@example.com", "phone": "9876543210", "phone_country": "IN",
            "topic": "booking", "subject": "Need help with booking", "message": "Please help me find my reservation.",
            "website": "",
        })
        self.assertRedirects(response, reverse("contact"))
        inquiry = ContactInquiry.objects.get()
        self.assertEqual(inquiry.name, "Asha Patel")
        self.assertEqual(inquiry.phone, "+919876543210")
        self.assertEqual(inquiry.status, "new")
        self.assertTrue(inquiry.messages.filter(body=inquiry.message, is_staff_reply=False).exists())

    def test_contact_form_rejects_honeypot_submission(self):
        response = self.client.post(reverse("contact"), {
            "name": "Spam", "email": "spam@example.com", "topic": "other",
            "subject": "Spam", "message": "Spam message", "website": "spam.example",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContactInquiry.objects.exists())

    def test_contact_phone_is_optional_and_country_aware_when_given(self):
        data = {"name": "Asha", "email": "asha@example.com", "phone": "987654321", "phone_country": "IN", "topic": "other", "subject": "Question", "message": "Hello"}
        self.assertFalse(ContactInquiryForm(data).is_valid())
        data["phone"] = ""
        self.assertTrue(ContactInquiryForm(data).is_valid())


class MobileNumberValidationTests(TestCase):
    def test_standard_booking_accepts_numbers_from_selected_countries(self):
        data = {"customer_name": "Guest", "email": "guest@example.com", "contact_phone": "9876543210", "phone_country": "IN", "quantity": "2", "payment_method": Booking.CASH}
        form = BookingForm(data=data, kind=Booking.EVENT)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["contact_phone"], "+919876543210")
        data.update(contact_phone="2025550125", phone_country="US")
        form = BookingForm(data=data, kind=Booking.EVENT)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["contact_phone"], "+12025550125")
        data.update(contact_phone="123", phone_country="US")
        self.assertFalse(BookingForm(data=data, kind=Booking.EVENT).is_valid())
        data.update(contact_phone="202-555-0125", phone_country="US")
        self.assertFalse(BookingForm(data=data, kind=Booking.EVENT).is_valid())

    def test_party_plot_booking_rejects_invalid_mobile_length(self):
        venue = VenueSpace.objects.create(name="Test Plot", space_type=VenueSpace.PARTY_PLOT, hourly_rate=Decimal("1000.00"))
        data = {
            "customer_name": "Guest", "email": "guest@example.com", "contact_phone": "98765432101", "phone_country": "IN",
            "occasion": "Birthday party", "reservation_date": (timezone.localdate() + timedelta(days=1)).isoformat(),
            "start_time": "18:00", "duration_hours": "2", "quantity": "40", "payment_method": Booking.CASH,
        }
        self.assertFalse(VenueBookingForm(data=data, venue=venue).is_valid())
class HomePageTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(
            name="Navratri Dhol Night",
            category="Navratri",
            venue="Riverfront Grounds",
            city="Ahmedabad",
            address="Riverfront, Ahmedabad",
            ticket_price=Decimal("499.00"),
            tickets_available=50,
            starts_at=timezone.now() + timedelta(days=2),
            is_published=True,
        )
        self.party_plot = VenueSpace.objects.create(
            name="Bopal Celebration Plot",
            space_type=VenueSpace.PARTY_PLOT,
            city="Ahmedabad",
            address="Bopal, Ahmedabad",
            hourly_rate=Decimal("5000.00"),
            capacity=300,
            is_available=True,
        )
        self.wedding_hall = VenueSpace.objects.create(
            name="Grand Satellite Banquet",
            space_type=VenueSpace.BANQUET_HALL,
            city="Ahmedabad",
            address="Satellite, Ahmedabad",
            hourly_rate=Decimal("15000.00"),
            capacity=800,
            is_available=True,
        )
        self.room = Room.objects.create(
            name="Deluxe Comfort Suite",
            room_type="Deluxe Room",
            property_name="Ahmedabad Grand Hotel",
            city="Ahmedabad",
            address="Navrangpura, Ahmedabad",
            price_per_night=Decimal("2500.00"),
            capacity=2,
            is_available=True,
        )

    def test_home_page_loads_and_displays_all_sections(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Navratri Dhol Night")
        self.assertContains(response, "Bopal Celebration Plot")
        self.assertContains(response, "Grand Satellite Banquet")
        self.assertContains(response, "Deluxe Comfort Suite")
        self.assertContains(response, "Where Ahmedabad Celebrates")
        self.assertContains(response, "Party Plots &amp; Celebration Lawns")
        self.assertContains(response, "Wedding &amp; Banquet Halls")

    def test_home_page_search_by_query(self):
        response = self.client.get(reverse("home") + "?q=Bopal")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bopal Celebration Plot")
        self.assertNotContains(response, "Grand Satellite Banquet")

    def test_home_page_filter_by_category(self):
        response = self.client.get(reverse("home") + "?category=Navratri")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Navratri Dhol Night")

    def test_home_page_filter_by_type(self):
        response = self.client.get(reverse("home") + "?type=party_plots")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bopal Celebration Plot")
        self.assertEqual(response.context["listing_type"], "party_plots")

    def test_home_page_sort_by_price(self):
        response = self.client.get(reverse("home") + "?sort=price_asc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sort_by"], "price_asc")
