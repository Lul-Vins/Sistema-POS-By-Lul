from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from decimal import Decimal, ROUND_HALF_UP
from configuracion.models import Moneda
from inventario.models import Producto

# Tasas IVA vigentes (SENIAT)
_TASAS_IVA = {
    'GENERAL':  Decimal('16'),
    'REDUCIDA': Decimal('8'),
    'EXENTO':   Decimal('0'),
}
_D2 = Decimal('0.01')


class ContadorFactura(models.Model):
    """
    Singleton. Lleva el último número correlativo de factura emitido.
    El incremento ocurre dentro de transaction.atomic() + select_for_update()
    para garantizar que no haya huecos ni duplicados aunque haya concurrencia.
    """
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Contador de Factura'

    def save(self, *args, **kwargs):
        if not self.pk and ContadorFactura.objects.exists():
            raise ValidationError('Solo puede existir un contador de factura.')
        super().save(*args, **kwargs)

    @classmethod
    def siguiente(cls):
        """Reserva y devuelve el siguiente número. Llamar dentro de atomic()."""
        obj, _ = cls.objects.select_for_update().get_or_create(
            defaults={'ultimo_numero': 0}
        )
        obj.ultimo_numero += 1
        obj.save(update_fields=['ultimo_numero'])
        return obj.ultimo_numero


class ContadorControl(models.Model):
    """
    Singleton. Lleva el último número de control emitido (SENIAT).
    Correlativo independiente del número de factura.
    """
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Contador de Control'

    def save(self, *args, **kwargs):
        if not self.pk and ContadorControl.objects.exists():
            raise ValidationError('Solo puede existir un contador de control.')
        super().save(*args, **kwargs)

    @classmethod
    def siguiente(cls):
        obj, _ = cls.objects.select_for_update().get_or_create(
            defaults={'ultimo_numero': 0}
        )
        obj.ultimo_numero += 1
        obj.save(update_fields=['ultimo_numero'])
        return obj.ultimo_numero


