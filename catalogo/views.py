from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Bitacora, registrar

from .forms import PlanForm, ZonaForm
from .models import Plan, Zona


# ---------------- Planes ----------------

@login_required
@permission_required("catalogo.view_plan", raise_exception=True)
def planes(request):
    qs = list(Plan.objects.annotate(n_clientes=Count("clientes")).order_by("nombre"))
    total_clientes = total_ingreso = 0
    for p in qs:
        p.ingreso_mes = p.n_clientes * p.precio_mensual
        total_clientes += p.n_clientes
        total_ingreso += p.ingreso_mes
    return render(request, "catalogo/planes.html", {
        "planes": qs, "total_clientes": total_clientes, "total_ingreso": total_ingreso,
    })


@login_required
@permission_required("catalogo.add_plan", raise_exception=True)
def plan_form(request, pk=None):
    obj = get_object_or_404(Plan, pk=pk) if pk else None
    form = PlanForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        cambio_velocidad = obj and (
            "mbps_bajada" in form.changed_data or "mbps_subida" in form.changed_data
        )
        p = form.save()
        registrar(request.user, Bitacora.Accion.EDITAR if obj else Bitacora.Accion.CREAR,
                  objeto=f"Plan {p.nombre}", detalle=f"{'Edición' if obj else 'Alta'} de plan.")
        messages.success(request, "Plan guardado.")

        if cambio_velocidad:
            from clientes.views import sincronizar_cola_cliente
            n = err = 0
            for c in p.clientes.exclude(estado="cancelado").select_related("router"):
                ok, e = sincronizar_cola_cliente(c, request.user)
                if ok:
                    n += 1
                elif e:
                    err += 1
            if n or err:
                messages.info(
                    request,
                    f"Se actualizó la velocidad en el router de {n} cliente(s)"
                    + (f", {err} con error" if err else "") + ".",
                )
        return redirect("catalogo:planes")
    return render(request, "catalogo/plan_form.html", {"form": form, "obj": obj})


@login_required
@permission_required("catalogo.delete_plan", raise_exception=True)
def plan_eliminar(request, pk):
    p = get_object_or_404(Plan, pk=pk)
    n = p.clientes.count()
    if request.method != "POST":
        if n:
            mensaje = (
                f"El plan «{p.nombre}» está asignado a {n} cliente(s). "
                "Primero cámbiales el plan; después podrás eliminarlo."
            )
            return render(request, "catalogo/confirmar.html", {
                "titulo": "No se puede eliminar", "mensaje": mensaje,
                "volver": "catalogo:planes", "solo_volver": True,
            })
        return render(request, "catalogo/confirmar.html", {
            "titulo": "Eliminar plan",
            "mensaje": f"¿Eliminar el plan «{p.nombre}»? No se puede deshacer.",
            "volver": "catalogo:planes",
        })
    if n == 0:
        nombre = p.nombre
        p.delete()
        registrar(request.user, Bitacora.Accion.ELIMINAR, objeto=f"Plan {nombre}",
                  detalle="Plan eliminado.")
        messages.success(request, f"Plan «{nombre}» eliminado.")
    else:
        messages.error(request, "No se pudo eliminar: el plan tiene clientes.")
    return redirect("catalogo:planes")


# ---------------- Zonas ----------------

@login_required
@permission_required("catalogo.view_zona", raise_exception=True)
def zonas(request):
    qs = Zona.objects.annotate(n_clientes=Count("clientes")).order_by("nombre")
    return render(request, "catalogo/zonas.html", {"zonas": qs})


@login_required
@permission_required("catalogo.add_zona", raise_exception=True)
def zona_form(request, pk=None):
    obj = get_object_or_404(Zona, pk=pk) if pk else None
    form = ZonaForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        z = form.save()
        registrar(request.user, Bitacora.Accion.EDITAR if obj else Bitacora.Accion.CREAR,
                  objeto=f"Zona {z.nombre}", detalle=f"{'Edición' if obj else 'Alta'} de zona.")
        messages.success(request, "Zona guardada.")
        return redirect("catalogo:zonas")
    return render(request, "catalogo/zona_form.html", {"form": form, "obj": obj})


@login_required
@permission_required("catalogo.delete_zona", raise_exception=True)
def zona_eliminar(request, pk):
    z = get_object_or_404(Zona, pk=pk)
    n = z.clientes.count()
    if request.method != "POST":
        if n:
            return render(request, "catalogo/confirmar.html", {
                "titulo": "No se puede eliminar",
                "mensaje": f"La zona «{z.nombre}» tiene {n} cliente(s). Reasígnalos primero.",
                "volver": "catalogo:zonas", "solo_volver": True,
            })
        return render(request, "catalogo/confirmar.html", {
            "titulo": "Eliminar zona",
            "mensaje": f"¿Eliminar la zona «{z.nombre}»?",
            "volver": "catalogo:zonas",
        })
    if n == 0:
        nombre = z.nombre
        z.delete()
        registrar(request.user, Bitacora.Accion.ELIMINAR, objeto=f"Zona {nombre}",
                  detalle="Zona eliminada.")
        messages.success(request, f"Zona «{nombre}» eliminada.")
    return redirect("catalogo:zonas")
