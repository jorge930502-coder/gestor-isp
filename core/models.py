from django.conf import settings
from django.db import models


class Config(models.Model):
    """Configuración general del ISP (un solo registro)."""

    nombre_empresa = models.CharField("nombre de la empresa", max_length=120, default="Mi ISP")
    logo = models.FileField(
        "logo", upload_to="branding/", blank=True,
        help_text="PNG con fondo transparente. Sale en la factura y en el portal.",
    )
    whatsapp = models.CharField(
        "WhatsApp de cobranza", max_length=30, blank=True,
        help_text="Con código de país, sin +, ej. 573001234567",
    )
    telefono = models.CharField("teléfono", max_length=40, blank=True)
    instrucciones_pago = models.TextField(
        "instrucciones de pago", blank=True,
        help_text="Cuentas, Nequi, Daviplata, etc. Se muestran al cliente suspendido.",
    )
    portal_host = models.CharField(
        "dirección del portal", max_length=60, blank=True,
        help_text="IP:puerto donde el router redirige a los morosos. Ej. 192.168.8.50:8000",
    )
    wa_phone_id = models.CharField(
        "WhatsApp API — Phone number ID", max_length=40, blank=True,
        help_text="De Meta (developers.facebook.com). Vacío = el botón abre WhatsApp a mano.",
    )
    wa_api_token = models.CharField(
        "WhatsApp API — Token de acceso", max_length=400, blank=True,
    )

    @property
    def wa_api_lista(self):
        return bool(self.wa_phone_id and self.wa_api_token)
    pie_factura = models.TextField(
        "mensaje al pie de la factura", blank=True,
        help_text="Frase, versículo o aviso que aparece abajo de cada factura.",
    )
    mensaje_whatsapp = models.TextField(
        "mensaje de cobro por WhatsApp", blank=True,
        help_text="Se manda al cliente. Puedes usar: {nombre} {empresa} {monto} "
                  "{periodo} {vence} {pago}",
    )

    MENSAJE_WA_DEFECTO = (
        "Hola {nombre}, te saluda {empresa}. "
        "Tu factura de {periodo} es de ${monto} y vence el {vence}. "
        "Para pagar:\n{pago}\n"
        "Cuando pagues, envía el comprobante por aquí. ¡Gracias!"
    )

    def texto_whatsapp(self, cliente, factura=None):
        from django.utils import timezone
        plantilla = self.mensaje_whatsapp.strip() or self.MENSAJE_WA_DEFECTO
        monto = factura.saldo if factura else cliente.monto_a_facturar()
        return plantilla.format(
            nombre=cliente.nombre,
            empresa=self.nombre_empresa,
            monto=f"{int(monto):,}".replace(",", "."),
            periodo=factura.periodo_texto if factura else "",
            vence=factura.vencimiento.strftime("%d/%m/%Y") if factura else "",
            pago=self.instrucciones_pago or "",
        )

    class Meta:
        verbose_name = "configuración"
        verbose_name_plural = "configuración"

    def __str__(self):
        return "Configuración"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def whatsapp_local(self):
        """El número sin el indicativo 57 y con espacios, para mostrar."""
        n = "".join(ch for ch in self.whatsapp if ch.isdigit())
        if n.startswith("57") and len(n) > 10:
            n = n[2:]
        if len(n) == 10:
            return f"{n[:3]} {n[3:6]} {n[6:]}"
        return n


class Bitacora(models.Model):
    """Registro de acciones relevantes hechas en el sistema."""

    class Accion(models.TextChoices):
        CREAR = "crear", "Crear"
        EDITAR = "editar", "Editar"
        ELIMINAR = "eliminar", "Eliminar"
        CORTE = "corte", "Corte"
        RECONEXION = "reconexion", "Reconexión"
        PAGO = "pago", "Pago"
        OTRO = "otro", "Otro"

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="acciones",
    )
    accion = models.CharField(max_length=20, choices=Accion.choices, default=Accion.OTRO)
    objeto = models.CharField("objeto afectado", max_length=120, blank=True)
    detalle = models.TextField(blank=True)

    class Meta:
        verbose_name = "registro de bitácora"
        verbose_name_plural = "bitácora"
        ordering = ["-fecha"]

    def __str__(self):
        return f"[{self.fecha:%Y-%m-%d %H:%M}] {self.get_accion_display()} — {self.objeto}"


def registrar(usuario, accion, objeto="", detalle=""):
    """Atajo para escribir en la bitácora sin romper el flujo si algo falla."""
    try:
        Bitacora.objects.create(
            usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
            accion=accion,
            objeto=str(objeto)[:120],
            detalle=detalle,
        )
    except Exception:  # pragma: no cover - la bitácora nunca debe tumbar la operación
        pass
