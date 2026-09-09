import ipaddress

from django.core.exceptions import ValidationError
from django.db import models


class Zona(models.Model):
    """Zona geográfica / sector donde se da servicio. Suele ser una VLAN."""

    nombre = models.CharField("nombre", max_length=80, unique=True)
    descripcion = models.CharField("descripción", max_length=200, blank=True)
    vlan = models.PositiveIntegerField("VLAN", null=True, blank=True)
    red_cidr = models.CharField(
        "red / subred", max_length=20, blank=True,
        help_text="En formato CIDR, ej. 10.10.101.0/24",
    )
    gateway = models.GenericIPAddressField(
        "gateway", protocol="IPv4", null=True, blank=True,
        help_text="IP del router en esta VLAN (se excluye de las disponibles).",
    )
    activa = models.BooleanField("activa", default=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "zona"
        verbose_name_plural = "zonas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def clean(self):
        if self.red_cidr:
            try:
                ipaddress.ip_network(self.red_cidr, strict=False)
            except ValueError:
                raise ValidationError({"red_cidr": "No es una red válida. Ej: 10.10.101.0/24"})

    def ips_del_rango(self):
        """Todas las IPs host de la subred (sin red ni broadcast)."""
        if not self.red_cidr:
            return []
        try:
            net = ipaddress.ip_network(self.red_cidr, strict=False)
        except ValueError:
            return []
        return [str(ip) for ip in net.hosts()]


class Plan(models.Model):
    """Plan de servicio de internet."""

    nombre = models.CharField("nombre", max_length=80, unique=True)
    mbps_bajada = models.PositiveIntegerField("Mbps de bajada")
    mbps_subida = models.PositiveIntegerField("Mbps de subida")
    precio_mensual = models.DecimalField("precio mensual", max_digits=10, decimal_places=2)
    descripcion = models.CharField("descripción", max_length=200, blank=True)
    activo = models.BooleanField("activo", default=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "plan"
        verbose_name_plural = "planes"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.mbps_bajada}/{self.mbps_subida} Mbps)"

    @property
    def texto_factura(self):
        """Cómo se describe el servicio en la factura del cliente."""
        return self.descripcion.strip() if self.descripcion.strip() else (
            f"Internet Fibra Óptica – {self.nombre}"
        )
