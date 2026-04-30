from django.apps import AppConfig


class ConfiguracionConfig(AppConfig):
    name = 'configuracion'

    def ready(self):
        from django.db.backends.signals import connection_created

        def activar_wal(sender, connection, **kwargs):
            if connection.vendor == 'sqlite':
                with connection.cursor() as cursor:
                    cursor.execute('PRAGMA journal_mode=WAL;')
                    cursor.execute('PRAGMA synchronous=NORMAL;')

        connection_created.connect(activar_wal)
