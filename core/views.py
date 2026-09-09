from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.views.decorators.clickjacking import xframe_options_exempt

from catalogo.models import Plan, Zona
from clientes.models import Cliente
from core.forms import ConfigForm
from core.models import Bitacora, Config


@login_required
def dashboard(request):
    por_estado = {
        row["estado"]: row["n"]
        for row in Cliente.objects.values("estado").annotate(n=Count("id"))
    }
    ctx = {
        "total_clientes": Cliente.objects.count(),
        "activos": por_estado.get(Cliente.Estado.ACTIVO, 0),
        "suspendidos": por_estado.get(Cliente.Estado.SUSPENDIDO, 0),
        "gratis": por_estado.get(Cliente.Estado.GRATIS, 0),
        "cancelados": por_estado.get(Cliente.Estado.CANCELADO, 0),
        "total_zonas": Zona.objects.count(),
        "total_planes": Plan.objects.filter(activo=True).count(),
        "eventos": Bitacora.objects.select_related("usuario")[:15],
    }
    return render(request, "core/dashboard.html", ctx)


@login_required
@permission_required("clientes.change_cliente", raise_exception=True)
def config(request):
    obj = Config.get()
    form = ConfigForm(
        request.POST or None, request.FILES or None, instance=obj
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Configuración guardada.")
        return redirect("config")
    return render(request, "core/config.html", {"form": form})


@xframe_options_exempt
def portal(request):
    """Página pública que ve el cliente suspendido al navegar (redirect del router)."""
    cfg = Config.get()
    ip = request.GET.get("ip") or request.META.get("REMOTE_ADDR", "")
    cliente = Cliente.objects.filter(ip=ip).select_related("plan").first()

    deuda = 0
    facturas = []
    if cliente:
        from facturacion.models import Factura
        facturas = list(
            Factura.objects.filter(cliente=cliente, estado=Factura.Estado.PENDIENTE)
            .order_by("periodo")
        )
        deuda = sum((f.saldo for f in facturas), 0)

    return render(request, "core/portal.html", {
        "cfg": cfg, "ip": ip, "cliente": cliente,
        "deuda": deuda, "facturas": facturas,
        "suspendido": bool(cliente) and cliente.estado == Cliente.Estado.SUSPENDIDO,
    })
