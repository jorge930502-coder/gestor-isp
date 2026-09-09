import io
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.management import call_command
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from clientes.models import Cliente
from core.models import Bitacora, registrar

from clientes.models import Cliente as _Cli

from .forms import PagoForm, PagoRapidoForm
from .models import Factura, Pago, ServicioAdicional


def _recalc_pendientes(cliente):
    """Ajusta el monto de las facturas pendientes del cliente a su cobro actual."""
    nuevo = cliente.monto_a_facturar()
    for f in cliente.facturas.filter(estado=Factura.Estado.PENDIENTE):
        if f.monto != nuevo:
            f.monto = nuevo
            f.detalle = cliente.detalle_cobro()
            f.save(update_fields=["monto", "detalle"])
            f.recalcular_estado()


def _aplicar_pago(pago, factura, reactivar, user):
    pago.registrado_por = user
    if factura:
        pago.factura = factura
        pago.cliente = factura.cliente
    pago.save()

    detalle = f"Pago ${pago.monto} de {pago.cliente.nombre} ({pago.get_metodo_display()})"
    if factura:
        factura.recalcular_estado()
        detalle += f" — factura {factura.periodo_texto} [{factura.get_estado_display()}]"

    reactivado = False
    if reactivar and pago.cliente.estado == Cliente.Estado.SUSPENDIDO:
        pago.cliente.estado = Cliente.Estado.ACTIVO
        pago.cliente.save(update_fields=["estado"])
        reactivado = True
        detalle += " — cliente reactivado"

    registrar(user, Bitacora.Accion.PAGO, objeto=f"Cliente #{pago.cliente.pk}", detalle=detalle)
    return reactivado


@login_required
@permission_required("facturacion.add_pago", raise_exception=True)
def registrar_pago(request):
    cliente = None
    factura = None
    if request.GET.get("factura"):
        factura = get_object_or_404(Factura, pk=request.GET["factura"])
        cliente = factura.cliente
    elif request.GET.get("cliente"):
        cliente = get_object_or_404(Cliente, pk=request.GET["cliente"])

    if cliente:
        inicial = {}
        pendiente = (
            factura
            or Factura.objects.filter(
                cliente=cliente, estado=Factura.Estado.PENDIENTE
            ).order_by("periodo").first()
        )
        if pendiente:
            inicial["monto"] = pendiente.saldo
        elif cliente.plan_id:
            inicial["monto"] = cliente.plan.precio_mensual
        form = PagoForm(request.POST or None, initial=inicial)
    else:
        form = PagoRapidoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        pago = form.save(commit=False)
        c = cliente or form.cleaned_data["cliente"]
        pago.cliente = c
        # Si no viene factura por URL, engancha a la factura pendiente más antigua.
        f = factura
        if f is None:
            f = (
                Factura.objects.filter(cliente=c, estado=Factura.Estado.PENDIENTE)
                .order_by("periodo")
                .first()
            )
        reactivado = _aplicar_pago(pago, f, form.cleaned_data.get("reactivar"), request.user)
        messages.success(
            request,
            f"Pago registrado para {c.nombre}." + (" Servicio reactivado." if reactivado else ""),
        )
        return redirect("clientes:detalle", pk=c.pk)

    return render(request, "facturacion/registrar_pago.html", {
        "form": form, "cliente": cliente, "factura": factura,
    })


