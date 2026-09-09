from django.conf import settings
from django.db import models
from django.urls import reverse


class Cliente(models.Model):
    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        SUSPENDIDO = "suspendido", "Suspendido"
        CANCELADO = "cancelado", "Cancelado"
        GRATIS = "gratis", "Gratis"

    class FormaContratacion(models.TextChoices):
        RECOMENDACION = "recomendacion", "Recomendación"
        TELEFONO = "telefono", "Teléfono"
        OFICINA = "oficina", "Oficina"
        VENDEDOR = "vendedor", "Vendedor"
        INTERNET = "internet", "Página / Internet"
        REDES = "redes", "Redes sociales"
        OTROS = "otros", "Otros"

    # Datos personales
    nombre = models.CharField("nombre completo", max_length=150)
    documento = models.CharField(
        "documento / identificación", max_length=40, blank=True,
        help_text="DNI, RFC, cédula, etc.",
    )
    telefono = models.CharField("teléfono", max_length=40, blank=True)
    email = models.EmailField("correo", blank=True)
    direccion = models.CharField("dirección", max_length=250, blank=True)
    coordenadas = models.CharField(
        "coordenadas", max_length=60, blank=True,
        help_text="Latitud,Longitud (ej. 4.6097,-74.0817).",
    )

    # Servicio
    zona = models.ForeignKey(
        "catalogo.Zona", on_delete=models.PROTECT, related_name="clientes",
        null=True, blank=True, verbose_name="zona",
    )
    plan = models.ForeignKey(
        "catalogo.Plan", on_delete=models.PROTECT, related_name="clientes",
        null=True, blank=True, verbose_name="plan",
    )
    router = models.ForeignKey(
        "red.Router", on_delete=models.SET_NULL, related_name="clientes",
        null=True, blank=True, verbose_name="router",
    )
    ip = models.GenericIPAddressField(
        "IP asignada", protocol="IPv4", null=True, blank=True, unique=True,
        help_text="IP fija del cliente. Se usa para el corte/reconexión.",
    )
    nombre_cola = models.CharField(
        "nombre en el router", max_length=120, blank=True,
        help_text="Nombre de la cola simple / usuario PPPoE en el Mikrotik.",
    )
    dia_de_pago = models.PositiveSmallIntegerField(
        "día de pago", default=1, help_text="Día del mes en que vence (1-28).",
    )
    dia_de_corte = models.PositiveSmallIntegerField(
        "día de corte", null=True, blank=True,
        help_text="Día del mes en que se suspende si no pagó. Vacío = no se corta automático.",
    )
    estado = models.CharField(
        "estado", max_length=12, choices=Estado.choices, default=Estado.ACTIVO,
    )
    forma_contratacion = models.CharField(
        "forma de contratación", max_length=20, choices=FormaContratacion.choices,
        blank=True,
    )
    fecha_registro = models.DateField("fecha de registro", null=True, blank=True)
    fecha_instalacion = models.DateField("fecha de instalación", null=True, blank=True)
    fecha_cancelacion = models.DateField("fecha de cancelación", null=True, blank=True)
    notas = models.TextField("comentarios", blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="clientes_creados",
    )

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nombre"]
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["nombre"]),
        ]

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        return reverse("clientes:detalle", args=[self.pk])

    @property
    def esta_activo(self):
        return self.estado == self.Estado.ACTIVO

    @property
    def cobra(self):
        """¿Se le factura? (todos menos Gratis y Cancelado)."""
        return self.estado in {self.Estado.ACTIVO, self.Estado.SUSPENDIDO}

    def monto_adicionales(self):
        return sum((a.monto for a in self.adicionales.all() if a.activo), 0)

    def monto_a_facturar(self):
        """Cuánto se le cobra al mes: plan + adicionales. Los Gratis pagan 0."""
        if self.estado == self.Estado.GRATIS:
            return 0
        base = self.plan.precio_mensual if self.plan_id else 0
        return base + self.monto_adicionales()

    def detalle_cobro(self):
        """Texto tipo 'Plan 50 Megas $30000 + Televisión $10000'."""
        if self.estado == self.Estado.GRATIS:
            return "Cortesía (sin cobro)"
        partes = []
        if self.plan_id:
            partes.append(f"{self.plan.nombre} ${self.plan.precio_mensual:g}")
        for a in self.adicionales.all():
            if a.activo:
                partes.append(f"{a.concepto} ${a.monto:g}")
        return " + ".join(partes) or "sin cargo"
