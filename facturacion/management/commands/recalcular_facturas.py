"""Ajusta el monto de las facturas PENDIENTES al precio del plan actual del cliente.

    python manage.py recalcular_facturas                  # todas las pendientes, simula
    python manage.py recalcular_facturas --commit
    python manage.py recalcular_facturas --periodo 2026-09 --commit

Las facturas pagadas o anuladas no se tocan.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Bitacora, registrar
from facturacion.models import Factura


class Command(BaseCommand):
    help = "Pone el monto de las facturas pendientes al precio del plan del cliente."

    def add_arguments(self, parser):
        parser.add_argument("--periodo", help="Solo ese mes, formato AAAA-MM.")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument(
            "--monto-defecto", type=float, default=0,
            help="Monto para clientes sin plan (por defecto 0).",
        )

    def handle(self, *args, **opts):
        qs = Factura.objects.filter(estado=Factura.Estado.PENDIENTE).select_related(
            "cliente", "cliente__plan"
        )
        if opts["periodo"]:
            try:
                a, m = map(int, opts["periodo"].split("-"))
                qs = qs.filter(periodo=date(a, m, 1))
            except ValueError:
                raise CommandError("Formato de --periodo inválido. Usa AAAA-MM.")

        cambiadas = 0
        with transaction.atomic():
            for f in qs:
                nuevo = f.cliente.monto_a_facturar()
                if nuevo == 0 and not f.cliente.plan_id:
                    nuevo = opts["monto_defecto"]
                if f.monto != nuevo:
                    self.stdout.write(
                        f"  {f.cliente.nombre[:30]:30} {f.periodo_texto}: "
                        f"${f.monto} -> ${nuevo}"
                    )
                    cambiadas += 1
                    if opts["commit"]:
                        f.monto = nuevo
                        f.detalle = f.cliente.detalle_cobro()
                        f.save(update_fields=["monto", "detalle"])
                        f.recalcular_estado()
            if not opts["commit"]:
                transaction.set_rollback(True)

        if opts["commit"]:
            self.stdout.write(self.style.SUCCESS(f"HECHO. {cambiadas} facturas ajustadas."))
            registrar(None, Bitacora.Accion.OTRO, objeto="Recalcular facturas",
                      detalle=f"{cambiadas} facturas pendientes ajustadas al precio del plan.")
        else:
            self.stdout.write(self.style.WARNING(
                f"SIMULACIÓN — {cambiadas} facturas cambiarían. Agrega --commit."
            ))
