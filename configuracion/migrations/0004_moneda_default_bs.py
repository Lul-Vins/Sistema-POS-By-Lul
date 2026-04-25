from django.db import migrations
from decimal import Decimal


def crear_moneda_bs(apps, schema_editor):
    Moneda = apps.get_model('configuracion', 'Moneda')
    if not Moneda.objects.exists():
        Moneda.objects.create(simbolo='Bs', tasa_cambio=Decimal('1.00'))


def revertir_moneda_bs(apps, schema_editor):
    Moneda = apps.get_model('configuracion', 'Moneda')
    Moneda.objects.filter(simbolo='Bs', tasa_cambio=Decimal('1.00')).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion', '0003_empresa_nombre_impresora'),
    ]

    operations = [
        migrations.RunPython(crear_moneda_bs, revertir_moneda_bs),
    ]
