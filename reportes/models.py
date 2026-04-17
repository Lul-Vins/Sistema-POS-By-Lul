from django.db import models


class CierreCaja(models.Model):
    """Registro de cierre de caja diario con desglose por método de pago."""

    fecha_cierre = models.DateTimeField(auto_now_add=True)
    fecha = models.DateField()  # Día del que se cierra

    # ── Efectivo ──
    efectivo_usd_esperado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    efectivo_bs_esperado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    efectivo_usd_real = models.DecimalField(max_digits=10, decimal_places=2)
    efectivo_bs_real = models.DecimalField(max_digits=14, decimal_places=2)
    diferencia_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    diferencia_bs = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # ── Métodos digitales (totales esperados del día) ──
    punto_de_venta_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    biopago_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transferencia_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pago_movil_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    mixto_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Notas opcionales
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Cierre de caja'
        verbose_name_plural = 'Cierres de caja'
        ordering = ['-fecha_cierre']
        unique_together = [['fecha']]  # Solo un cierre por día

    def __str__(self):
        return f'Cierre {self.fecha:%d/%m/%Y} — USD: ${self.efectivo_usd_real}'
