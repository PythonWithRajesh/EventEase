"""
WSGI config for booking_site project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'booking_site.settings')

application = get_wsgi_application()

# Auto-initialize database with catalog data on first startup if empty
try:
    from django.core.management import call_command
    from bookings.models import FoodItem
    if FoodItem.objects.count() == 0:
        call_command("migrate", interactive=False)
        call_command("seed_demo")
except Exception:
    pass
