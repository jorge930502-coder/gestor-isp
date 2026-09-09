"""Sincroniza los cortes con el Mikrotik.

Para cada router activo:
  - calcula qué clientes deben estar CORTADOS (suspendidos, o con factura
    vencida cuyo día de corte ya pasó),
  - agrega sus IPs a la address-list de morosos del router,
  - quita de esa lista a los que ya no deben,
  - actualiza el estado del cliente (suspendido / activo) en el sistema.

En el Mikrotik debe existir UNA regla de firewall que bloquee esa address-list.

    python manage.py aplicar_cortes                # simula
    python manage.py aplicar_cortes --commit
    python manage.py aplicar_cortes --router REDPUNTO --commit
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from clientes.models import Cliente
from core.models import Bitacora, registrar
from facturacion.models import Factura
from red import mikrotik
from red.models import Router


class Command(BaseCommand):
    help = "Aplica/levanta los cortes en el Mikrotik según la deuda de cada cliente."

    def add_arguments(self, parser):
        parser.add_argument("--router", help="Solo este router (nombre).")
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **opts):
        hoy = timezone.localdate()
        routers = Router.objects.filter(activo=True)
        if opts["router"]:
            routers = routers.filter(nombre__iexact=opts["router"])
        if not routers:
            raise CommandError("No hay routers activos que coincidan.")

        un_solo_router = Router.objects.filter(activo=True).count() == 1
        commit = opts["commit"]

        for router in routers:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n== {router.nombre} ({router.host}) =="))
            try:
                mikrotik.probar_conexion(router)
            except mikrotik.MikrotikError as exc:
                self.stderr.write(self.style.ERROR(f"  Sin conexión: {exc}"))
                continue

            clientes = Cliente.objects.exclude(
                estado__in=[Cliente.Estado.GRATIS, Cliente.Estado.CANCELADO]
            ).exclude(ip__isnull=True)
            if not un_solo_router:
                clientes = clientes.filter(router=router)

            debe_cortado = {}      # ip -> cliente
            for c in clientes:
                moroso = Factura.objects.filter(
                    cliente=c, estado=Factura.Estado.PENDIENTE,
                    corte__isnull=False, corte__lte=hoy,
                ).exists()
                if moroso or c.estado == Cliente.Estado.SUSPENDIDO:
                    debe_cortado[c.ip] = c

            try:
                ya_en_lista = mikrotik.ips_en_lista(router, router.lista_morosos)
            except mikrotik.MikrotikError as exc:
                self.stderr.write(self.style.ERROR(f"  {exc}"))
                continue

            gestionadas = {c.ip for c in clientes}
            a_bloquear = set(debe_cortado) - ya_en_lista
            a_liberar = (ya_en_lista & gestionadas) - set(debe_cortado)

            self.stdout.write(f"  a cortar: {len(a_bloquear)}   a reconectar: {len(a_liberar)}")

            for ip in sorted(a_bloquear):
                c = debe_cortado[ip]
                self.stdout.write(f"    CORTAR   {ip:15} {c.nombre}")
                if commit:
                    mikrotik.bloquear_ip(router, ip, router.lista_morosos, f"corte {c.nombre}")
                    if c.estado != Cliente.Estado.SUSPENDIDO:
                        c.estado = Cliente.Estado.SUSPENDIDO
                        c.save(update_fields=["estado"])
                    registrar(None, Bitacora.Accion.CORTE, objeto=f"Cliente #{c.pk}",
                              detalle=f"Corte automático en {router.nombre} ({ip}).")

            for ip in sorted(a_liberar):
                c = next((x for x in clientes if x.ip == ip), None)
                nombre = c.nombre if c else ip
                self.stdout.write(f"    RECONECTAR {ip:15} {nombre}")
                if commit:
                    mikrotik.desbloquear_ip(router, ip, router.lista_morosos)
                    if c and c.estado == Cliente.Estado.SUSPENDIDO:
                        c.estado = Cliente.Estado.ACTIVO
                        c.save(update_fields=["estado"])
                    if c:
                        registrar(None, Bitacora.Accion.RECONEXION, objeto=f"Cliente #{c.pk}",
                                  detalle=f"Reconexión automática en {router.nombre} ({ip}).")

        if not commit:
            self.stdout.write(self.style.WARNING("\nSIMULACIÓN — nada se aplicó. Agrega --commit."))
        else:
            self.stdout.write(self.style.SUCCESS("\nHecho."))
