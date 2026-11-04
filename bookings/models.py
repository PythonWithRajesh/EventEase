import uuid
from datetime import time

from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator


international_phone_validator = RegexValidator(
    regex=r"^\+[1-9][0-9]{7,14}$",
    message="Enter a valid international number with country calling code, for example +919876543210.",
)


class Event(models.Model):
    name = models.CharField(max_length=140)
    category = models.CharField(max_length=40, default="Party")
    description = models.TextField(blank=True)
    venue = models.CharField(max_length=180)
    city = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=240, blank=True)
    organizer_name = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True, validators=[international_phone_validator])
    cover_image_url = models.URLField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    ticket_price = models.DecimalField(max_digits=9, decimal_places=2)
    tickets_available = models.PositiveIntegerField(default=0)
    age_limit = models.CharField(max_length=40, default="All ages")
    what_is_included = models.TextField(blank=True)
    entry_rules = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.name


class Room(models.Model):
    name = models.CharField(max_length=120)
    property_name = models.CharField(max_length=140, default="Amazing Ahmedabad Stay")
    room_type = models.CharField(max_length=80, default="Deluxe Room")
    description = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=240, blank=True)
    cover_image_url = models.URLField(blank=True)
    price_per_night = models.DecimalField(max_digits=9, decimal_places=2)
    capacity = models.PositiveIntegerField(default=2)
    bed_type = models.CharField(max_length=80, default="Double bed")
    amenities = models.TextField(blank=True, help_text="Comma-separated, for example Wi-Fi, AC, TV")
    breakfast_included = models.BooleanField(default=False)
    guest_rating = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True, default=None)
    check_in_time = models.TimeField(default=time(14, 0))
    check_out_time = models.TimeField(default=time(11, 0))
    cancellation_policy = models.TextField(blank=True)
    house_rules = models.TextField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True, validators=[international_phone_validator])
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class VenueSpace(models.Model):
    PARTY_PLOT = "party_plot"
    BANQUET_HALL = "banquet_hall"
    SPACE_TYPE_CHOICES = [(PARTY_PLOT, "Party plot"), (BANQUET_HALL, "Wedding / banquet hall")]

    name = models.CharField(max_length=140)
    space_type = models.CharField(max_length=20, choices=SPACE_TYPE_CHOICES)
    description = models.TextField(blank=True)
    city = models.CharField(max_length=100, default="Ahmedabad")
    address = models.CharField(max_length=240, blank=True)
    cover_image_url = models.URLField(blank=True)
    hourly_rate = models.DecimalField(max_digits=9, decimal_places=2)
    capacity = models.PositiveIntegerField(default=100)
    amenities = models.TextField(blank=True, help_text="Comma-separated amenities")
    rules = models.TextField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True, validators=[international_phone_validator])
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ["hourly_rate", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_space_type_display()})"


class Booking(models.Model):
    EVENT = "event"
    ROOM = "room"
    VENUE = "venue"
    KIND_CHOICES = [(EVENT, "Event ticket"), (ROOM, "Room"), (VENUE, "Party plot / banquet hall")]
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [(PENDING, "Pending"), (CONFIRMED, "Confirmed"), (CANCELLED, "Cancelled")]
    RAZORPAY = "razorpay"
    CASH = "cash"
    PAYMENT_METHOD_CHOICES = [(RAZORPAY, "Razorpay (online payment)"), (CASH, "Cash on delivery (pay at venue / check-in)")]
    UNPAID = "unpaid"
    PAID = "paid"
    PAYMENT_FAILED = "failed"
    REFUNDED = "refunded"
    PAYMENT_STATUS_CHOICES = [(UNPAID, "Unpaid"), (PAID, "Paid"), (PAYMENT_FAILED, "Failed"), (REFUNDED, "Refunded")]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.PROTECT)
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.PROTECT)
    venue_space = models.ForeignKey(VenueSpace, null=True, blank=True, on_delete=models.PROTECT, related_name="bookings")
    customer_name = models.CharField(max_length=120)
    email = models.EmailField()
    contact_phone = models.CharField(max_length=20, default="", validators=[international_phone_validator])
    quantity = models.PositiveIntegerField(default=1)
    check_in = models.DateField(null=True, blank=True)
    check_out = models.DateField(null=True, blank=True)
    venue_start_at = models.DateTimeField(null=True, blank=True)
    venue_end_at = models.DateTimeField(null=True, blank=True)
    occasion = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    payment_method = models.CharField(max_length=12, choices=PAYMENT_METHOD_CHOICES, default=CASH)
    payment_status = models.CharField(max_length=12, choices=PAYMENT_STATUS_CHOICES, default=UNPAID)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    razorpay_order_id = models.CharField(max_length=80, blank=True)
    razorpay_payment_id = models.CharField(max_length=80, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer_name} - {self.get_kind_display()} #{self.pk or 'new'}"


