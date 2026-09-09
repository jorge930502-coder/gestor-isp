"""Carga datos de ejemplo para probar el sistema.

    python manage.py seed_demo
"""

import random
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from catalogo.models import Plan, Zona
from clientes.models import Cliente

NOMBRES = [
    "María López", "Juan Pérez", "Carlos Ramírez", "Ana Torres", "Luis Gómez",
    "Sofía Hernández", "Pedro Sánchez", "Lucía Díaz", "Miguel Castro", "Elena Ruiz",
    "Jorge Morales", "Paula Vargas", "Diego Flores", "Carmen Ortiz", "Andrés Silva",
]


class Command(BaseCommand):
    help = "Crea zonas, planes, usuarios y clientes de ejemplo."

    def handle(self, *args, **options):
        zonas = []
        for n in ["Centro", "Norte", "Sur", "El Mirador", "La Loma"]:
            z, _ = Zona.objects.get_or_create(nombre=n)
            zonas.append(z)

        planes = []
        for nombre, dn, up, precio in [
            ("Básico 10", 10, 2, "250.00"),
            ("Hogar 20", 20, 4, "350.00"),
            ("Plus 50", 50, 10, "550.00"),
            ("Pro 100", 100, 20, "850.00"),
        ]:
            p, _ = Plan.objects.get_or_create(
                nombre=nombre,
                defaults=dict(mbps_bajada=dn, mbps_subida=up, precio_mensual=precio),
            )
            planes.append(p)

        # Usuarios de ejemplo por rol
        for username, rol in [("admin_isp", "Administración"), ("cobranza1", "Cobranza"), ("soporte1", "Soporte")]:
            user, created = User.objects.get_or_create(
                username=username, defaults={"is_staff": True}
            )
            if created:
                user.set_password("demo12345")
                user.save()
            try:
                user.groups.add(Group.objects.get(name=rol))
            except Group.DoesNotExist:
                self.stderr.write("Ejecuta primero: python manage.py init_roles")

        if Cliente.objects.exists():
            self.stdout.write("Ya hay clientes; no se agregan más.")
            return

        estados = (
            [Cliente.Estado.ACTIVO] * 7
            + [Cliente.Estado.SUSPENDIDO] * 2
            + [Cliente.Estado.GRATIS]
        )
        base_ip = 100
        for i, nombre in enumerate(NOMBRES):
            Cliente.objects.create(
                nombre=nombre,
                telefono=f"55-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                direccion=f"Calle {random.randint(1, 40)} #{random.randint(1, 200)}",
                zona=random.choice(zonas),
                plan=random.choice(planes),
                ip=f"10.0.0.{base_ip + i}",
                dia_de_pago=random.choice([1, 5, 10, 15, 20]),
                estado=random.choice(estados),
                fecha_instalacion=date.today() - timedelta(days=random.randint(30, 900)),
            )
        self.stdout.write(self.style.SUCCESS(f"Creados {len(NOMBRES)} clientes de ejemplo."))
        self.stdout.write("Usuarios: admin_isp / cobranza1 / soporte1  (contraseña: demo12345)")
