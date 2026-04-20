from django.db import models
from django.core.exceptions import ValidationError


class Empresa(models.Model):
    nombre = models.CharField(max_length=200)
    rif = models.CharField(max_length=20)
    telefono = models.CharField(max_length=20, blank=True)
    direccion = models.TextField(blank=True)
    logo = models.ImageField(upload_to='empresa/', blank=True, null=True)
    imprimir_ticket   = models.BooleanField(default=False)
    nombre_impresora  = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        verbose_name = 'Empresa'

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        # Patrón Singleton: solo puede existir 1 registro
        if not self.pk and Empresa.objects.exists():
            raise ValidationError('Solo puede existir una configuración de empresa.')
        super().save(*args, **kwargs)


class Moneda(models.Model):
    tasa_cambio = models.DecimalField(max_digits=12, decimal_places=2)
    simbolo = models.CharField(max_length=5, default='Bs')
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Moneda'
        verbose_name_plural = 'Moneda'

    def __str__(self):
        return f'{self.simbolo} — Tasa: {self.tasa_cambio}'

    def save(self, *args, **kwargs):
        # Patrón Singleton: solo puede existir 1 registro
        if not self.pk and Moneda.objects.exists():
            raise ValidationError('Solo puede existir una configuración de moneda.')
        super().save(*args, **kwargs)

    @classmethod
    def get_tasa_activa(cls):
        """Devuelve la tasa vigente. Usado por Producto.get_precio_bs() y en ventas."""
        instancia = cls.objects.first()
        if instancia is None:
            raise ValueError('No hay tasa de cambio configurada. Configure la moneda primero.')
        return instancia.tasa_cambio
