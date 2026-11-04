from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.admin.forms import AdminAuthenticationForm

from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(
        template_name="dashboard/staff_login.html",
        authentication_form=AdminAuthenticationForm,
    ), name="dashboard_login"),
    path("", views.overview, name="staff_dashboard"),
    path("bookings/", views.booking_list, name="dashboard_booking_list"),
    path("bookings/<int:pk>/", views.booking_detail, name="dashboard_booking_detail"),
    path("payments/", views.payments, name="dashboard_payments"),
    path("payments/<int:pk>/record-cash/", views.record_cash_payment, name="dashboard_record_cash_payment"),
    path("reports/", views.reports, name="dashboard_reports"),
    path("reports/download.pdf", views.reports_pdf, name="dashboard_reports_pdf"),
    path("bookings/<int:pk>/receipt/", views.payment_receipt, name="dashboard_payment_receipt"),
    path("contacts/", views.contact_inbox, name="dashboard_contact_inbox"),
    path("contacts/new/", views.contact_inquiry_create, name="dashboard_contact_create"),
    path("contacts/<int:pk>/", views.contact_inquiry_detail, name="dashboard_contact_detail"),
]
