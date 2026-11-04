from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Booking, Event


def update_booking_financial_status(booking_id, status, payment_status):
    """Update a booking state and keep event ticket inventory in sync."""
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)
        previous_status = booking.status
        if booking.kind == Booking.EVENT and booking.event_id and previous_status != status:
            event = Event.objects.select_for_update().get(pk=booking.event_id)
            if status == Booking.CANCELLED and previous_status != Booking.CANCELLED:
                if payment_status == Booking.PAID:
                    raise ValidationError("Record a refund before cancelling a paid booking.")
                event.tickets_available += booking.quantity
                event.save(update_fields=("tickets_available",))
            elif previous_status == Booking.CANCELLED and status != Booking.CANCELLED:
                if booking.quantity > event.tickets_available:
                    raise ValidationError("Not enough tickets remain to reactivate this booking.")
                event.tickets_available -= booking.quantity
                event.save(update_fields=("tickets_available",))
        booking.status = status
        booking.payment_status = payment_status
        if payment_status == Booking.PAID and not booking.paid_at:
            booking.paid_at = timezone.now()
        elif payment_status in (Booking.UNPAID, Booking.PAYMENT_FAILED):
            booking.paid_at = None
        booking.save(update_fields=("status", "payment_status", "paid_at"))
        return booking
