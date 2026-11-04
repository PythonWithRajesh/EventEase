from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    Booking,
    ContactInquiry,
    ContactMessage,
    Event,
    FoodItem,
    FoodOrder,
    Room,
    UserProfile,
    VenueSpace,
)


# ─── Admin Site Configuration ───────────────────────────────────────────────

admin.site.site_header = "🏆 Amazing Ahmedabad · Admin"
admin.site.site_title = "Amazing Ahmedabad Admin"
admin.site.index_title = (
    "Manage Navratri Events, Luxury Rooms, Party Plots, "
    "Wedding Halls & Bookings"
)
admin.site.site_url = "/"


# ─── Event Admin ────────────────────────────────────────────────────────────

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "category",
        "starts_at",
        "city",
        "venue",
        "ticket_price_display",
        "tickets_available",
        "published_badge",
        "is_published",
    )

    list_filter = ("category", "is_published", "city")

    search_fields = (
        "name",
        "venue",
        "city",
        "organizer_name",
    )

    list_editable = ("is_published",)
    ordering = ("starts_at",)
    date_hierarchy = "starts_at"

    readonly_fields = ("cover_image_preview",)

    fieldsets = (
        (
            "Event Details",
            {
                "fields": (
                    "name",
                    "category",
                    "organizer_name",
                    "contact_phone",
                    "description",
                    "cover_image_url",
                    "cover_image_preview",
                    "age_limit",
                ),
            },
        ),
        (
            "Date & Venue",
            {
                "fields": (
                    "starts_at",
                    "ends_at",
                    "venue",
                    "city",
                    "address",
                ),
            },
        ),
        (
            "Tickets & Publishing",
            {
                "fields": (
                    "ticket_price",
                    "tickets_available",
                    "is_published",
                ),
            },
        ),
        (
            "Entry Information",
            {
                "fields": (
                    "what_is_included",
                    "entry_rules",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Ticket Price", ordering="ticket_price")
    def ticket_price_display(self, obj):
        return format_html("₹{}", obj.ticket_price)

    @admin.display(description="Status")
    def published_badge(self, obj):
        if obj.is_published:
            return mark_safe(
                '<span style="color:#16803d;font-weight:800;">'
                "● Published</span>"
            )

        return mark_safe(
            '<span style="color:#dc2626;font-weight:800;">'
            "● Draft</span>"
        )

    @admin.display(description="Cover Image Preview")
    def cover_image_preview(self, obj):
        if obj and obj.cover_image_url:
            return format_html(
                '<img src="{}" '
                'style="max-width:300px;max-height:180px;'
                'border-radius:10px;object-fit:cover;" />',
                obj.cover_image_url,
            )

        return "No image set"


# ─── Room Admin ─────────────────────────────────────────────────────────────

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "property_name",
        "room_type",
        "city",
        "price_display",
        "capacity",
        "rating_display",
        "breakfast_included",
        "availability_badge",
        "is_available",
    )

    list_filter = (
        "is_available",
        "breakfast_included",
        "city",
        "room_type",
    )

    search_fields = (
        "name",
        "property_name",
        "city",
        "address",
        "room_type",
    )

    list_editable = ("is_available",)

    ordering = ("price_per_night", "name")

    readonly_fields = ("cover_image_preview",)

    fieldsets = (
        (
            "Property & Room",
            {
                "fields": (
                    "property_name",
                    "name",
                    "room_type",
                    "description",
                    "cover_image_url",
                    "cover_image_preview",
                    "guest_rating",
                ),
            },
        ),
        (
            "Location",
            {
                "fields": (
                    "city",
                    "address",
                    "contact_phone",
                ),
            },
        ),
        (
            "Stay Details",
            {
                "fields": (
                    "price_per_night",
                    "capacity",
                    "bed_type",
                    "amenities",
                    "breakfast_included",
                    "check_in_time",
                    "check_out_time",
                ),
            },
        ),
        (
            "Policies & Availability",
            {
                "fields": (
                    "cancellation_policy",
                    "house_rules",
                    "is_available",
                ),
            },
        ),
    )

    @admin.display(description="Price/Night", ordering="price_per_night")
    def price_display(self, obj):
        return format_html("₹{}", obj.price_per_night)

    @admin.display(description="Rating")
    def rating_display(self, obj):
        if obj.guest_rating:
            stars = "★" * int(obj.guest_rating)

            return format_html(
                '<span style="color:#f59e0b;">{}</span> {}/5',
                stars,
                obj.guest_rating,
            )

        return "—"

    @admin.display(description="Availability")
    def availability_badge(self, obj):
        if obj.is_available:
            return mark_safe(
                '<span style="color:#16803d;font-weight:800;">'
                "✓ Available</span>"
            )

        return mark_safe(
            '<span style="color:#dc2626;font-weight:800;">'
            "✗ Unavailable</span>"
        )

    @admin.display(description="Image Preview")
    def cover_image_preview(self, obj):
        if obj and obj.cover_image_url:
            return format_html(
                '<img src="{}" '
                'style="max-width:300px;max-height:180px;'
                'border-radius:10px;object-fit:cover;" />',
                obj.cover_image_url,
            )

        return "No image set"


# ─── VenueSpace Admin ──────────────────────────────────────────────────────

@admin.register(VenueSpace)
class VenueSpaceAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "space_type_badge",
        "city",
        "address",
        "hourly_rate_display",
        "capacity",
        "availability_badge",
        "is_available",
    )

    list_filter = ("space_type", "is_available", "city")

    search_fields = (
        "name",
        "city",
        "address",
        "amenities",
    )

    list_editable = ("is_available",)

    ordering = ("space_type", "hourly_rate", "name")

    readonly_fields = (
        "cover_image_preview",
        "booking_count",
    )

    fieldsets = (
        (
            "Venue Details",
            {
                "fields": (
                    "name",
                    "space_type",
                    "description",
                    "cover_image_url",
                    "cover_image_preview",
                ),
            },
        ),
        (
            "Location",
            {
                "fields": (
                    "city",
                    "address",
                    "contact_phone",
                ),
            },
        ),
        (
            "Capacity & Pricing",
            {
                "fields": (
                    "hourly_rate",
                    "capacity",
                    "amenities",
                ),
            },
        ),
        (
            "Rules & Availability",
            {
                "fields": (
                    "rules",
                    "is_available",
                ),
            },
        ),
        (
            "Stats (read-only)",
            {
                "fields": ("booking_count",),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Type")
    def space_type_badge(self, obj):
        if obj.space_type == VenueSpace.PARTY_PLOT:
            return mark_safe(
                '<span style="background:#fff3ea;color:#c2410c;'
                'padding:3px 9px;border-radius:99px;'
                'font-weight:800;font-size:.75rem;">'
                "🎪 Party Plot</span>"
            )

        return mark_safe(
            '<span style="background:#fdf4ff;color:#7e22ce;'
            'padding:3px 9px;border-radius:99px;'
            'font-weight:800;font-size:.75rem;">'
            "💍 Wedding Hall</span>"
        )

    @admin.display(description="Hourly Rate", ordering="hourly_rate")
    def hourly_rate_display(self, obj):
        return format_html("₹{}/hr", obj.hourly_rate)

    @admin.display(description="Availability")
    def availability_badge(self, obj):
        if obj.is_available:
            return mark_safe(
                '<span style="color:#16803d;font-weight:800;">'
                "✓ Available</span>"
            )

        return mark_safe(
            '<span style="color:#dc2626;font-weight:800;">'
            "✗ Booked Out</span>"
        )

    @admin.display(description="Total Bookings")
    def booking_count(self, obj):
        if not obj:
            return "Save the venue first"

        return f"{obj.bookings.count()} total bookings"

    @admin.display(description="Image Preview")
    def cover_image_preview(self, obj):
        if obj and obj.cover_image_url:
            return format_html(
                '<img src="{}" '
                'style="max-width:300px;max-height:180px;'
                'border-radius:10px;object-fit:cover;" />',
                obj.cover_image_url,
            )

        return "No image set"


# ─── ContactInquiry Admin ──────────────────────────────────────────────────

class ContactMessageInline(admin.TabularInline):
    model = ContactMessage
    extra = 0

    readonly_fields = (
        "author_name",
        "body",
        "is_staff_reply",
        "created_by",
        "created_at",
    )

    fields = (
        "author_name",
        "body",
        "is_staff_reply",
        "created_by",
        "created_at",
    )

    can_delete = False


@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):

    list_display = (
        "subject",
        "name",
        "email",
        "topic_badge",
        "status_badge",
        "message_count",
        "created_at",
    )

    list_filter = ("status", "topic")

    search_fields = (
        "name",
        "email",
        "subject",
        "message",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "created_at",
        "message_count",
    )

    date_hierarchy = "created_at"

    inlines = [ContactMessageInline]

    fieldsets = (
        (
            "Contact Details",
            {
                "fields": (
                    "name",
                    "email",
                    "phone",
                    "topic",
                ),
            },
        ),
        (
            "Inquiry",
            {
                "fields": (
                    "subject",
                    "message",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "created_at",
                ),
            },
        ),
    )

    @admin.display(description="Topic")
    def topic_badge(self, obj):
        colors = {
            "booking": "#dbeafe:#1d4ed8",
            "payment": "#fef9c3:#854d0e",
            "venue": "#f3e8ff:#7e22ce",
            "stay": "#d1fae5:#065f46",
            "account": "#e0e7ff:#3730a3",
            "other": "#f3f4f6:#374151",
        }

        bg, fg = colors.get(
            obj.topic,
            "#f3f4f6:#374151",
        ).split(":")

        return format_html(
            '<span style="background:{};color:{};'
            'padding:3px 8px;border-radius:99px;'
            'font-size:.75rem;font-weight:800;">{}</span>',
            bg,
            fg,
            obj.get_topic_display(),
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        if obj.status == "new":
            return mark_safe(
                '<span style="color:#c2410c;font-weight:800;">'
                "🔴 New</span>"
            )

        if obj.status == "in_progress":
            return mark_safe(
                '<span style="color:#d97706;font-weight:800;">'
                "🟡 In Progress</span>"
            )

        return mark_safe(
            '<span style="color:#16803d;font-weight:800;">'
            "🟢 Resolved</span>"
        )

    @admin.display(description="Messages")
    def message_count(self, obj):
        return obj.messages.count()


# ─── Booking Admin ──────────────────────────────────────────────────────────

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):

    list_display = (
        "customer_name",
        "contact_phone",
        "kind_badge",
        "booking_title",
        "quantity",
        "amount_display",
        "payment_badge",
        "status_badge",
        "created_at",
    )

    list_filter = (
        "kind",
        "status",
        "payment_method",
        "payment_status",
    )

    search_fields = (
        "customer_name",
        "email",
        "contact_phone",
        "event__name",
        "room__name",
        "venue_space__name",
    )

    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    readonly_fields = (
        "kind",
        "event",
        "room",
        "venue_space",
        "customer_name",
        "email",
        "contact_phone",
        "quantity",
        "check_in",
        "check_out",
        "venue_start_at",
        "venue_end_at",
        "total_amount",
        "payment_method",
        "razorpay_order_id",
        "razorpay_payment_id",
        "public_token",
        "created_at",
        "paid_at",
        "user",
    )

    fieldsets = (
        (
            "Booking Overview",
            {
                "fields": (
                    "kind",
                    "status",
                    "user",
                    "public_token",
                    "created_at",
                ),
            },
        ),
        (
            "What Was Booked",
            {
                "fields": (
                    "event",
                    "room",
                    "venue_space",
                    "quantity",
                    "occasion",
                ),
            },
        ),
        (
            "Schedule",
            {
                "fields": (
                    "check_in",
                    "check_out",
                    "venue_start_at",
                    "venue_end_at",
                ),
            },
        ),
        (
            "Guest Details",
            {
                "fields": (
                    "customer_name",
                    "email",
                    "contact_phone",
                ),
            },
        ),
        (
            "Payment",
            {
                "fields": (
                    "total_amount",
                    "payment_method",
                    "payment_status",
                    "paid_at",
                    "razorpay_order_id",
                    "razorpay_payment_id",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    @admin.display(description="Kind")
    def kind_badge(self, obj):
        icons = {
            "event": "🎭",
            "room": "🏨",
            "venue": "🎪",
        }

        colors = {
            "event": "#fff3ea:#c2410c",
            "room": "#f3e8ff:#7e22ce",
            "venue": "#d1fae5:#065f46",
        }

        icon = icons.get(obj.kind, "📋")

        bg, fg = colors.get(
            obj.kind,
            "#f3f4f6:#374151",
        ).split(":")

        return format_html(
            '<span style="background:{};color:{};'
            'padding:3px 9px;border-radius:99px;'
            'font-size:.75rem;font-weight:800;">'
            "{} {}</span>",
            bg,
            fg,
            icon,
            obj.get_kind_display(),
        )

    @admin.display(description="Booking")
    def booking_title(self, obj):
        if obj.event_id:
            return obj.event.name

        if obj.room_id:
            return obj.room.name

        if obj.venue_space_id:
            return obj.venue_space.name

        return "—"

    @admin.display(description="Total", ordering="total_amount")
    def amount_display(self, obj):
        if obj.total_amount is None:
            return "—"
        try:
            return format_html("₹{}", f"{float(obj.total_amount):,.2f}")
        except (ValueError, TypeError):
            return format_html("₹{}", obj.total_amount)

    @admin.display(description="Payment")
    def payment_badge(self, obj):
        if obj.payment_status == Booking.PAID:
            return mark_safe(
                '<span style="color:#16803d;font-weight:800;">'
                "✓ Paid</span>"
            )

        if obj.payment_status == Booking.REFUNDED:
            return mark_safe(
                '<span style="color:#7e22ce;font-weight:800;">'
                "↩ Refunded</span>"
            )

        if obj.payment_status == Booking.PAYMENT_FAILED:
            return mark_safe(
                '<span style="color:#dc2626;font-weight:800;">'
                "✗ Failed</span>"
            )

        method = (
            "Cash"
            if obj.payment_method == Booking.CASH
            else "Online"
        )

        return format_html(
            '<span style="color:#b45309;font-weight:800;">'
            "⏳ Unpaid · {}</span>",
            method,
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        if obj.status == Booking.CONFIRMED:
            return mark_safe(
                '<span style="color:#16803d;font-weight:800;">'
                "✓ Confirmed</span>"
            )

        if obj.status == Booking.CANCELLED:
            return mark_safe(
                '<span style="color:#dc2626;font-weight:800;">'
                "✗ Cancelled</span>"
            )

        return mark_safe(
            '<span style="color:#b45309;font-weight:800;">'
            "⏳ Pending</span>"
        )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():

            previous_status = None

            if change:
                previous = (
                    Booking.objects
                    .select_for_update()
                    .get(pk=obj.pk)
                )
                previous_status = previous.status

            if (
                obj.kind == Booking.EVENT
                and obj.event_id
                and previous_status != obj.status
            ):
                event = (
                    Event.objects
                    .select_for_update()
                    .get(pk=obj.event_id)
                )

                # Return tickets when a booking is cancelled.
                if (
                    obj.status == Booking.CANCELLED
                    and previous_status != Booking.CANCELLED
                ):
                    if obj.payment_status == Booking.PAID:
                        raise ValidationError(
                            "Record the payment as refunded before "
                            "cancelling this paid booking."
                        )

                    event.tickets_available += obj.quantity

                    event.save(
                        update_fields=("tickets_available",)
                    )

                # Deduct tickets when a cancelled booking is restored.
                elif (
                    previous_status == Booking.CANCELLED
                    and obj.status != Booking.CANCELLED
                ):
                    if obj.quantity > event.tickets_available:
                        raise ValidationError(
                            "Not enough tickets remain to reactivate "
                            "this booking."
                        )

                    event.tickets_available -= obj.quantity

                    event.save(
                        update_fields=("tickets_available",)
                    )

            super().save_model(request, obj, form, change)


# ─── Food Item Admin ───────────────────────────────────────────────────────

@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "restaurant_name",
        "price",
        "area",
        "rating",
        "is_veg",
        "is_jain_available",
        "is_best_seller",
        "is_available",
    )
    list_filter = (
        "category",
        "area",
        "is_veg",
        "is_jain_available",
        "is_best_seller",
        "is_available",
    )
    search_fields = (
        "name",
        "restaurant_name",
        "area",
        "description",
    )
    list_editable = ("price", "is_available", "is_best_seller")


# ─── Food Order Admin ──────────────────────────────────────────────────────

@admin.register(FoodOrder)
class FoodOrderAdmin(admin.ModelAdmin):
    list_display = (
        "public_token",
        "customer_name",
        "contact_phone",
        "food_item",
        "quantity",
        "order_type",
        "payment_method",
        "payment_status",
        "total_amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "payment_method", "payment_status", "order_type", "created_at")
    search_fields = (
        "customer_name",
        "contact_phone",
        "delivery_address",
        "food_item__name",
    )
    list_editable = ("status",)


# ─── User Profile Admin ───────────────────────────────────────────────────

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "mobile_number",
        "gender",
        "date_of_birth",
        "created_at",
    )
    list_filter = ("gender", "created_at")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "mobile_number",
    )
