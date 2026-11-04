from datetime import timedelta
import csv
from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import CharField, Count, Q, Sum
from django.db.models.functions import Cast
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from bookings.models import Booking, ContactInquiry, ContactMessage
from bookings.services import update_booking_financial_status
from .forms import BookingOperationsForm, ContactInquiryCreateForm, ContactInquiryEditForm, ContactMessageForm


staff_only = staff_member_required(login_url="dashboard_login")


def _page(request, queryset, per_page=15):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


def _report_filters(request):
    today = timezone.localdate()
    start_raw = request.GET.get("start", "")
    end_raw = request.GET.get("end", "")
    try:
        start = date.fromisoformat(start_raw) if start_raw else today - timedelta(days=29)
    except ValueError:
        start = today - timedelta(days=29)
    try:
        end = date.fromisoformat(end_raw) if end_raw else today
    except ValueError:
        end = today
    if start > end:
        start, end = end, start
    kind = request.GET.get("kind", "")
    payment = request.GET.get("payment", "")
    rows = Booking.objects.select_related("event", "room", "venue_space", "user").filter(created_at__date__gte=start, created_at__date__lte=end)
    if kind in dict(Booking.KIND_CHOICES):
        rows = rows.filter(kind=kind)
    if payment in dict(Booking.PAYMENT_METHOD_CHOICES):
        rows = rows.filter(payment_method=payment)
    return rows, {"start": start.isoformat(), "end": end.isoformat(), "kind": kind, "payment": payment}


def _booking_title(booking):
    return booking.event.name if booking.event_id else booking.room.name if booking.room_id else booking.venue_space.name if booking.venue_space_id else "Listing unavailable"


@staff_only
@never_cache
def overview(request):
    today = timezone.localdate()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    chart = [{"label": day.strftime("%a"), "count": Booking.objects.filter(created_at__date=day).count()} for day in days]
    maximum = max((item["count"] for item in chart), default=0) or 1
    for item in chart:
        item["height"] = max(round(item["count"] / maximum * 100), 8)
    metrics = {
        "total": Booking.objects.count(),
        "today": Booking.objects.filter(created_at__date=today).count(),
        "confirmed": Booking.objects.filter(status=Booking.CONFIRMED).count(),
        "pending": Booking.objects.filter(status=Booking.PENDING).count(),
        "cancelled": Booking.objects.filter(status=Booking.CANCELLED).count(),
        "event_total": Booking.objects.filter(kind=Booking.EVENT).count(),
        "room_total": Booking.objects.filter(kind=Booking.ROOM).count(),
        "venue_total": Booking.objects.filter(kind=Booking.VENUE).count(),
        "paid": Booking.objects.filter(payment_status=Booking.PAID).aggregate(total=Sum("total_amount"))["total"] or 0,
        "cash_due": Booking.objects.filter(status=Booking.CONFIRMED, payment_method=Booking.CASH, payment_status=Booking.UNPAID).aggregate(total=Sum("total_amount"))["total"] or 0,
    }
    return render(request, "dashboard/overview.html", {
        "active": "overview", "metrics": metrics, "chart": chart,
        "recent_bookings": Booking.objects.select_related("event", "room", "venue_space", "user")[:8],
    })


