from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalogo.models import Plan, Zona
from clientes.models import Cliente
from core.models import Bitacora


class ClientesFlujoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("init_roles")
        cls.zona = Zona.objects.create(nombre="Centro")
        cls.plan = Plan.objects.create(
            nombre="Hogar 20", mbps_bajada=20, mbps_subida=4, precio_mensual="350.00"
        )
        cls.admin = User.objects.create_user("admin_isp", password="x", is_staff=True)
        cls.admin.groups.add(cls.admin.groups.model.objects.get(name="Administración"))

    def test_lista_requiere_login(self):
        resp = self.client.get(reverse("clientes:lista"))
        self.assertEqual(resp.status_code, 302)

    def test_alta_cliente_crea_bitacora(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("clientes:crear"),
            {
                "nombre": "Juan Pérez",
                "documento": "",
                "telefono": "555",
                "email": "",
                "direccion": "",
                "zona": self.zona.pk,
                "plan": self.plan.pk,
                "ip": "10.0.0.5",
                "dia_de_pago": 10,
                "estado": Cliente.Estado.ACTIVO,
                "fecha_instalacion": "",
                "notas": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        cliente = Cliente.objects.get(nombre="Juan Pérez")
        self.assertEqual(cliente.creado_por, self.admin)
        self.assertTrue(
            Bitacora.objects.filter(
                accion=Bitacora.Accion.CREAR, objeto=f"Cliente #{cliente.pk}"
            ).exists()
        )

    def test_dia_de_pago_invalido(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("clientes:crear"),
            {
                "nombre": "Ana", "telefono": "", "documento": "", "email": "",
                "direccion": "", "zona": "", "plan": "", "ip": "",
                "dia_de_pago": 31, "estado": Cliente.Estado.ACTIVO,
                "fecha_instalacion": "", "notas": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "día entre 1 y 28")

    def test_busqueda_por_ip(self):
        Cliente.objects.create(nombre="Busca IP", ip="192.168.1.50", dia_de_pago=1)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("clientes:lista"), {"q": "192.168.1.50"})
        self.assertContains(resp, "Busca IP")