class Venta(models.Model):

    METODO_PAGO = [
        ('EFECTIVO_USD',   'Efectivo USD'),
        ('EFECTIVO_BS',    'Efectivo Bs'),
        ('TRANSFERENCIA',  'Transferencia'),
        ('PAGO_MOVIL',     'Pago Móvil'),
        ('PUNTO_DE_VENTA', 'PdV (Tarjeta)'),
        ('BIOPAGO',        'Biopago'),
        ('MIXTO',          'Pago Mixto'),
    ]

    ESTADO = [
        ('COMPLETADA', 'Completada'),
        ('ANULADA',    'Anulada'),
    ]

    fecha           = models.DateTimeField(auto_now_add=True)
    total_usd       = models.DecimalField(max_digits=10, decimal_places=2)
    total_bs        = models.DecimalField(max_digits=14, decimal_places=2)
    tasa_aplicada   = models.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago     = models.CharField(max_length=20, choices=METODO_PAGO)
    estado          = models.CharField(max_length=15, choices=ESTADO, default='COMPLETADA')
    notas           = models.TextField(blank=True)
    monto_recibido  = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    vuelto          = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    vendedor        = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='ventas')
    numero_factura  = models.PositiveIntegerField(unique=True, null=True, blank=True)
    numero_control  = models.PositiveIntegerField(unique=True, null=True, blank=True)

    # Desglose fiscal SENIAT
    monto_exento_usd    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    base_imponible_usd  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    iva_usd             = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_exento_bs     = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    base_imponible_bs   = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    iva_bs              = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name        = 'Venta'
        verbose_name_plural = 'Ventas'
        ordering            = ['-fecha']

    def __str__(self):
        return f'Factura {self.numero_fmt} — {self.fecha:%d/%m/%Y %H:%M}'

    @property
    def numero_fmt(self):
        """Número de factura SENIAT: 8 dígitos, cero-relleno."""
        if self.numero_factura:
            return f'{self.numero_factura:08d}'
        return f'#{self.pk}'

    @property
    def numero_control_fmt(self):
        """Número de control SENIAT: prefijo 00- + 8 dígitos."""
        if self.numero_control:
            return f'00-{self.numero_control:08d}'
        return '—'

    @classmethod
    def crear_desde_carrito(cls, carrito, metodo_pago, notas='', monto_recibido=None, vuelto=None, vendedor=None):
        """
        Procesa el carrito completo en una transacción atómica.

        carrito: [{'producto': <Producto>, 'cantidad': int}, ...]

        El precio_usd de cada producto es el precio al público con IVA incluido.
        El sistema desglosa base_imponible + iva = total sin alterar lo que paga el cliente.
        """
        with transaction.atomic():
            tasa = Moneda.get_tasa_activa()

            total_usd          = Decimal('0')
            monto_exento_usd   = Decimal('0')
            base_imponible_usd = Decimal('0')
            iva_usd            = Decimal('0')

            items = []
            for item in carrito:
                producto = Producto.objects.select_for_update().get(pk=item['producto'].pk)
                cantidad = item['cantidad']

                if producto.stock_actual < cantidad:
                    raise ValueError(
                        f'Stock insuficiente para "{producto.nombre}". '
                        f'Disponible: {producto.stock_actual}, solicitado: {cantidad}.'
                    )

                precio   = producto.precio_usd   # precio al público, IVA ya incluido
                alicuota = producto.alicuota_iva
                subtotal = precio * cantidad
                total_usd += subtotal

                if alicuota == 'EXENTO':
                    monto_exento_usd += subtotal
                else:
                    tasa_pct  = _TASAS_IVA.get(alicuota, Decimal('16'))
                    factor    = 1 + tasa_pct / 100
                    base_item = (subtotal / factor).quantize(_D2, rounding=ROUND_HALF_UP)
                    iva_usd  += subtotal - base_item
                    base_imponible_usd += base_item

                items.append((producto, cantidad, precio, alicuota))

            total_usd          = total_usd.quantize(_D2, rounding=ROUND_HALF_UP)
            monto_exento_usd   = monto_exento_usd.quantize(_D2, rounding=ROUND_HALF_UP)
            base_imponible_usd = base_imponible_usd.quantize(_D2, rounding=ROUND_HALF_UP)
            iva_usd            = iva_usd.quantize(_D2, rounding=ROUND_HALF_UP)

            total_bs          = (total_usd          * tasa).quantize(_D2, rounding=ROUND_HALF_UP)
            monto_exento_bs   = (monto_exento_usd   * tasa).quantize(_D2, rounding=ROUND_HALF_UP)
            base_imponible_bs = (base_imponible_usd * tasa).quantize(_D2, rounding=ROUND_HALF_UP)
            iva_bs            = (iva_usd            * tasa).quantize(_D2, rounding=ROUND_HALF_UP)

            # Reservar ambos correlativos dentro del mismo lock
            numero          = ContadorFactura.siguiente()
            numero_control  = ContadorControl.siguiente()

            venta = cls.objects.create(
                numero_factura     = numero,
                numero_control     = numero_control,
                total_usd          = total_usd,
                total_bs           = total_bs,
                tasa_aplicada      = tasa,
                metodo_pago        = metodo_pago,
                notas              = notas,
                monto_recibido     = monto_recibido,
                vuelto             = vuelto,
                vendedor           = vendedor,
                monto_exento_usd   = monto_exento_usd,
                base_imponible_usd = base_imponible_usd,
                iva_usd            = iva_usd,
                monto_exento_bs    = monto_exento_bs,
                base_imponible_bs  = base_imponible_bs,
                iva_bs             = iva_bs,
            )

            for producto, cantidad, precio_capturado, alicuota in items:
                DetalleVenta.objects.create(
                    venta                = venta,
                    producto             = producto,
                    cantidad             = cantidad,
                    precio_usd_capturado = precio_capturado,
                    alicuota_iva         = alicuota,
                )
                producto.stock_actual -= cantidad
                producto.save(update_fields=['stock_actual'])

            return venta


class DetalleVenta(models.Model):
    venta                = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto             = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='detalles_venta')
    cantidad             = models.DecimalField(max_digits=10, decimal_places=3)
    precio_usd_capturado = models.DecimalField(max_digits=10, decimal_places=4)
    alicuota_iva         = models.CharField(max_length=10, default='GENERAL')  # snapshot al momento de la venta

    class Meta:
        verbose_name        = 'Detalle de venta'
        verbose_name_plural = 'Detalles de venta'

    def __str__(self):
        return f'{self.cantidad}x {self.producto.nombre}'

    @property
    def subtotal_usd(self):
        return self.precio_usd_capturado * self.cantidad

    @property
    def subtotal_bs(self):
        return self.subtotal_usd * self.venta.tasa_aplicada

    @property
    def base_unitaria_usd(self):
        """Precio unitario sin IVA."""
        if self.alicuota_iva == 'EXENTO':
            return self.precio_usd_capturado
        tasa_pct = _TASAS_IVA.get(self.alicuota_iva, Decimal('16'))
        factor   = 1 + tasa_pct / 100
        return (self.precio_usd_capturado / factor).quantize(_D2, rounding=ROUND_HALF_UP)

    @property
    def iva_unitario_usd(self):
        return (self.precio_usd_capturado - self.base_unitaria_usd).quantize(_D2, rounding=ROUND_HALF_UP)
