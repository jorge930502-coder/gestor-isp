import io
import tempfile
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.management import call_command
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Bitacora, Config, registrar

from clientes.models import Cliente

from .forms import ImportarForm, RouterForm
from .mikrotik import (
    MikrotikError, configurar_portal, crear_o_actualizar_cola, listar_queues_simple,
    monitor_trafico, ping_desde_router, probar_conexion,
)
from .models import Router


DEF_PROVEEDOR = "ether1,sfp-sfpplus1"
DEF_CLIENTES = "vlan101,vlan102,vlan103,vlan104"


def _ifaces(router, que):
    txt = router.ifaces_proveedor if que == "proveedor" else router.ifaces_clientes
    txt = txt or (DEF_PROVEEDOR if que == "proveedor" else DEF_CLIENTES)
    return [x.strip() for x in txt.split(",") if x.strip()]


def _mbps_par(v):
    a, _, b = (v or "0/0").partition("/")
    try:
        return int(a) // 1_000_000, int(b) // 1_000_000
    except ValueError:
        return 0, 0


@login_required
@permission_required("clientes.change_cliente", raise_exception=True)
def sincronizar_colas(request):
    """Empuja la velocidad del PLAN del panel a las colas del Mikrotik."""
    salida = []
    aplicado = request.method == "POST" and request.POST.get("modo") == "aplicar"
    solo_sube = request.method == "POST" and request.POST.get("solo_sube") == "1"
    router = Router.objects.filter(activo=True).first()

    if request.method == "POST" and router:
        try:
            qmap = {
                (q.get("target") or "").split(",")[0].split("/")[0]: q.get("max-limit", "")
                for q in listar_queues_simple(router)
            }
        except MikrotikError as exc:
            qmap = {}
            salida.append(f"ERROR leyendo colas: {exc}")

        clientes = (
            Cliente.objects.exclude(estado=Cliente.Estado.CANCELADO)
            .exclude(ip__isnull=True).exclude(plan__isnull=True)
            .select_related("plan").order_by("nombre")
        )
        sube = baja = igual = err = creadas = 0
        for c in clientes:
            r = c.router or router
            nombre = c.nombre_cola or c.nombre
            plan_sub, plan_baj = c.plan.mbps_subida, c.plan.mbps_bajada
            actual = qmap.get(c.ip)
            if actual is None:
                estado_txt = "SIN COLA (se crea)"
                creadas += 1
            else:
                cur_sub, cur_baj = _mbps_par(actual)
                if (cur_sub, cur_baj) == (plan_sub, plan_baj):
                    igual += 1
                    continue
                if plan_baj > cur_baj:
                    estado_txt = f"SUBE  {cur_baj}->{plan_baj} Mbps"
                    sube += 1
                else:
                    if solo_sube:
                        salida.append(f"  {c.nombre[:28]:28} {c.ip:15} (se deja igual: bajaría)")
                        continue
                    estado_txt = f"BAJA  {cur_baj}->{plan_baj} Mbps"
                    baja += 1
            salida.append(f"  {c.nombre[:28]:28} {c.ip:15} {c.plan.nombre:11} {estado_txt}")
            if aplicado:
                try:
                    crear_o_actualizar_cola(r, nombre, c.ip, plan_sub, plan_baj, comentario=c.nombre)
                except MikrotikError as exc:
                    err += 1
                    salida.append(f"      ✖ {exc}")
        resumen = (f"suben={sube} bajan={baja} sin cambio={igual} "
                   f"nuevas={creadas} errores={err}")
        salida.append("")
        salida.append(("APLICADO. " if aplicado else "SIMULACIÓN (no se tocó el router). ") + resumen)
        if aplicado:
            registrar(request.user, Bitacora.Accion.OTRO, objeto="Sincronizar colas",
                      detalle=f"Velocidades del plan aplicadas al router. {resumen}")
            messages.success(request, "Colas sincronizadas con los planes.")

    return render(request, "red/sincronizar_colas.html", {
        "salida": "\n".join(salida), "router": router,
    })


@login_required
@permission_required("red.view_router", raise_exception=True)
def trafico(request):
    router = Router.objects.filter(activo=True).first()
    return render(request, "red/trafico.html", {
        "router": router,
        "ifaces_prov": _ifaces(router, "proveedor") if router else [],
        "ifaces_cli": _ifaces(router, "clientes") if router else [],
    })


@login_required
@permission_required("red.view_router", raise_exception=True)
def trafico_datos(request):
    router = Router.objects.filter(activo=True).first()
    que = request.GET.get("que", "proveedor")
    if router is None:
        return JsonResponse({"error": "No hay router.", "interfaces": []})
    try:
        datos = monitor_trafico(router, _ifaces(router, que))
    except MikrotikError as exc:
        return JsonResponse({"error": str(exc), "interfaces": []})
    # En las VLAN de clientes, lo que "baja" el cliente es el tx del router.
    if que == "clientes":
        for d in datos:
            d["rx_bps"], d["tx_bps"] = d["tx_bps"], d["rx_bps"]
    total_rx = sum(d["rx_bps"] for d in datos)
    total_tx = sum(d["tx_bps"] for d in datos)
    return JsonResponse({"interfaces": datos, "total_rx": total_rx, "total_tx": total_tx})