@staff_only
@never_cache
def booking_list(request):
    rows = Booking.objects.select_related("event", "room", "venue_space", "user")
    query = request.GET.get("q", "").strip()
    filters = {key: request.GET.get(key, "") for key in ("status", "kind", "payment", "payment_status")}
    if query:
        rows = rows.annotate(token_text=Cast("public_token", output_field=CharField())).filter(
            Q(customer_name__icontains=query) | Q(email__icontains=query)
            | Q(contact_phone__icontains=query) | Q(token_text__icontains=query)
            | Q(razorpay_payment_id__icontains=query) | Q(razorpay_order_id__icontains=query)
            | Q(event__name__icontains=query) | Q(room__name__icontains=query)
            | Q(venue_space__name__icontains=query)
        )
    if filters["status"] in dict(Booking.STATUS_CHOICES):
        rows = rows.filter(status=filters["status"])
    if filters["kind"] in dict(Booking.KIND_CHOICES):
        rows = rows.filter(kind=filters["kind"])
    if filters["payment"] in dict(Booking.PAYMENT_METHOD_CHOICES):
        rows = rows.filter(payment_method=filters["payment"])
    if filters["payment_status"] in dict(Booking.PAYMENT_STATUS_CHOICES):
        rows = rows.filter(payment_status=filters["payment_status"])
    return render(request, "dashboard/booking_list.html", {
        "active": "bookings", "rows": _page(request, rows), "query": query, "filters": filters,
        "statuses": Booking.STATUS_CHOICES, "kinds": Booking.KIND_CHOICES,
        "payments": Booking.PAYMENT_METHOD_CHOICES,
        "payment_statuses": Booking.PAYMENT_STATUS_CHOICES,
    })


@staff_only
@never_cache
def booking_detail(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("event", "room", "venue_space", "user"), pk=pk)
    form = BookingOperationsForm(request.POST or None, instance=booking)
    if request.method == "POST" and form.is_valid():
        try:
            update_booking_financial_status(booking.pk, form.cleaned_data["status"], booking.payment_status)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Booking status updated. Payment status remains controlled by the payment flow.")
            return redirect("dashboard_booking_detail", pk=booking.pk)
    return render(request, "dashboard/booking_detail.html", {"active": "bookings", "booking": booking, "form": form})


@staff_only
@never_cache
def payments(request):
    _, filters = _report_filters(request)
    query = request.GET.get("q", "").strip()
    payment_status = request.GET.get("payment_status", "")
    start, end = date.fromisoformat(filters["start"]), date.fromisoformat(filters["end"])
    period = Q(paid_at__date__gte=start, paid_at__date__lte=end) | Q(
        paid_at__isnull=True, created_at__date__gte=start, created_at__date__lte=end,
    )
    summary = Booking.objects.filter(period)
    rows = Booking.objects.select_related("event", "room", "venue_space", "user").filter(period)
    if filters["kind"] in dict(Booking.KIND_CHOICES):
        summary = summary.filter(kind=filters["kind"])
        rows = rows.filter(kind=filters["kind"])
    if filters["payment"] in dict(Booking.PAYMENT_METHOD_CHOICES):
        summary = summary.filter(payment_method=filters["payment"])
        rows = rows.filter(payment_method=filters["payment"])
    if query:
        rows = rows.annotate(token_text=Cast("public_token", output_field=CharField())).filter(
            Q(customer_name__icontains=query) | Q(email__icontains=query)
            | Q(contact_phone__icontains=query) | Q(token_text__icontains=query)
            | Q(event__name__icontains=query) | Q(room__name__icontains=query)
            | Q(venue_space__name__icontains=query)
        )
    if payment_status in dict(Booking.PAYMENT_STATUS_CHOICES):
        rows = rows.filter(payment_status=payment_status)

    summary_rows = list(summary.only("payment_method", "payment_status", "status", "total_amount"))
    totals = {
        "online_received": sum((item.total_amount for item in summary_rows if item.payment_method == Booking.RAZORPAY and item.payment_status == Booking.PAID), start=0),
        "cash_received": sum((item.total_amount for item in summary_rows if item.payment_method == Booking.CASH and item.payment_status == Booking.PAID), start=0),
        "cash_due": sum((item.total_amount for item in summary_rows if item.payment_method == Booking.CASH and item.status == Booking.CONFIRMED and item.payment_status == Booking.UNPAID), start=0),
        "online_pending": sum((item.total_amount for item in summary_rows if item.payment_method == Booking.RAZORPAY and item.status == Booking.PENDING and item.payment_status == Booking.UNPAID), start=0),
        "refunded": sum((item.total_amount for item in summary_rows if item.payment_status == Booking.REFUNDED), start=0),
    }
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="amazing-ahmedabad-payment-ledger.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["Booking reference", "Customer", "Email", "Booking", "Payment method", "Payment status", "Amount INR", "Booked at", "Paid at", "Razorpay order ID", "Razorpay payment ID"])
        for booking in rows.order_by("-created_at"):
            writer.writerow([str(booking.public_token), booking.customer_name, booking.email, _booking_title(booking), booking.get_payment_method_display(), booking.get_payment_status_display(), booking.total_amount, timezone.localtime(booking.created_at).isoformat(), timezone.localtime(booking.paid_at).isoformat() if booking.paid_at else "", booking.razorpay_order_id, booking.razorpay_payment_id])
        return response
    filters["payment_status"] = payment_status
    filters["q"] = query
    return render(request, "dashboard/payments.html", {
        "active": "payments", "rows": _page(request, rows), "filters": filters,
        "payments": Booking.PAYMENT_METHOD_CHOICES, "payment_statuses": Booking.PAYMENT_STATUS_CHOICES,
        "totals": totals, "gateway_ready": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET),
    })


