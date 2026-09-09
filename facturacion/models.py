from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

MESES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


class Factura(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PAGADA = "pagada", "Pagada"
        ANULADA = "anulada", "Anulada"

    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.CASCADE, related_name="facturas",
    )
    periodo = models.DateField(
        "periodo", help_text="Primer día del mes que cubre la factura.",
    )
    monto = models.DecimalField("monto", max_digits=10, decimal_places=2, default=0)
    detalle = models.CharField("detalle", max_length=200, blank=True)
    vencimiento = models.DateField("vence")
    corte = models.DateField("corte", null=True, blank=True)
    estado = models.CharField(
        "estado", max_length=10, choices=Estado.choices, default=Estado.PENDIENTE,
    )

    creada = models.DateTimeField(auto_now_add=True)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="facturas_creadas",
    )

    class Meta:
        verbose_name = "factura"
        verbose_name_plural = "facturas"
        ordering = ["-periodo", "cliente__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "periodo"], name="factura_unica_por_periodo",
            )
        ]

    def __str__(self):
        return f"{self.cliente.nombre} — {self.periodo_texto}"

    @property
    def periodo_texto(self):
        return f"{MESES[self.periodo.month].capitalize()} {self.periodo.year}"

    @property
    def pagado(self):
        return self.pagos.aggregate(t=Sum("monto"))["t"] or 0

    @property
    def saldo(self):
        return self.monto - self.pagado

    @property
    def vencida(self):
        return self.estado == self.Estado.PENDIENTE and self.vencimiento < timezone.localdate()

    def recalcular_estado(self, guardar=True):
        if self.estado == self.Estado.ANULADA:
            return
        self.estado = self.Estado.PAGADA if self.saldo <= 0 else self.Estado.PENDIENTE
        if guardar:
            self.save(update_fields=["estado"])


class ServicioAdicional(models.Model):
    """Cargo mensual extra de un cliente (TV, teléfono, IP fija, etc.)."""

    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.CASCADE, related_name="adicionales",
    )
    concepto = models.CharField("concepto", max_length=80, default="Televisión")
    monto = models.DecimalField("monto mensual", max_digits=10, decimal_places=2)
    activo = models.BooleanField("activo", default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "servicio adicional"
        verbose_name_plural = "servicios adicionales"
        ordering = ["concepto"]

    def __str__(self):
        return f"{self.cliente.nombre} — {self.concepto} ${self.monto}"


class Pago(models.Model):
    class Metodo(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Transferencia"
        TARJETA = "tarjeta", "Tarjeta"
        OTRO = "otro", "Otro"

    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.CASCADE, related_name="pagos",
    )
    factura = models.ForeignKey(
        Factura, on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos",
    )
    fecha = models.DateField("fecha", default=timezone.localdate)
    monto = models.DecimalField("monto", max_digits=10, decimal_places=2)
    metodo = models.CharField(
        "método", max_length=15, choices=Metodo.choices, default=Metodo.EFECTIVO,
    )
    referencia = models.CharField("referencia", max_length=80, blank=True)
    nota = models.CharField("nota", max_length=200, blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pagos_registrados",
    )

    class Meta:
        verbose_name = "pago"
        verbose_name_plural = "pagos"
        ordering = ["-fecha", "-creado"]

    def __str__(self):
        return f"{self.cliente.nombre} — ${self.monto} ({self.fecha})"
