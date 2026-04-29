from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fiados', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='detallefiado',
            name='cantidad',
            field=models.DecimalField(decimal_places=3, max_digits=10),
        ),
    ]