@staff_only
@never_cache
@require_POST
def record_cash_payment(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.payment_method != Booking.CASH:
        messages.error(request, "Only an offline cash booking can be recorded as cash collected.")
    elif booking.status != Booking.CONFIRMED:
        messages.error(request, "Cash can be recorded only for a confirmed booking.")
    elif booking.payment_status == Booking.PAID:
        messages.info(request, "This cash payment was already recorded.")
    elif booking.payment_status != Booking.UNPAID:
        messages.error(request, "This booking is not awaiting a cash payment.")
    else:
        update_booking_financial_status(booking.pk, booking.status, Booking.PAID)
        messages.success(request, f"Cash payment of ₹{booking.total_amount:,.2f} recorded.")
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect("dashboard_payments")


@staff_only
@never_cache
def reports(request):
    rows, filters = _report_filters(request)
    bookings = list(rows.order_by("created_at"))
    paid_rows = Booking.objects.filter(
        payment_status=Booking.PAID, paid_at__date__gte=filters["start"], paid_at__date__lte=filters["end"]
    )
    if filters["kind"] in dict(Booking.KIND_CHOICES):
        paid_rows = paid_rows.filter(kind=filters["kind"])
    if filters["payment"] in dict(Booking.PAYMENT_METHOD_CHOICES):
        paid_rows = paid_rows.filter(payment_method=filters["payment"])
    paid = list(paid_rows)
    by_kind = []
    for value, label in Booking.KIND_CHOICES:
        count = sum(1 for item in bookings if item.kind == value)
        by_kind.append({"label": label, "count": count})
    by_method = []
    for value, label in Booking.PAYMENT_METHOD_CHOICES:
        count = sum(1 for item in bookings if item.payment_method == value)
        by_method.append({"label": label, "count": count})
    max_count = max((item["count"] for item in by_kind + by_method), default=0) or 1
    for item in by_kind + by_method:
        item["width"] = max(round(item["count"] / max_count * 100), 2)
    day_values = []
    span = (date.fromisoformat(filters["end"]) - date.fromisoformat(filters["start"])).days + 1
    step = max(1, (span + 9) // 10)
    start = date.fromisoformat(filters["start"])
    end = date.fromisoformat(filters["end"])
    cursor = start
    while cursor <= end:
        bucket_end = min(end, date.fromordinal(cursor.toordinal() + step - 1))
        amount = sum((item.total_amount for item in paid if item.paid_at and cursor <= timezone.localtime(item.paid_at).date() <= bucket_end), start=0)
        day_values.append({"label": cursor.strftime("%b %d").replace(" 0", " "), "amount": amount})
        cursor = date.fromordinal(bucket_end.toordinal() + 1)
    max_amount = max((item["amount"] for item in day_values), default=0) or 1
    for item in day_values:
        item["height"] = max(round(float(item["amount"] / max_amount * 100)), 3)
    cash_due = sum((item.total_amount for item in bookings if item.status == Booking.CONFIRMED and item.payment_method == Booking.CASH and item.payment_status == Booking.UNPAID), start=0)
    metrics = {
        "total": len(bookings), "confirmed": sum(1 for item in bookings if item.status == Booking.CONFIRMED),
        "cancelled": sum(1 for item in bookings if item.status == Booking.CANCELLED),
        "paid": sum((item.total_amount for item in paid), start=0),
        "online_paid": sum((item.total_amount for item in paid if item.payment_method == Booking.RAZORPAY), start=0),
        "cash_due": cash_due,
    }
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="amazing-ahmedabad-booking-report.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["Booking reference", "Customer", "Email", "Phone", "Category", "Listing", "Booking status", "Payment method", "Payment status", "Amount (INR)", "Booked at", "Paid at", "Razorpay payment ID"])
        for booking in bookings:
            writer.writerow([str(booking.public_token), booking.customer_name, booking.email, booking.contact_phone, booking.get_kind_display(), _booking_title(booking), booking.get_status_display(), booking.get_payment_method_display(), booking.get_payment_status_display(), booking.total_amount, timezone.localtime(booking.created_at).isoformat(), timezone.localtime(booking.paid_at).isoformat() if booking.paid_at else "", booking.razorpay_payment_id])
        return response
    return render(request, "dashboard/reports.html", {"active": "reports", "filters": filters, "metrics": metrics, "by_kind": by_kind, "by_method": by_method, "revenue_chart": day_values, "statuses": Booking.STATUS_CHOICES, "kinds": Booking.KIND_CHOICES, "payments": Booking.PAYMENT_METHOD_CHOICES})


@staff_only
@never_cache
def reports_pdf(request):
    rows, filters = _report_filters(request)
    bookings = list(rows.order_by("created_at"))
    paid_total = Booking.objects.filter(payment_status=Booking.PAID, paid_at__date__gte=filters["start"], paid_at__date__lte=filters["end"])
    if filters["kind"] in dict(Booking.KIND_CHOICES):
        paid_total = paid_total.filter(kind=filters["kind"])
    if filters["payment"] in dict(Booking.PAYMENT_METHOD_CHOICES):
        paid_total = paid_total.filter(payment_method=filters["payment"])
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=12*mm, leftMargin=12*mm, topMargin=13*mm, bottomMargin=13*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], textColor=colors.HexColor("#392052"), alignment=TA_LEFT, fontSize=19, leading=22, spaceAfter=3))
    styles.add(ParagraphStyle(name="ReportSmall", parent=styles["Normal"], textColor=colors.HexColor("#655d70"), fontSize=7, leading=9, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="ReportHead", parent=styles["Normal"], textColor=colors.white, fontSize=7, leading=9, fontName="Helvetica-Bold"))
    story = [Paragraph("AMAZING AHMEDABAD · CUSTOM ADMIN", styles["ReportSmall"]), Paragraph("Booking & revenue report", styles["ReportTitle"]), Paragraph(f"Booking dates: {escape(filters['start'])} to {escape(filters['end'])} · {len(bookings)} booking records · Payments recorded as paid in range: INR {paid_total.aggregate(total=Sum('total_amount'))['total'] or 0:,.2f}", styles["ReportSmall"]), Spacer(1, 5*mm)]
    headings = ["Reference", "Customer", "Category / listing", "Booking", "Payment", "Total (INR)", "Booked at", "Payment ref"]
    data = [[Paragraph(escape(label), styles["ReportHead"]) for label in headings]]
    for booking in bookings:
        title = f"{booking.get_kind_display()}<br/>{_booking_title(booking)}"
        payment_ref = booking.razorpay_payment_id or ("Cash" if booking.payment_method == Booking.CASH else "—")
        values = [str(booking.public_token)[:8].upper(), booking.customer_name, title, booking.get_status_display(), f"{booking.get_payment_method_display()}<br/>{booking.get_payment_status_display()}", f"{booking.total_amount:,.2f}", timezone.localtime(booking.created_at).strftime("%d %b %Y %H:%M"), payment_ref]
        data.append([Paragraph(escape(str(value)).replace("&lt;br/&gt;", "<br/>"), styles["ReportSmall"]) for value in values])
    table = Table(data, colWidths=[23*mm, 31*mm, 45*mm, 23*mm, 42*mm, 22*mm, 32*mm, 51*mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#352052")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f6fa")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#e5b783")), ("LINEBELOW", (0, 1), (-1, -1), .35, colors.HexColor("#e9e5ed")),
    ]))
    story.append(table)
    document.build(story)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="amazing-ahmedabad-booking-report.pdf"'
    return response


