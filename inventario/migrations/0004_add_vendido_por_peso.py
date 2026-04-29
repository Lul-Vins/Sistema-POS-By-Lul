from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0003_add_alicuota_iva'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='vendido_por_peso',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='producto',
            name='stock_actual',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=12),
        ),
        migrations.AlterField(
            model_name='producto',
            name='stock_minimo',
            field=models.DecimalField(decimal_places=3, default=5, max_digits=12),
        ),
    ]
