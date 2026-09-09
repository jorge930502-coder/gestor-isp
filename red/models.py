from django.db import models

from core.crypto import decrypt, encrypt


class Router(models.Model):
    """Un equipo Mikrotik (RouterOS) al que el sistema se conecta por API."""

    nombre = models.CharField("nombre", max_length=80, unique=True)
    host = models.CharField("IP / host", max_length=120)
    api_puerto = models.PositiveIntegerField("puerto API", default=8728)
    usa_tls = models.BooleanField("API con TLS (8729)", default=False)
    usuario = models.CharField("usuario", max_length=80)
    password_cifrada = models.TextField("contraseña (cifrada)", blank=True)

    lista_morosos = models.CharField(
        "address-list de morosos", max_length=60, default="MOROSOS",
        help_text="Nombre de la address-list que el router bloquea.",
    )
    ifaces_proveedor = models.CharField(
        "interfaces de proveedores (WAN)", max_length=200, blank=True,
        help_text="Nombres separados por coma, ej. ether1,sfp-sfpplus1",
    )
    ifaces_clientes = models.CharField(
        "interfaces de clientes", max_length=200, blank=True,
        help_text="Nombres separados por coma, ej. vlan101,vlan102,vlan103",
    )
    activo = models.BooleanField("activo", default=True)
    notas = models.CharField("notas", max_length=200, blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "router"
        verbose_name_plural = "routers"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.host})"

    # --- contraseña cifrada ---
    def set_password(self, valor: str):
        self.password_cifrada = encrypt(valor or "")

    def get_password(self) -> str:
        return decrypt(self.password_cifrada)

    password = property(get_password, set_password)