@login_required
@permission_required("facturacion.add_pago", raise_exception=True)
def pago_lote(request):
    """Marca varios clientes como pagados de una vez (por grupo de día de pago)."""
    hoy = timezone.localdate()
    grupo = request.GET.get("dia", "")

    qs = (
        Factura.objects.select_related("cliente", "cliente__plan")
        .filter(estado=Factura.Estado.PENDIENTE)
        .order_by("cliente__nombre")
    )
    if grupo.isdigit():
        qs = qs.filter(cliente__dia_de_pago=int(grupo))

    if request.method == "POST":
        ids = request.POST.getlist("factura")
        try:
            fecha = timezone.datetime.strptime(request.POST["fecha"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            fecha = hoy
        metodo = request.POST.get("metodo", Pago.Metodo.EFECTIVO)
        reactivar = request.POST.get("reactivar") == "on"
        n = 0
        for f in Factura.objects.filter(pk__in=ids, estado=Factura.Estado.PENDIENTE).select_related("cliente"):
            saldo = f.saldo
            if saldo <= 0:
                continue
            pago = Pago(
                cliente=f.cliente, factura=f, fecha=fecha, monto=saldo,
                metodo=metodo, nota="Pago en lote",
            )
            _aplicar_pago(pago, f, reactivar, request.user)
            n += 1
        messages.success(request, f"{n} pago(s) registrado(s).")
        return redirect(f"{request.path}?dia={grupo}")

    filas = [{"f": f, "saldo": f.saldo} for f in qs]
    return render(request, "facturacion/pago_lote.html", {
        "filas": filas, "grupo": grupo, "hoy": hoy.isoformat(),
        "metodos": Pago.Metodo.choices,
        "total": sum(x["saldo"] for x in filas),
    })


def _next(request, defecto):
    return request.POST.get("next") or request.GET.get("next") or defecto


def _confirmar(request, titulo, mensaje, volver, peligro=True):
    return render(request, "facturacion/confirmar.html", {
        "titulo": titulo, "mensaje": mensaje, "volver": volver, "peligro": peligro,
    })


@login_required
@permission_required("facturacion.add_factura", raise_exception=True)
def adicional_agregar(request, cliente_pk):
    cliente = get_object_or_404(_Cli, pk=cliente_pk)
    if request.method == "POST":
        concepto = (request.POST.get("concepto") or "").strip() or "Televisión"
        try:
            monto = float(request.POST.get("monto") or 0)
        except ValueError:
            monto = 0
        if monto > 0:
            ServicioAdicional.objects.create(cliente=cliente, concepto=concepto, monto=monto)
            _recalc_pendientes(cliente)
            registrar(request.user, Bitacora.Accion.EDITAR, objeto=f"Cliente #{cliente.pk}",
                      detalle=f"Servicio adicional: {concepto} ${monto:g}/mes")
            messages.success(request, f"Agregado: {concepto} ${monto:g}/mes.")
        else:
            messages.warning(request, "Pon un monto mayor a 0.")
    return redirect("clientes:detalle", pk=cliente.pk)


@login_required
@permission_required("facturacion.change_factura", raise_exception=True)
def adicional_eliminar(request, pk):
    a = get_object_or_404(ServicioAdicional, pk=pk)
    cliente = a.cliente
    if request.method == "POST":
        a.delete()
        _recalc_pendientes(cliente)
        registrar(request.user, Bitacora.Accion.EDITAR, objeto=f"Cliente #{cliente.pk}",
                  detalle=f"Quitado servicio adicional: {a.concepto}")
        messages.success(request, "Servicio adicional quitado.")
    return redirect("clientes:detalle", pk=cliente.pk)


@login_required
@permission_required("facturacion.change_factura", raise_exception=True)
def factura_anular(request, pk):
    f = get_object_or_404(Factura, pk=pk)
    volver = _next(request, "facturacion:facturas")
    if request.method != "POST":
        return _confirmar(
            request, "Anular factura",
            f"¿Anular la factura de {f.cliente.nombre} — {f.periodo_texto} (${f.monto})? "
            "Deja de contar como deuda pero queda el registro.",
            volver, peligro=False,
        )
    f.estado = Factura.Estado.ANULADA
    f.save(update_fields=["estado"])
    registrar(request.user, Bitacora.Accion.OTRO, objeto=f"Cliente #{f.cliente_id}",
              detalle=f"Factura {f.periodo_texto} ANULADA (${f.monto}).")
    messages.success(request, f"Factura de {f.cliente.nombre} anulada.")
    return redirect(volver)


@login_required
@permission_required("facturacion.delete_factura", raise_exception=True)
def factura_eliminar(request, pk):
    f = get_object_or_404(Factura, pk=pk)
    volver = _next(request, "facturacion:facturas")
    n_pagos = f.pagos.count()
    if request.method != "POST":
        extra = f" Se borrarán también {n_pagos} pago(s) por ${f.pagado}." if n_pagos else ""
        return _confirmar(
            request, "Eliminar factura",
            f"¿ELIMINAR por completo la factura de {f.cliente.nombre} — "
            f"{f.periodo_texto}?{extra} Esto no se puede deshacer.",
            volver,
        )
    cli, per, pk_cli = f.cliente.nombre, f.periodo_texto, f.cliente_id
    f.pagos.all().delete()
    f.delete()
    extra = f" y {n_pagos} pago(s)" if n_pagos else ""
    registrar(request.user, Bitacora.Accion.ELIMINAR, objeto=f"Cliente #{pk_cli}",
              detalle=f"Factura {per} ELIMINADA{extra}.")
    messages.success(request, f"Factura de {cli} ({per}){extra} eliminada.")
    return redirect(volver)


@login_required
@permission_required("facturacion.delete_pago", raise_exception=True)
def pago_eliminar(request, pk):
    p = get_object_or_404(Pago, pk=pk)
    volver = _next(request, "facturacion:pagos")
    if request.method != "POST":
        return _confirmar(
            request, "Eliminar pago",
            f"¿Eliminar el pago de {p.cliente.nombre} por ${p.monto} del {p.fecha:%d/%m/%Y}? "
            "La factura vuelve a quedar pendiente.",
            volver,
        )
    f = p.factura
    cli, monto, pk_cli = p.cliente.nombre, p.monto, p.cliente_id
    p.delete()
    if f:
        f.recalcular_estado()
    registrar(request.user, Bitacora.Accion.ELIMINAR, objeto=f"Cliente #{pk_cli}",
              detalle=f"Pago de ${monto} ELIMINADO ({cli}).")
    messages.success(request, f"Pago de {cli} (${monto}) eliminado.")
    return redirect(volver)


@login_required
@permission_required("facturacion.view_factura", raise_exception=True)
def factura_detalle(request, pk):
    from core.models import Config
    f = get_object_or_404(
        Factura.objects.select_related("cliente", "cliente__plan", "cliente__zona"), pk=pk
    )
    return render(request, "facturacion/factura_detalle.html", {
        "f": f, "cfg": Config.get(),
        "pagos": f.pagos.select_related("registrado_por").order_by("fecha"),
        "adicionales": f.cliente.adicionales.filter(activo=True),
    })


@login_required
@permission_required("facturacion.view_factura", raise_exception=True)
def facturas(request):
    qs = Factura.objects.select_related("cliente").order_by("-periodo", "cliente__nombre")
    estado = request.GET.get("estado", "")
    q = request.GET.get("q", "").strip()
    if estado == "vencidas":
        qs = qs.filter(estado=Factura.Estado.PENDIENTE, vencimiento__lt=timezone.localdate())
    elif estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(Q(cliente__nombre__icontains=q) | Q(cliente__ip__icontains=q))

    resumen = Factura.objects.aggregate(
        pendiente=Sum("monto", filter=Q(estado=Factura.Estado.PENDIENTE)),
        pagado=Sum("monto", filter=Q(estado=Factura.Estado.PAGADA)),
    )
    return render(request, "facturacion/facturas.html", {
        "facturas": qs[:400],
        "total": qs.count(),
        "estado_sel": estado,
        "q": q,
        "resumen": resumen,
    })


@login_required
@permission_required("facturacion.view_pago", raise_exception=True)
def pagos(request):
    qs = Pago.objects.select_related("cliente", "registrado_por").order_by("-fecha", "-creado")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(cliente__nombre__icontains=q)
    hoy = timezone.localdate()
    mes = Pago.objects.filter(fecha__year=hoy.year, fecha__month=hoy.month).aggregate(
        t=Sum("monto")
    )["t"] or 0
    return render(request, "facturacion/pagos.html", {
        "pagos": qs[:300], "total": qs.count(), "q": q, "mes_total": mes,
    })


@login_required
@permission_required("facturacion.view_factura", raise_exception=True)
def morosos(request):
    hoy = timezone.localdate()
    qs = (
        Factura.objects.select_related("cliente")
        .filter(estado=Factura.Estado.PENDIENTE, vencimiento__lt=hoy)
        .order_by("vencimiento")
    )
    filas = []
    for f in qs:
        filas.append({
            "f": f,
            "dias": (hoy - f.vencimiento).days,
            "para_corte": f.corte and f.corte <= hoy,
        })
    total = qs.aggregate(t=Sum("monto"))["t"] or 0
    return render(request, "facturacion/morosos.html", {
        "filas": filas, "total": total, "n": len(filas),
    })


@login_required
@permission_required("facturacion.change_factura", raise_exception=True)
def recalcular(request):
    if request.method == "POST":
        buf = io.StringIO()
        try:
            call_command("recalcular_facturas", commit=True, stdout=buf, stderr=buf)
            messages.success(request, "Montos de facturas pendientes actualizados al precio del plan.")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"Error: {exc}")
    return redirect("facturacion:facturas")


@login_required
@permission_required("facturacion.add_factura", raise_exception=True)
def generar(request):
    salida = None
    hoy = timezone.localdate()
    periodo_def = f"{hoy.year}-{hoy.month:02d}"
    if request.method == "POST":
        periodo = request.POST.get("periodo") or periodo_def
        commit = request.POST.get("modo") == "generar"
        try:
            monto_defecto = float(request.POST.get("monto_defecto") or 0)
        except ValueError:
            monto_defecto = 0
        buf = io.StringIO()
        try:
            call_command("generar_facturas", periodo=periodo, commit=commit,
                         monto_defecto=monto_defecto, stdout=buf, stderr=buf)
            salida = buf.getvalue()
            if commit:
                messages.success(request, "Facturas generadas.")
        except Exception as exc:  # noqa: BLE001
            salida = buf.getvalue() + f"\n\nERROR: {exc}"
            messages.error(request, f"Error: {exc}")
    return render(request, "facturacion/generar.html", {
        "salida": salida, "periodo_def": periodo_def,
    })
