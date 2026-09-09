from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Exists, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from facturacion.models import Factura

from core.models import registrar, Bitacora
from catalogo.models import Plan, Zona
from red.mikrotik import (
    MikrotikError, crear_o_actualizar_cola, estado_conexiones, monitor_cola,
)
from red.models import Router

from .forms import ClienteForm
from .models import Cliente


def _fmt_bps(bps):
    for unidad, factor in (("Gbps", 1e9), ("Mbps", 1e6), ("Kbps", 1e3)):
        if bps >= factor:
            return f"{bps / factor:.2f} {unidad}"
    return f"{bps:.0f} bps"


def _fmt_bytes(n):
    for unidad, factor in (("TB", 2**40), ("GB", 2**30), ("MB", 2**20), ("KB", 2**10)):
        if n >= factor:
            return f"{n / factor:.2f} {unidad}"
    return f"{n} B"


def sincronizar_cola_cliente(cliente, user):
    """Crea/actualiza la cola simple del cliente en su router.

    Devuelve (ok_msg, error_msg). Ambos None si faltan datos (silencioso).
    Nunca lanza: si el router falla, devuelve error_msg para avisar sin romper.
    """
    if cliente.estado == Cliente.Estado.CANCELADO:
        return None, None
    router = cliente.router or Router.objects.filter(activo=True).first()
    if not (cliente.ip and cliente.plan_id and router):
        return None, None
    nombre_cola = cliente.nombre_cola or cliente.nombre
    try:
        estado, detalle = crear_o_actualizar_cola(
            router, nombre_cola, cliente.ip,
            cliente.plan.mbps_subida, cliente.plan.mbps_bajada,
            comentario=cliente.nombre,
        )
        if not cliente.nombre_cola:
            cliente.nombre_cola = nombre_cola
            cliente.save(update_fields=["nombre_cola"])
        registrar(user, Bitacora.Accion.OTRO, objeto=f"Cliente #{cliente.pk}",
                  detalle=f"Cola {estado} en {router.nombre}: {detalle}")
        return f"Cola {estado} en {router.nombre}: {detalle}", None
    except MikrotikError as exc:
        return None, f"El cliente se guardó, pero no se pudo enviar la cola al router: {exc}"


@login_required
@permission_required("clientes.change_cliente", raise_exception=True)
def asignar_lote(request):
    """Asigna zona / router / plan a varios clientes de una vez."""
    qs = Cliente.objects.select_related("zona", "plan", "router").order_by("nombre")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(ip__icontains=q) | Q(nombre_cola__icontains=q))
    f_zona = request.GET.get("zona", "")
    if f_zona == "sin":
        qs = qs.filter(zona__isnull=True)
    elif f_zona:
        qs = qs.filter(zona_id=f_zona)
    f_router = request.GET.get("router", "")
    if f_router == "sin":
        qs = qs.filter(router__isnull=True)
    elif f_router:
        qs = qs.filter(router_id=f_router)
    if request.GET.get("estado"):
        qs = qs.filter(estado=request.GET["estado"])

    if request.method == "POST" and request.POST.get("accion") == "zona_por_ip":
        import ipaddress
        redes = []
        for z in Zona.objects.exclude(red_cidr=""):
            try:
                redes.append((ipaddress.ip_network(z.red_cidr, strict=False), z))
            except ValueError:
                pass
        n = 0
        for c in Cliente.objects.exclude(ip__isnull=True):
            ipobj = ipaddress.ip_address(c.ip)
            for net, z in redes:
                if ipobj in net and c.zona_id != z.pk:
                    c.zona = z
                    c.save(update_fields=["zona"])
                    n += 1
                    break
        registrar(request.user, Bitacora.Accion.EDITAR, objeto="Asignación en lote",
                  detalle=f"Zona asignada por subred de IP a {n} clientes.")
        messages.success(request, f"Zona asignada automáticamente a {n} cliente(s) según su IP.")
        return redirect(f"{request.path}?{request.GET.urlencode()}")

    if request.method == "POST":
        ids = request.POST.getlist("cliente")
        seleccion = Cliente.objects.filter(pk__in=ids)
        cambios = {}
        if request.POST.get("set_zona"):
            cambios["zona"] = get_object_or_404(Zona, pk=request.POST["set_zona"])
        if request.POST.get("set_router"):
            cambios["router"] = get_object_or_404(Router, pk=request.POST["set_router"])
        if request.POST.get("set_plan"):
            cambios["plan"] = get_object_or_404(Plan, pk=request.POST["set_plan"])
        if not cambios:
            messages.warning(request, "Elige al menos qué asignar (zona, router o plan).")
        elif not ids:
            messages.warning(request, "No marcaste ningún cliente.")
        else:
            n = seleccion.update(**{k: v.pk for k, v in cambios.items()})
            # si cambió el plan, reajustar facturas pendientes
            if "plan" in cambios:
                for c in seleccion:
                    for fac in c.facturas.filter(estado="pendiente"):
                        if fac.monto != cambios["plan"].precio_mensual:
                            fac.monto = cambios["plan"].precio_mensual
                            fac.save(update_fields=["monto"])
            detalle = ", ".join(f"{k}={v}" for k, v in cambios.items())
            registrar(request.user, Bitacora.Accion.EDITAR, objeto="Asignación en lote",
                      detalle=f"{n} clientes: {detalle}")
            messages.success(request, f"{n} cliente(s) actualizado(s): {detalle}.")
        return redirect(f"{request.path}?{request.GET.urlencode()}")

    return render(request, "clientes/asignar_lote.html", {
        "clientes": qs[:500], "total": qs.count(),
        "zonas": Zona.objects.all(), "routers": Router.objects.filter(activo=True),
        "planes": Plan.objects.filter(activo=True), "estados": Cliente.Estado.choices,
        "q": q, "f_zona": f_zona, "f_router": f_router,
        "estado_sel": request.GET.get("estado", ""),
    })


