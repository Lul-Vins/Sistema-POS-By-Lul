from django.db import models
from configuracion.models import Moneda


class Categoria(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='productos'
    )
    nombre = models.CharField(max_length=200)
    codigo_barras = models.CharField(max_length=100, blank=True, null=True, unique=True)
    costo_usd = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    precio_usd = models.DecimalField(max_digits=10, decimal_places=4)
    stock_actual = models.IntegerField(default=0)
    stock_minimo = models.IntegerField(default=5)
    imagen = models.ImageField(upload_to='productos/', blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def get_precio_bs(self):
        """Calcula el precio en Bs usando la tasa de cambio vigente. Retorna None si no hay tasa configurada."""
        try:
            return self.precio_usd * Moneda.get_tasa_activa()
        except ValueError:
            return None

    @property
    def margen(self):
        """Margen de ganancia en % sobre el precio de venta. None si no hay costo cargado."""
        try:
            if not self.costo_usd or self.precio_usd == 0:
                return None
            return float(round((self.precio_usd - self.costo_usd) / self.precio_usd * 100, 1))
        except Exception:
            return None

    @property
    def stock_bajo(self):
        """True si el stock actual está en o por debajo del mínimo."""
        return self.stock_actual <= self.stock_minimo
