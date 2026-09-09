"""Genera las facturas de un mes para los clientes que cobran.

    python manage.py generar_facturas                 # mes actual, simula
    python manage.py generar_facturas --commit         # mes actual, aplica
    python manage.py generar_facturas --periodo 2026-09 --commit
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from clientes.models import Cliente
from core.models import Bitacora, registrar
from facturacion.models import Factura


def _dia_valido(anio, mes, dia):
    """Ajusta el día al último del mes si se pasa (ej. 31 en febrero)."""
    dia = max(1, min(int(dia or 1), 28))
    return date(anio, mes, dia)


class Command(BaseCommand):
    help = "Genera las facturas mensuales de los clientes activos/suspendidos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--periodo", help="Mes a facturar en formato AAAA-MM. Por defecto, el mes actual."
        )
        parser.add_argument("--commit", action="store_true", help="Guarda las facturas.")
        parser.add_argument(
            "--monto-defecto", type=float, default=0,
            help="Monto para clientes que no tienen plan asignado.",
        )

    def handle(self, *args, **opts):
        hoy = timezone.localdate()
        if opts["periodo"]:
            try:
                anio, mes = map(int, opts["periodo"].split("-"))
                periodo = date(anio, mes, 1)
            except ValueError:
                raise CommandError("Formato de --periodo inválido. Usa AAAA-MM (ej. 2026-09).")
        else:
            periodo = date(hoy.year, hoy.month, 1)

        commit = opts["commit"]
        clientes = Cliente.objects.filter(
            estado__in=[Cliente.Estado.ACTIVO, Cliente.Estado.SUSPENDIDO]
        ).select_related("plan")

        creadas = existentes = sin_plan = 0
        total = 0

        with transaction.atomic():
            for c in clientes:
                if Factura.objects.filter(cliente=c, periodo=periodo).exists():
                    existentes += 1
                    continue
                monto = c.monto_a_facturar()
                if not c.plan_id and monto == 0:
                    monto = opts["monto_defecto"]
                    sin_plan += 1
                venc = _dia_valido(periodo.year, periodo.month, c.dia_de_pago)
                corte = (
                    _dia_valido(periodo.year, periodo.month, c.dia_de_corte)
                    if c.dia_de_corte else None
                )
                creadas += 1
                total += float(monto)
                if commit:
                    Factura.objects.create(
                        cliente=c, periodo=periodo, monto=monto,
                        detalle=c.detalle_cobro(),
                        vencimiento=venc, corte=corte,
                    )

            if not commit:
                transaction.set_rollback(True)

        resumen = (
            f"periodo={periodo:%Y-%m}  a crear={creadas}  ya existían={existentes}  "
            f"sin plan (monto 0)={sin_plan}  total=${total:,.2f}"
        )
        if commit:
            self.stdout.write(self.style.SUCCESS(f"HECHO. {resumen}"))
            registrar(None, Bitacora.Accion.OTRO, objeto="Generar facturas",
                      detalle=resumen)
        else:
            self.stdout.write(self.style.WARNING(f"SIMULACIÓN — nada se guardó. {resumen}"))
            self.stdout.write("Agrega --commit para aplicar.")