@login_required
@permission_required("clientes.view_cliente", raise_exception=True)
def ips_libres(request):
    """Devuelve las IPs libres de la subred de una zona (JSON)."""
    zona = get_object_or_404(Zona, pk=request.GET.get("zona"))
    todas = zona.ips_del_rango()
    if not todas:
        return JsonResponse({
            "zona": zona.nombre, "error": "La zona no tiene una red/subred configurada.",
            "libres": [], "total": 0, "usadas": 0,
        })
    excluir = set(request.GET.get("actual", "").split(",")) if request.GET.get("actual") else set()
    if zona.gateway:
        excluir.add(zona.gateway)
    usadas = set(
        Cliente.objects.exclude(ip__isnull=True).values_list("ip", flat=True)
    ) - excluir
    libres = [ip for ip in todas if ip not in usadas]
    return JsonResponse({
        "zona": zona.nombre,
        "libres": libres[:400],
        "total": len(todas),
        "usadas": len(todas) - len(libres),
    })


def _tel_wa(telefono):
    """Normaliza un teléfono a formato wa.me (con indicativo 57)."""
    n = "".join(ch for ch in (telefono or "") if ch.isdigit())
    if len(n) == 10 and n[0] == "3":
        n = "57" + n
    return n


@login_required
@permission_required("clientes.view_cliente", raise_exception=True)
def whatsapp_cobro(request, pk):
    """Envía (o abre) un mensaje de cobro por WhatsApp para el cliente."""
    from urllib.parse import quote

    from core.models import Config
    from core.whatsapp_api import WhatsAppError, enviar_texto
    from facturacion.models import Factura

    cliente = get_object_or_404(Cliente, pk=pk)
    tel = _tel_wa(cliente.telefono)
    if not tel:
        messages.error(request, f"{cliente.nombre} no tiene teléfono cargado.")
        return redirect("clientes:detalle", pk=pk)

    factura = (
        Factura.objects.filter(cliente=cliente, estado=Factura.Estado.PENDIENTE)
        .order_by("periodo").first()
    )
    cfg = Config.get()
    texto = cfg.texto_whatsapp(cliente, factura)

    if cfg.wa_api_lista:
        try:
            enviar_texto(cfg.wa_phone_id, cfg.wa_api_token, tel, texto)
            registrar(request.user, Bitacora.Accion.OTRO, objeto=f"Cliente #{cliente.pk}",
                      detalle="WhatsApp de cobro ENVIADO por la API.")
            messages.success(request, f"WhatsApp enviado a {cliente.nombre}.")
        except WhatsAppError as exc:
            messages.error(request, f"No se pudo enviar: {exc}")
        return redirect("clientes:detalle", pk=pk)

    registrar(request.user, Bitacora.Accion.OTRO, objeto=f"Cliente #{cliente.pk}",
              detalle="Se abrió WhatsApp de cobro.")
    return redirect(f"https://wa.me/{tel}?text={quote(texto)}")


