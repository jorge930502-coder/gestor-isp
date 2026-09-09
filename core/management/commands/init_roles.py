"""Crea/actualiza los roles (grupos) del sistema y sus permisos.

Ejecutar cada vez que se agreguen modelos nuevos:

    python manage.py init_roles
"""

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


# Rol -> { "app_label.modelo": ["add", "change", "delete", "view"] }
# "*" en la lista de acciones = todas las acciones de ese modelo.
ROLES = {
    "Administración": {
        "catalogo.zona": ["*"],
        "catalogo.plan": ["*"],
        "clientes.cliente": ["*"],
        "red.router": ["*"],
        "facturacion.factura": ["*"],
        "facturacion.pago": ["*"],
        "facturacion.servicioadicional": ["*"],
        "core.bitacora": ["view"],
        "auth.user": ["*"],
        "auth.group": ["view"],
    },
    "Cobranza": {
        "catalogo.zona": ["view"],
        "catalogo.plan": ["view"],
        "clientes.cliente": ["view", "change"],
        "facturacion.factura": ["add", "change", "view"],
        "facturacion.pago": ["add", "change", "view"],
        "facturacion.servicioadicional": ["add", "change", "view"],
        "core.bitacora": ["view"],
    },
    "Soporte": {
        "catalogo.zona": ["view"],
        "catalogo.plan": ["view"],
        "clientes.cliente": ["add", "change", "view"],
        "facturacion.factura": ["view"],
        "facturacion.pago": ["view"],
    },
}

ACTIONS = ["add", "change", "delete", "view"]


class Command(BaseCommand):
    help = "Crea los roles del sistema y asigna sus permisos."

    def handle(self, *args, **options):
        for rol, modelos in ROLES.items():
            group, created = Group.objects.get_or_create(name=rol)
            perms = []
            for dotted, acciones in modelos.items():
                app_label, model_name = dotted.split(".")
                try:
                    model = apps.get_model(app_label, model_name)
                except LookupError:
                    self.stderr.write(f"  ! modelo no encontrado: {dotted} (se omite)")
                    continue
                wanted = ACTIONS if acciones == ["*"] else acciones
                for action in wanted:
                    codename = f"{action}_{model._meta.model_name}"
                    try:
                        perms.append(
                            Permission.objects.get(
                                codename=codename,
                                content_type__app_label=model._meta.app_label,
                            )
                        )
                    except Permission.DoesNotExist:
                        self.stderr.write(f"  ! permiso no encontrado: {codename}")
            group.permissions.set(perms)
            estado = "creado" if created else "actualizado"
            self.stdout.write(
                self.style.SUCCESS(f"Rol {estado}: {rol} ({len(perms)} permisos)")
            )
