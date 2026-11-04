# Amazing Ahmedabad

A Django website for Navratri and party tickets, hotel-style room stays, hourly party-plot hire and wedding / banquet hall reservations. Party plots and wedding halls have separate browsing pages and booking forms, with 1–6 hour party slots and 2–12 hour wedding-hall slots. Venue bookings collect the occasion, guest count, date, start time and duration, calculate the hourly total, and block overlapping time slots. It includes Razorpay checkout, cash payment at the venue, and a detailed receipt.

Customers can register and sign in with a username or email, manage event, room and venue bookings from **My bookings**, and log out using a CSRF-protected form. Reservations require an account and are linked to it. Django validates and hashes passwords; registration rejects duplicate email addresses. The public `/contact/` form validates and stores support inquiries in the database; staff can search the private inbox and track inquiry status at `/custom_admin/contacts/`. After a captured Razorpay payment, customers can download a PDF receipt. The separate staff-only `dashboard` app at `/custom_admin/` shows booking records, including occasion, guest count and reserved venue times. Staff can review and update booking/payment status, with event ticket inventory checks, and export filtered reports as PDF or CSV. The public website does not show a link to this private portal.

## Run on Windows

```powershell
cd R:\openai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000/> for the customer website. Staff can enter the separate booking portal directly at <http://127.0.0.1:8000/custom_admin/>. The demo data is fictional and marked as sample; replace it and add verified photo URLs before publishing.

Customers can create an account or log in. Booking flows ask customers to sign in first, then continue to their selected event, room, party plot or wedding hall. The migration adds clearly labelled sample venue listings; replace them with verified operators, prices, photos and availability before taking real bookings.

## Payments

Customers can select Razorpay online or cash on arrival. Cash bookings are confirmed immediately and show the cash due on the receipt. Online bookings confirm only after the server validates the Razorpay signature and verifies the captured amount. To use Razorpay locally, copy the sample configuration and add your own **Test Mode** API keys from the Razorpay Dashboard:

```powershell
Copy-Item .env.example .env
notepad .env
python manage.py runserver
```

Replace both example values with the Test Mode Key ID and Key Secret, save `.env`, then restart the server. Keep `.env` private; it is excluded from Git. Set the Razorpay Dashboard to auto-capture payments, because the site confirms bookings only after Razorpay reports a captured payment. Test a full booking using Razorpay Test Mode before switching to Live Mode keys. Razorpay requires an order for each checkout and server-side signature verification; this project performs both steps. See [Razorpay's official Python integration guide](https://razorpay.com/docs/server-integration/python/test-app/).

This project runs locally. Before opening to real customers, configure production settings and hosting, use PostgreSQL, set up email notifications and a Razorpay webhook, and publish only verified listings and prices.