@login_required
@permission_required("clientes.change_cliente", raise_exception=True)
def cambiar_estado(request, pk):
    """Suspende o reactiva a un cliente a mano (solo en el sistema, no toca el router)."""
    cliente = get_object_or_404(Cliente, pk=pk)
    nuevo = request.GET.get("a") or request.POST.get("a")
    if nuevo not in (Cliente.Estado.SUSPENDIDO, Cliente.Estado.ACTIVO):
        messages.error(request, "Estado no válido.")
        return render(request, "clientes/confirmar.html", {
            "titulo": "Error", "mensaje": "Acción no válida.",
            "volver_url": cliente.get_absolute_url(),
        })

    if request.method != "POST":
        verbo = "suspender" if nuevo == Cliente.Estado.SUSPENDIDO else "reactivar"
        return render(request, "clientes/confirmar.html", {
            "titulo": f"{verbo.capitalize()} cliente",
            "mensaje": (
                f"¿{verbo.capitalize()} a {cliente.nombre} en el sistema? "
                "Esto NO corta el internet en el Mikrotik; eso lo haces aparte "
                "(o con Sincronizar cortes si el router está conectado)."
            ),
            "volver_url": cliente.get_absolute_url(),
        })

    anterior = cliente.estado
    cliente.estado = nuevo
    cliente.save(update_fields=["estado"])
    accion = Bitacora.Accion.CORTE if nuevo == Cliente.Estado.SUSPENDIDO else Bitacora.Accion.RECONEXION
    registrar(request.user, accion, objeto=f"Cliente #{cliente.pk}",
              detalle=f"Cambio manual de estado: {anterior} → {nuevo}.")
    messages.success(
        request,
        f"{cliente.nombre} quedó como "
        f"{'Suspendido' if nuevo == Cliente.Estado.SUSPENDIDO else 'Activo'}.",
    )
    return redirect(cliente.get_absolute_url())


@login_required
@permission_required("clientes.change_cliente", raise_exception=True)
def enviar_al_router(request, pk):
    """Crea o actualiza la cola simple del cliente en su Mikrotik."""
    cliente = get_object_or_404(Cliente, pk=pk)
    router = cliente.router or Router.objects.filter(activo=True).first()
    problema = None
    if not cliente.ip:
        problema = "El cliente no tiene IP asignada."
    elif not cliente.plan_id:
        problema = "El cliente no tiene plan (no se sabe la velocidad)."
    elif router is None:
        problema = "No hay un router configurado."

    if request.method != "POST":
        if problema:
            return render(request, "clientes/confirmar.html", {
                "titulo": "No se puede enviar", "mensaje": problema,
                "volver_url": cliente.get_absolute_url(),
            })
        nombre_cola = cliente.nombre_cola or cliente.nombre
        return render(request, "clientes/confirmar.html", {
            "titulo": "Enviar al router",
            "mensaje": (
                f"¿Crear/actualizar la cola de {cliente.nombre} en {router.nombre}? "
                f"Cola: {nombre_cola} · IP {cliente.ip} · "
                f"{cliente.plan.mbps_bajada}/{cliente.plan.mbps_subida} Mbps."
            ),
            "volver_url": cliente.get_absolute_url(),
        })

    if problema:
        messages.error(request, problema)
        return redirect(cliente.get_absolute_url())

    ok, err = sincronizar_cola_cliente(cliente, request.user)
    if ok:
        messages.success(request, ok)
    elif err:
        messages.error(request, err)
    return redirect(cliente.get_absolute_url())


