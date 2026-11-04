from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking, ContactInquiry, ContactMessage, Event


class CustomAdminReportPDFTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(username="report-staff", password="test", is_staff=True)
        self.client.force_login(self.staff)
        event = Event.objects.create(
            name="Test Celebration", venue="Test Venue", starts_at=timezone.now() + timedelta(days=4),
            ticket_price=Decimal("500.00"), tickets_available=12,
        )
        Booking.objects.create(
            kind=Booking.EVENT, event=event, user=self.staff, customer_name="Report Guest",
            email="report@example.com", total_amount=Decimal("500.00"),
        )

    def test_reports_page_offers_pdf_and_csv_downloads(self):
        response = self.client.get(reverse("dashboard_reports"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Download PDF")
        self.assertContains(response, "CSV")

    def test_reports_pdf_download_is_a_valid_pdf_response(self):
        response = self.client.get(reverse("dashboard_reports_pdf"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_reports_pdf_requires_staff_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard_reports_pdf"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/custom_admin/login/", response["Location"])


class PaymentLedgerTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(username="payment-staff", password="test", is_staff=True)
        self.client.force_login(self.staff)
        event = Event.objects.create(
            name="Payment test event", venue="Payment venue", starts_at=timezone.now() + timedelta(days=3),
            ticket_price=Decimal("600.00"), tickets_available=20,
        )
        self.cash_booking = Booking.objects.create(
            kind=Booking.EVENT, event=event, customer_name="Cash Guest", email="cash@example.com",
            status=Booking.CONFIRMED, payment_method=Booking.CASH, payment_status=Booking.UNPAID,
            total_amount=Decimal("600.00"),
        )
        self.online_booking = Booking.objects.create(
            kind=Booking.EVENT, event=event, customer_name="Online Guest", email="online@example.com",
            status=Booking.PENDING, payment_method=Booking.RAZORPAY, payment_status=Booking.UNPAID,
            total_amount=Decimal("600.00"), razorpay_order_id="order_pending_test",
        )

    def test_payment_ledger_separates_methods_and_records_cash_as_paid(self):
        response = self.client.get(reverse("dashboard_payments"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Online received")
        self.assertContains(response, "Cash to collect")
        self.assertContains(response, self.cash_booking.customer_name)
        self.assertContains(response, self.online_booking.razorpay_order_id)

        response = self.client.post(reverse("dashboard_record_cash_payment", args=[self.cash_booking.pk]))
        self.assertRedirects(response, reverse("dashboard_payments"))
        self.cash_booking.refresh_from_db()
        self.assertEqual(self.cash_booking.payment_status, Booking.PAID)
        self.assertIsNotNone(self.cash_booking.paid_at)
        receipt = self.client.get(reverse("dashboard_payment_receipt", args=[self.cash_booking.pk]))
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, "Cash payment recorded")
        pdf = self.client.get(reverse("booking_receipt_pdf", args=[self.cash_booking.public_token]))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_admin_cannot_mark_an_online_payment_paid_without_gateway_verification(self):
        response = self.client.post(reverse("dashboard_record_cash_payment", args=[self.online_booking.pk]))
        self.assertRedirects(response, reverse("dashboard_payments"))
        self.online_booking.refresh_from_db()
        self.assertEqual(self.online_booking.payment_status, Booking.UNPAID)


class ContactInboxTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(username="contact-staff", password="test", is_staff=True)
        self.client.force_login(self.staff)
        self.inquiry = ContactInquiry.objects.create(
            name="Guest Name", email="guest@example.com", topic="payment",
            subject="Question about payment", message="I need help with my online payment.",
        )

    def test_staff_can_open_inbox_and_update_inquiry_status(self):
        response = self.client.get(reverse("dashboard_contact_inbox"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Question about payment")
        response = self.client.post(reverse("dashboard_contact_detail", args=[self.inquiry.pk]), {
            "action": "save_details", "name": "Updated Guest", "email": "guest@example.com",
            "phone": "9876543210", "phone_country": "IN", "topic": "payment",
            "subject": "Payment question updated", "status": "in_progress",
        })
        self.assertRedirects(response, reverse("dashboard_contact_detail", args=[self.inquiry.pk]))
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, "in_progress")
        self.assertEqual(self.inquiry.name, "Updated Guest")
        self.assertEqual(self.inquiry.phone, "+919876543210")
        self.assertEqual(self.inquiry.subject, "Payment question updated")

    def test_staff_can_add_a_conversation_message_and_create_an_inquiry(self):
        response = self.client.post(reverse("dashboard_contact_detail", args=[self.inquiry.pk]), {
            "action": "add_message", "body": "We have checked this payment for you.",
        })
        self.assertRedirects(response, reverse("dashboard_contact_detail", args=[self.inquiry.pk]))
        self.assertTrue(self.inquiry.messages.filter(is_staff_reply=True, body="We have checked this payment for you.").exists())

        response = self.client.post(reverse("dashboard_contact_create"), {
            "name": "Phone Guest", "email": "phone@example.com", "phone_country": "IN",
            "phone": "9876543210", "topic": "booking", "subject": "New booking question",
            "message": "Please help with my reservation.",
        })
        self.assertEqual(response.status_code, 302)
        created = ContactInquiry.objects.get(subject="New booking question")
        self.assertEqual(created.phone, "+919876543210")
        self.assertEqual(created.messages.count(), 1)
        self.assertContains(self.client.get(reverse("dashboard_contact_detail", args=[created.pk])), "Please help with my reservation.")

    def test_contact_inbox_requires_staff_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard_contact_inbox"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/custom_admin/login/", response["Location"])
