from django.db import models
from django.db import transaction
from configuracion.models import Moneda
from inventario.models import Producto


class Venta(models.Model):

    METODO_PAGO = [
        ('EFECTIVO_USD', 'Efectivo USD'),
        ('EFECTIVO_BS',  'Efectivo Bs'),
        ('TRANSFERENCIA', 'Transferencia'),
        ('PAGO_MOVIL',   'Pago Móvil'),
        ('MIXTO',        'Pago Mixto'),
    ]

    ESTADO = [
        ('COMPLETADA', 'Completada'),
        ('ANULADA',    'Anulada'),
    ]

    fecha = models.DateTimeField(auto_now_add=True)
    total_usd = models.DecimalField(max_digits=10, decimal_places=2)
    total_bs = models.DecimalField(max_digits=14, decimal_places=2)
    tasa_aplicada = models.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO)
    estado = models.CharField(max_length=15, choices=ESTADO, default='COMPLETADA')
    notas = models.TextField(blank=True)
    # Solo para pagos en efectivo (USD o Bs según metodo_pago)
    monto_recibido = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    vuelto = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'
        ordering = ['-fecha']

    def __str__(self):
        return f'Venta #{self.pk} — {self.fecha:%d/%m/%Y %H:%M}'

    @classmethod
    def crear_desde_carrito(cls, carrito, metodo_pago, notas='', monto_recibido=None, vuelto=None):
        """
        Procesa el carrito completo en una transacción atómica.

        `carrito` es una lista de dicts:
            [{'producto': <Producto>, 'cantidad': 2}, ...]

        Si cualquier paso falla (stock insuficiente, tasa no configurada, etc.),
        se hace rollback completo: ni se descuenta el inventario ni se guarda la venta.
        """
        with transaction.atomic():
            tasa = Moneda.get_tasa_activa()
            total_usd = 0

            # Validar stock y calcular total antes de tocar la BD
            items = []
            for item in carrito:
                producto = Producto.objects.select_for_update().get(pk=item['producto'].pk)
                cantidad = item['cantidad']

                if producto.stock_actual < cantidad:
                    raise ValueError(
                        f'Stock insuficiente para "{producto.nombre}". '
                        f'Disponible: {producto.stock_actual}, solicitado: {cantidad}.'
                    )

                precio_capturado = producto.precio_usd
                total_usd += precio_capturado * cantidad
                items.append((producto, cantidad, precio_capturado))

            total_bs = total_usd * tasa

            # Registrar la venta
            venta = cls.objects.create(
                total_usd=total_usd,
                total_bs=total_bs,
                tasa_aplicada=tasa,
                metodo_pago=metodo_pago,
                notas=notas,
                monto_recibido=monto_recibido,
                vuelto=vuelto,
            )

            # Registrar detalles y descontar inventario
            for producto, cantidad, precio_capturado in items:
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    cantidad=cantidad,
                    precio_usd_capturado=precio_capturado,
                )
                producto.stock_actual -= cantidad
                producto.save(update_fields=['stock_actual'])

            return venta


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='detalles_venta')
    cantidad = models.PositiveIntegerField()
    precio_usd_capturado = models.DecimalField(max_digits=10, decimal_places=4)

    class Meta:
        verbose_name = 'Detalle de venta'
        verbose_name_plural = 'Detalles de venta'

    def __str__(self):
        return f'{self.cantidad}x {self.producto.nombre}'

    @property
    def subtotal_usd(self):
        return self.precio_usd_capturado * self.cantidad

    @property
    def subtotal_bs(self):
        return self.subtotal_usd * self.venta.tasa_aplicada