@login_required
@permission_required("clientes.view_cliente", raise_exception=True)
def consumo(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    router = cliente.router or Router.objects.filter(activo=True).first()
    error = None
    if not cliente.ip:
        error = "El cliente no tiene IP asignada."
    elif router is None:
        error = "No hay un router configurado. Ve a Red → Routers."
    return render(request, "clientes/consumo.html", {
        "cliente": cliente, "router": router, "error": error,
    })


@login_required
@permission_required("clientes.view_cliente", raise_exception=True)
def en_linea(request):
    """Muestra qué clientes están en línea (según ARP) y cuáles no."""
    router = Router.objects.filter(activo=True).first()
    filas = []
    error = None
    n_on = n_off = 0
    if router is None:
        error = "No hay un router configurado."
    else:
        try:
            estado = estado_conexiones(router)
        except MikrotikError as exc:
            estado = {}
            error = str(exc)
        clientes = (
            Cliente.objects.exclude(estado=Cliente.Estado.CANCELADO)
            .exclude(ip__isnull=True)
            .select_related("zona")
            .order_by("nombre")
        )
        for c in clientes:
            e = estado.get(c.ip, {"en_linea": False, "arp": "", "bytes_baj": 0, "bytes_sub": 0})
            if e["en_linea"]:
                n_on += 1
            else:
                n_off += 1
            filas.append({
                "c": c,
                "en_linea": e["en_linea"],
                "arp": e["arp"] or "sin ARP",
                "baj": _fmt_bytes(e["bytes_baj"]),
                "sub": _fmt_bytes(e["bytes_sub"]),
            })
        # los desconectados primero
        filas.sort(key=lambda x: (x["en_linea"], x["c"].nombre))
    return render(request, "clientes/en_linea.html", {
        "filas": filas, "error": error, "n_on": n_on, "n_off": n_off,
    })


@login_required
@permission_required("clientes.view_cliente", raise_exception=True)
def consumo_datos(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    router = cliente.router or Router.objects.filter(activo=True).first()
    if not cliente.ip or router is None:
        return JsonResponse({"error": "Falta IP o router."})
    try:
        c = monitor_cola(router, cliente.ip)
    except MikrotikError as exc:
        return JsonResponse({"error": str(exc)})
    return JsonResponse({
        "cola": c["nombre"],
        "bajada_bps": c["bajada_bps"],
        "subida_bps": c["subida_bps"],
        "total_bajada": _fmt_bytes(c["total_bajada_bytes"]),
        "total_subida": _fmt_bytes(c["total_subida_bytes"]),
        "deshabilitada": c["deshabilitada"],
    })


class ClienteListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Cliente
    permission_required = "clientes.view_cliente"
    paginate_by = 25
    context_object_name = "clientes"
    template_name = "clientes/cliente_list.html"

    def get_queryset(self):
        qs = (
            Cliente.objects.select_related("zona", "plan")
            .order_by("nombre")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q)
                | Q(documento__icontains=q)
                | Q(telefono__icontains=q)
                | Q(email__icontains=q)
                | Q(ip__icontains=q)
                | Q(direccion__icontains=q)
            )
        estado = self.request.GET.get("estado", "").strip()
        if estado:
            qs = qs.filter(estado=estado)
        zona = self.request.GET.get("zona", "").strip()
        if zona:
            qs = qs.filter(zona_id=zona)
        plan = self.request.GET.get("plan", "").strip()
        if plan:
            qs = qs.filter(plan_id=plan)

        hoy = timezone.localdate()
        periodo = date(hoy.year, hoy.month, 1)
        pendiente_mes = Factura.objects.filter(
            cliente=OuterRef("pk"), periodo=periodo, estado=Factura.Estado.PENDIENTE
        )
        qs = qs.annotate(_debe_mes=Exists(pendiente_mes))

        pago = self.request.GET.get("pago", "").strip()
        if pago == "debe":
            qs = qs.filter(
                Q(_debe_mes=True) | Q(estado=Cliente.Estado.SUSPENDIDO)
            )
        elif pago == "al_dia":
            qs = qs.filter(_debe_mes=False).exclude(estado=Cliente.Estado.SUSPENDIDO)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["estado_sel"] = self.request.GET.get("estado", "")
        ctx["zona_sel"] = self.request.GET.get("zona", "")
        ctx["plan_sel"] = self.request.GET.get("plan", "")
        ctx["estados"] = Cliente.Estado.choices
        ctx["zonas"] = Zona.objects.all()
        ctx["planes"] = Plan.objects.all()
        ctx["total"] = self.get_queryset().count()
        ctx["pago_sel"] = self.request.GET.get("pago", "")

        # Estado de pago del mes actual, para el semáforo de la lista.
        hoy = timezone.localdate()
        periodo = date(hoy.year, hoy.month, 1)
        page_clientes = list(ctx["clientes"])
        facturas = {
            f.cliente_id: f
            for f in Factura.objects.filter(
                periodo=periodo, cliente__in=page_clientes
            )
        }
        for c in page_clientes:
            f = facturas.get(c.id)
            debe = f is not None and f.estado == Factura.Estado.PENDIENTE
            if c.estado == Cliente.Estado.SUSPENDIDO:
                c.pago_mes = "suspendido"
            elif debe:
                c.pago_mes = "pendiente"
            else:
                c.pago_mes = "al_dia"
            c.factura_mes = f

        # Preserva filtros en la paginación
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class ClienteDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Cliente
    permission_required = "clientes.view_cliente"
    context_object_name = "cliente"
    template_name = "clientes/cliente_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["eventos"] = Bitacora.objects.filter(
            objeto=f"Cliente #{self.object.pk}"
        )[:20]
        facturas = list(self.object.facturas.all()[:12])
        ctx["facturas"] = facturas
        ctx["pagos"] = self.object.pagos.select_related("registrado_por")[:10]
        ctx["saldo"] = sum(
            (f.saldo for f in facturas if f.estado == f.Estado.PENDIENTE), 0
        )
        return ctx


class ClienteCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    permission_required = "clientes.add_cliente"
    template_name = "clientes/cliente_form.html"

    def form_valid(self, form):
        form.instance.creado_por = self.request.user
        response = super().form_valid(form)
        registrar(
            self.request.user, Bitacora.Accion.CREAR,
            objeto=f"Cliente #{self.object.pk}",
            detalle=f"Alta de cliente: {self.object.nombre}",
        )
        messages.success(self.request, "Cliente creado.")
        ok, err = sincronizar_cola_cliente(self.object, self.request.user)
        if ok:
            messages.success(self.request, ok)
        elif err:
            messages.warning(self.request, err)
        return response


class ClienteUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Cliente
    form_class = ClienteForm
    permission_required = "clientes.change_cliente"
    template_name = "clientes/cliente_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        cambios = ", ".join(form.changed_data) or "sin cambios"
        registrar(
            self.request.user, Bitacora.Accion.EDITAR,
            objeto=f"Cliente #{self.object.pk}",
            detalle=f"Edición de {self.object.nombre}. Campos: {cambios}",
        )
        msg = "Cambios guardados."
        if "plan" in form.changed_data or "estado" in form.changed_data:
            nuevo_monto = self.object.monto_a_facturar()
            n = 0
            for f in self.object.facturas.filter(estado="pendiente"):
                if f.monto != nuevo_monto:
                    f.monto = nuevo_monto
                    f.save(update_fields=["monto"])
                    f.recalcular_estado()
                    n += 1
            if n:
                msg += f" Se actualizó el monto de {n} factura(s) pendiente(s) a ${nuevo_monto:,.0f}."
        messages.success(self.request, msg)
        # Si cambió algo que afecta la cola del router, la actualiza sola.
        if any(c in form.changed_data for c in ("ip", "plan", "nombre_cola", "router")):
            ok, err = sincronizar_cola_cliente(self.object, self.request.user)
            if ok:
                messages.success(self.request, ok)
            elif err:
                messages.warning(self.request, err)
        return response