@staff_only
@never_cache
def payment_receipt(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("event", "room", "venue_space", "user"), pk=pk)
    if booking.payment_status != Booking.PAID or (booking.payment_method == Booking.RAZORPAY and not booking.razorpay_payment_id):
        messages.warning(request, "A receipt is available after the payment has been recorded as paid.")
        return redirect("dashboard_booking_detail", pk=booking.pk)
    return render(request, "dashboard/payment_receipt.html", {"booking": booking})


@staff_only
@never_cache
def contact_inbox(request):
    rows = ContactInquiry.objects.annotate(message_count=Count("messages")).order_by("-created_at")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    topic = request.GET.get("topic", "")
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(email__icontains=query) | Q(subject__icontains=query) | Q(message__icontains=query) | Q(messages__body__icontains=query)).distinct()
    if status in dict(ContactInquiry.STATUS_CHOICES):
        rows = rows.filter(status=status)
    if topic in dict(ContactInquiry.TOPIC_CHOICES):
        rows = rows.filter(topic=topic)
    page = _page(request, rows)
    return render(request, "dashboard/contact_inbox.html", {
        "active": "contacts", "rows": page, "page": page, "query": query,
        "filters": {"status": status, "topic": topic},
        "selected_status": status, "selected_topic": topic,
        "statuses": ContactInquiry.STATUS_CHOICES, "topics": ContactInquiry.TOPIC_CHOICES,
        "new_count": ContactInquiry.objects.filter(status="new").count(),
    })