class ContactInquiry(models.Model):
    TOPIC_CHOICES = [
        ("booking", "Booking help"), ("payment", "Payment question"),
        ("venue", "Party plot or wedding hall"), ("stay", "Room or stay"),
        ("account", "Account help"), ("other", "Something else"),
    ]
    STATUS_CHOICES = [
        ("new", "New"), ("in_progress", "In progress"), ("resolved", "Resolved"),
    ]

    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, validators=[international_phone_validator])
    topic = models.CharField(max_length=20, choices=TOPIC_CHOICES, default="other")
    subject = models.CharField(max_length=140)
    message = models.TextField(max_length=4000)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="new")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "contact inquiry"
        verbose_name_plural = "contact inquiries"

    def __str__(self):
        return f"{self.subject} · {self.name}"


class ContactMessage(models.Model):
    inquiry = models.ForeignKey(ContactInquiry, on_delete=models.CASCADE, related_name="messages")
    author_name = models.CharField(max_length=120)
    body = models.TextField(max_length=4000)
    is_staff_reply = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="contact_messages")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.author_name} · inquiry #{self.inquiry_id}"


class FoodItem(models.Model):
    CATEGORY_CHOICES = [
        ("morning_nasto", "Morning Nasto & Fafda"),
        ("vada_vadapav", "Vada & Vadapav Specials (10+ Varieties)"),
        ("pizza_burgers", "Pizzas & Burgers"),
        ("packets_namkeen", "Packets, Wafers & Namkeen (₹10+)"),
        ("snacks_chaat", "Street Snacks & Chaat"),
        ("tea_coffee", "Chai, Coffee & Shakes"),
        ("soda_drinks", "Amdavadi Soda & Refreshments"),
        ("late_night", "Late Night & Manek Chowk"),
        ("fast_food", "Sandwiches, Maggi & Frankies"),
        ("sweets_desserts", "Mithai, Kulfi & Ice Cream"),
        ("thali_meals", "Kathiyawadi Thali & Meals"),
    ]

    name = models.CharField(max_length=140)
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default="morning_nasto")
    restaurant_name = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=7, decimal_places=2)
    original_price = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    area = models.CharField(max_length=100, default="Manek Chowk")
    address = models.CharField(max_length=240, blank=True)
    city = models.CharField(max_length=80, default="Ahmedabad")
    cover_image_url = models.URLField(blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=4.8)
    rating_count = models.PositiveIntegerField(default=120)
    timing = models.CharField(max_length=100, default="7:00 AM – 11:00 PM")
    prep_time = models.CharField(max_length=40, default="10-15 mins")
    is_veg = models.BooleanField(default=True)
    is_jain_available = models.BooleanField(default=True)
    is_best_seller = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    contact_phone = models.CharField(max_length=20, blank=True, validators=[international_phone_validator])

    class Meta:
        ordering = ["category", "price", "name"]

    def __str__(self):
        return f"{self.name} ({self.restaurant_name})"

    @property
    def image_url(self):
        return self.cover_image_url

    @property
    def stall_location(self):
        if self.area and self.city:
            return f"{self.area}, {self.city}"
        return self.area or self.city or "Ahmedabad"


class FoodOrder(models.Model):
    ORDER_TYPE_CHOICES = [
        ("dine_in", "Dine-in / Pickup"),
        ("delivery", "Doorstep Delivery"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="food_orders")
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name="orders")
    customer_name = models.CharField(max_length=120)
    contact_phone = models.CharField(max_length=20, validators=[international_phone_validator])
    delivery_address = models.CharField(max_length=255, blank=True)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default="dine_in")
    quantity = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=9, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="confirmed")

    PAYMENT_METHOD_CHOICES = [
        ("cod", "Cash on Delivery / Pay at Stall (Offline)"),
        ("razorpay", "Razorpay Online (UPI / Card / NetBanking)"),
    ]
    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid Online"),
        ("failed", "Failed"),
    ]
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default="cod")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending")
    razorpay_order_id = models.CharField(max_length=80, blank=True)
    razorpay_payment_id = models.CharField(max_length=80, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{str(self.public_token)[:8].upper()} · {self.customer_name} · {self.food_item.name}"


class UserProfile(models.Model):
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    mobile_number = models.CharField(max_length=20, default="")
    profile_photo = models.ImageField(upload_to="profiles/%Y/%m/", blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username} ({self.mobile_number})"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_otps",
    )
    email = models.EmailField()
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def is_valid(self):
        from django.utils import timezone
        return (not self.is_used) and (timezone.now() <= self.expires_at)

    def __str__(self):
        return f"OTP {self.otp_code} for {self.email} (used={self.is_used})"

