from django.apps import AppConfig
from django.db.backends.signals import connection_created


def configure_sqlite_pragmas(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        try:
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA journal_mode = WAL;")
                cursor.execute("PRAGMA busy_timeout = 60000;")
                cursor.execute("PRAGMA synchronous = NORMAL;")
                cursor.execute("PRAGMA cache_size = -64000;")
        except Exception:
            pass


class BookingsConfig(AppConfig):
    name = 'bookings'

    def ready(self):
        connection_created.connect(configure_sqlite_pragmas)