@staff_only
@never_cache
def contact_inquiry_create(request):
    form = ContactInquiryCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        inquiry = form.save()
        ContactMessage.objects.create(inquiry=inquiry, author_name=inquiry.name, body=inquiry.message)
        messages.success(request, f"Inquiry #{inquiry.pk} was added to the contact inbox.")
        return redirect("dashboard_contact_detail", pk=inquiry.pk)
    return render(request, "dashboard/contact_create.html", {"active": "contacts", "form": form})


@staff_only
@never_cache
def contact_inquiry_detail(request, pk):
    inquiry = get_object_or_404(ContactInquiry.objects.prefetch_related("messages"), pk=pk)
    if not inquiry.messages.exists():
        ContactMessage.objects.create(inquiry=inquiry, author_name=inquiry.name, body=inquiry.message)
        inquiry = ContactInquiry.objects.prefetch_related("messages").get(pk=pk)
    action = request.POST.get("action") if request.method == "POST" else ""
    form = ContactInquiryEditForm(request.POST if action == "save_details" else None, instance=inquiry)
    reply_form = ContactMessageForm(request.POST if action == "add_message" else None)
    if action == "save_details" and form.is_valid():
        form.save()
        messages.success(request, "Customer details and inquiry status saved.")
        return redirect("dashboard_contact_detail", pk=inquiry.pk)
    if action == "add_message" and reply_form.is_valid():
        ContactMessage.objects.create(
            inquiry=inquiry,
            author_name=request.user.get_full_name() or request.user.get_username(),
            body=reply_form.cleaned_data["body"],
            is_staff_reply=True,
            created_by=request.user,
        )
        messages.success(request, "Message added to this inquiry's conversation.")
        return redirect("dashboard_contact_detail", pk=inquiry.pk)
    return render(request, "dashboard/contact_detail.html", {
        "active": "contacts", "inquiry": inquiry, "form": form,
        "reply_form": reply_form, "conversation": inquiry.messages.all(),
    })