@login_required
@permission_required("red.view_router", raise_exception=True)
def routers(request):
    return render(request, "red/routers.html", {"routers": Router.objects.all()})


@login_required
@permission_required("red.add_router", raise_exception=True)
def router_form(request, pk=None):
    obj = get_object_or_404(Router, pk=pk) if pk else None
    form = RouterForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        r = form.save()
        registrar(
            request.user,
            Bitacora.Accion.EDITAR if obj else Bitacora.Accion.CREAR,
            objeto=f"Router #{r.pk}", detalle=f"{'Edición' if obj else 'Alta'} de router {r.nombre}",
        )
        messages.success(request, "Router guardado.")
        return redirect("red:routers")
    return render(request, "red/router_form.html", {"form": form, "obj": obj})


@login_required
@permission_required("red.view_router", raise_exception=True)
def router_probar(request, pk):
    r = get_object_or_404(Router, pk=pk)
    try:
        info = probar_conexion(r)
        messages.success(
            request,
            f"Conexión OK con {r.nombre}: {info['identidad']} (RouterOS {info['version']}).",
        )
    except MikrotikError as exc:
        messages.error(request, f"No se pudo conectar a {r.nombre}: {exc}")
    return redirect("red:routers")


@login_required
@permission_required("red.change_router", raise_exception=True)
def configurar_portal_router(request):
    """Deja los routers activos listos para redirigir a los morosos al portal."""
    cfg = Config.get()
    host = cfg.portal_host.strip()
    salida = []
    if request.method == "POST":
        if not host:
            messages.error(request, "Falta la 'dirección del portal' en Configuración.")
            return redirect("config")
        for r in Router.objects.filter(activo=True):
            salida.append(f"== {r.nombre} ({r.host}) ==")
            try:
                ping = ping_desde_router(r, host.split(":")[0])
                salida.append(
                    f"  ping a {host.split(':')[0]}: {ping['recibidos']}/{ping['enviados']} "
                    f"respuestas" + (f", {ping['promedio_ms']}" if ping['promedio_ms'] else "")
                )
                if ping["recibidos"] == 0:
                    salida.append("  ⚠ el router NO alcanza esa IP. Revisa la red antes de seguir.")
                acciones = configurar_portal(r, host, r.lista_morosos)
                salida += [f"  ✔ {a}" for a in acciones]
            except MikrotikError as exc:
                salida.append(f"  ✖ {exc}")
        registrar(request.user, Bitacora.Accion.OTRO, objeto="Portal cautivo",
                  detalle="Configuración del portal aplicada a los routers.")
        messages.success(request, "Configuración del portal aplicada. Revisa el detalle.")
    return render(request, "red/configurar_portal.html", {"salida": "\n".join(salida), "host": host})


@login_required
@permission_required("clientes.change_cliente", raise_exception=True)
def sincronizar_cortes(request):
    salida = None
    if request.method == "POST":
        commit = request.POST.get("modo") == "aplicar"
        buf = io.StringIO()
        try:
            call_command("aplicar_cortes", commit=commit, stdout=buf, stderr=buf)
            salida = buf.getvalue()
            if commit:
                messages.success(request, "Cortes sincronizados con el/los router(s).")
        except Exception as exc:  # noqa: BLE001
            salida = buf.getvalue() + f"\n\nERROR: {exc}"
            messages.error(request, f"Error: {exc}")
    return render(request, "red/sincronizar_cortes.html", {"salida": salida})


@login_required
@permission_required("clientes.add_cliente", raise_exception=True)
def importar(request):
    form = ImportarForm(request.POST or None, request.FILES or None)
    salida = None
    modo = None

    if request.method == "POST" and form.is_valid():
        modo = request.POST.get("modo", "simular")
        commit = modo == "importar"

        kwargs = {
            "fuente": form.cleaned_data["fuente"],
            "crear_planes": form.cleaned_data["crear_planes"],
            "commit": commit,
        }
        tmp_path = None
        if form.cleaned_data.get("archivo"):
            f = form.cleaned_data["archivo"]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".rsc")
            for chunk in f.chunks():
                tmp.write(chunk)
            tmp.close()
            tmp_path = tmp.name
            kwargs["archivo"] = tmp_path
        else:
            kwargs["router"] = str(form.cleaned_data["router"].pk)

        buf = io.StringIO()
        try:
            call_command("importar_mikrotik", stdout=buf, stderr=buf, **kwargs)
            salida = buf.getvalue()
            if commit:
                registrar(
                    request.user, Bitacora.Accion.OTRO,
                    objeto="Importación Mikrotik",
                    detalle=f"Fuente {kwargs['fuente']} (vía panel).",
                )
                messages.success(request, "Importación aplicada. Revisa el detalle abajo.")
        except Exception as exc:  # noqa: BLE001 - mostrar el error al usuario
            salida = buf.getvalue() + f"\n\nERROR: {exc}"
            messages.error(request, f"Falló la importación: {exc}")
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    return render(
        request, "red/importar.html",
        {"form": form, "salida": salida, "modo": modo},
    )
