from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0005_add_iva_y_control'),
    ]

    operations = [
        migrations.AlterField(
            model_name='detalleventa',
            name='cantidad',
            field=models.DecimalField(decimal_places=3, max_digits=10),
        ),
    ]
