"""Cliente ligero para hablar con un Mikrotik (RouterOS) por API.

Usa la librería `librouteros`. Todas las funciones devuelven listas de dicts
con las llaves tal cual las entrega RouterOS (con guiones: 'remote-address', etc.).
"""

from __future__ import annotations

import ssl
from contextlib import contextmanager

from librouteros import connect
from librouteros.exceptions import LibRouterosError, TrapError


class MikrotikError(RuntimeError):
    pass


@contextmanager
def conectar(router):
    """Context manager que abre y cierra la conexión al router.

    `router` es una instancia de red.models.Router (o cualquier objeto con
    host, usuario, password, api_puerto, usa_tls).
    """
    kwargs = dict(
        username=router.usuario,
        password=router.password,
        host=router.host,
        port=int(router.api_puerto),
    )
    if getattr(router, "usa_tls", False):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_wrapper"] = ctx.wrap_socket

    try:
        api = connect(**kwargs)
    except (LibRouterosError, OSError) as exc:
        raise MikrotikError(f"No se pudo conectar a {router.host}: {exc}") from exc

    try:
        yield api
    finally:
        try:
            api.close()
        except Exception:
            pass


def probar_conexion(router) -> dict:
    """Devuelve identidad y versión del router; lanza MikrotikError si falla."""
    with conectar(router) as api:
        identidad = tuple(api.path("system", "identity"))
        recurso = tuple(api.path("system", "resource"))
    nombre = identidad[0].get("name", "") if identidad else ""
    version = recurso[0].get("version", "") if recurso else ""
    return {"identidad": nombre, "version": version}


def _listar(router, *path) -> list[dict]:
    try:
        with conectar(router) as api:
            return list(api.path(*path))
    except TrapError as exc:
        raise MikrotikError(f"El router rechazó la consulta {'/'.join(path)}: {exc}") from exc


def listar_ppp_secrets(router) -> list[dict]:
    """Usuarios PPPoE: name, password, profile, remote-address, disabled, comment."""
    return _listar(router, "ppp", "secret")


def listar_ppp_activos(router) -> list[dict]:
    """Sesiones PPPoE activas ahora mismo: name, address, uptime."""
    return _listar(router, "ppp", "active")


def listar_queues_simple(router) -> list[dict]:
    """Colas simples: name, target, max-limit, disabled, comment."""
    return _listar(router, "queue", "simple")


def listar_dhcp_leases(router) -> list[dict]:
    """Leases DHCP: address, mac-address, host-name, comment, status, dynamic."""
    return _listar(router, "ip", "dhcp-server", "lease")


def estado_conexiones(router) -> dict:
    """Devuelve {ip: {'en_linea': bool, 'arp': status, 'bytes_baj': int, 'bytes_sub': int}}
    combinando la tabla ARP y los contadores de las colas simples."""
    ONLINE = {"reachable", "delay", "probe", "permanent", "stale"}
    res = {}
    with conectar(router) as api:
        for a in api.path("ip", "arp"):
            ip = (a.get("address") or "").strip()
            if not ip:
                continue
            st = a.get("status", "")
            res[ip] = {
                "arp": st,
                "en_linea": st in ONLINE and str(a.get("complete", "")).lower() in ("true", "yes"),
                "bytes_baj": 0, "bytes_sub": 0,
            }
        for q in api.path("queue", "simple"):
            ip = (q.get("target") or "").split(",")[0].split("/")[0].strip()
            if not ip:
                continue
            sub, baj = _split_par(q.get("bytes"))
            d = res.setdefault(ip, {"arp": "", "en_linea": False, "bytes_baj": 0, "bytes_sub": 0})
            d["bytes_baj"], d["bytes_sub"] = baj, sub
    return res


def listar_address_list(router, lista: str) -> list[dict]:
    filas = _listar(router, "ip", "firewall", "address-list")
    return [f for f in filas if f.get("list") == lista]


def ips_en_lista(router, lista: str) -> set[str]:
    return {f.get("address", "").split("/")[0] for f in listar_address_list(router, lista)}


def bloquear_ip(router, ip: str, lista: str, comentario: str = "") -> bool:
    """Agrega la IP a la address-list `lista`. Devuelve True si la agregó
    (False si ya estaba). Requiere un usuario con permiso de escritura."""
    with conectar(router) as api:
        path = api.path("ip", "firewall", "address-list")
        for f in path:
            if f.get("list") == lista and f.get("address", "").split("/")[0] == ip:
                return False
        datos = {"list": lista, "address": ip}
        if comentario:
            datos["comment"] = comentario[:100]
        try:
            path.add(**datos)
        except TrapError as exc:
            raise MikrotikError(f"No se pudo bloquear {ip}: {exc}") from exc
    return True


def desbloquear_ip(router, ip: str, lista: str) -> bool:
    """Quita la IP de la address-list `lista`. True si quitó algo."""
    with conectar(router) as api:
        path = api.path("ip", "firewall", "address-list")
        ids = [
            f[".id"] for f in path
            if f.get("list") == lista and f.get("address", "").split("/")[0] == ip
        ]
        for _id in ids:
            path.remove(_id)
    return bool(ids)


def monitor_cola(router, ip: str) -> dict:
    """Rate instantáneo de la cola simple del cliente cuya IP es `ip`.
    Devuelve {nombre, subida_bps, bajada_bps, total_subida, total_bajada, deshabilitada}.
    """
    with conectar(router) as api:
        qid = qname = None
        total_s = total_b = 0
        disabled = False
        for q in api.path("queue", "simple"):
            t = (q.get("target") or "").split(",")[0].split("/")[0].strip()
            if t == ip:
                qid = q.get(".id")
                qname = q.get("name", "")
                total_s, total_b = _split_par(q.get("bytes"))
                disabled = str(q.get("disabled", "")).lower() in ("true", "yes")
                break
        if qid is None:
            raise MikrotikError(f"No hay una cola para la IP {ip}.")
        try:
            filas = list(api("/queue/simple/monitor", **{"numbers": qid, "once": True}))
        except (TrapError, LibRouterosError):
            filas = []
    rate = (filas[0].get("rate") if filas else "0/0") or "0/0"
    sub_bps, baj_bps = _split_par(rate)
    return {
        "nombre": qname,
        "subida_bps": sub_bps,
        "bajada_bps": baj_bps,
        "total_subida_bytes": total_s,
        "total_bajada_bytes": total_b,
        "deshabilitada": disabled,
    }


def monitor_trafico(router, interfaces) -> list[dict]:
    """Rate instantáneo (bits/s) de cada interfaz. `interfaces` = lista de nombres."""
    if not interfaces:
        return []
    metadatos = {}
    with conectar(router) as api:
        for f in api.path("interface"):
            if f.get("name") in interfaces:
                metadatos[f.get("name")] = f.get("comment", "") or ""
        salida = []
        for nombre in interfaces:
            try:
                filas = list(api(
                    "/interface/monitor-traffic", **{"interface": nombre, "once": True}
                ))
            except (TrapError, LibRouterosError):
                filas = []
            d = filas[0] if filas else {}
            salida.append({
                "nombre": nombre,
                "comentario": metadatos.get(nombre, ""),
                "rx_bps": int(d.get("rx-bits-per-second", 0) or 0),
                "tx_bps": int(d.get("tx-bits-per-second", 0) or 0),
            })
    return salida


def ping_desde_router(router, destino, veces=4) -> dict:
    """Hace ping desde el router a `destino`. Devuelve {recibidos, enviados, promedio_ms}."""
    with conectar(router) as api:
        try:
            filas = list(api("/ping", address=destino, count=veces))
        except (TrapError, LibRouterosError) as exc:
            raise MikrotikError(f"No se pudo hacer ping: {exc}") from exc
    if not filas:
        return {"recibidos": 0, "enviados": veces, "promedio_ms": None}
    ultimo = filas[-1]
    return {
        "recibidos": int(ultimo.get("received", 0)),
        "enviados": int(ultimo.get("sent", veces)),
        "promedio_ms": ultimo.get("avg-rtt"),
    }


def configurar_portal(router, portal_host, lista="MOROSOS") -> list[str]:
    """Deja el router listo para redirigir a los clientes de `lista` al portal.

    Idempotente: no repite reglas que ya existan. Devuelve la lista de acciones.
    `portal_host` es 'IP:puerto' (ej. 192.168.8.50:8000).
    """
    acciones = []
    destino = f"{portal_host.rstrip('/')}/portal/"
    with conectar(router) as api:
        # 1. DNS del router
        dns = list(api.path("ip", "dns"))
        if dns and str(dns[0].get("allow-remote-requests")).lower() not in ("true", "yes"):
            api.path("ip", "dns").update(**{".id": dns[0][".id"], "allow-remote-requests": "yes"})
            acciones.append("DNS del router activado (allow-remote-requests)")

        # 2. Proxy
        proxy = list(api.path("ip", "proxy"))
        if proxy and str(proxy[0].get("enabled")).lower() not in ("true", "yes"):
            api.path("ip", "proxy").update(**{".id": proxy[0][".id"], "enabled": "yes", "port": "8080"})
            acciones.append("Proxy del router activado (puerto 8080)")

        # 3. Proxy access: redirect
        pacc = api.path("ip", "proxy", "access")
        ya = any(f.get("src-address-list") == lista and f.get("action") == "deny" for f in pacc)
        if not ya:
            pacc.add(**{"src-address-list": lista, "action": "deny", "redirect-to": destino})
            acciones.append(f"Regla de proxy: {lista} -> {destino}")

        # 4/5. NAT redirects
        nat = api.path("ip", "firewall", "nat")
        existentes = list(nat)

        def hay(proto, dport, toport):
            return any(
                f.get("chain") == "dstnat" and f.get("src-address-list") == lista
                and f.get("protocol") == proto and f.get("dst-port") == str(dport)
                and f.get("action") == "redirect" and f.get("to-ports") == str(toport)
                for f in existentes
            )

        for proto, dport, toport, com in [
            ("udp", 53, 53, "DNS morosos"),
            ("tcp", 53, 53, "DNS morosos"),
            ("tcp", 80, 8080, "Portal morosos"),
        ]:
            if not hay(proto, dport, toport):
                nat.add(**{
                    "chain": "dstnat", "protocol": proto, "src-address-list": lista,
                    "dst-port": str(dport), "action": "redirect", "to-ports": str(toport),
                    "comment": com,
                })
                acciones.append(f"NAT redirect {proto}/{dport} -> {toport} ({com})")

    return acciones or ["Ya estaba todo configurado (no se cambió nada)."]


def crear_o_actualizar_cola(router, nombre, ip, subida_mbps, bajada_mbps, comentario=""):
    """Crea (o actualiza si ya existe por IP o por nombre) una cola simple.

    max-limit de RouterOS es 'subida/bajada' desde el punto de vista del target.
    Devuelve ('creada'|'actualizada', detalle).
    """
    max_limit = f"{int(subida_mbps or 0)}M/{int(bajada_mbps or 0)}M"
    target = f"{ip}/32"
    with conectar(router) as api:
        path = api.path("queue", "simple")
        existente = None
        for q in path:
            t = (q.get("target") or "").split(",")[0].split("/")[0].strip()
            if t == ip or q.get("name") == nombre:
                existente = q
                break
        datos = {
            "name": nombre, "target": target, "max-limit": max_limit,
            # apagamos burst para que no choque con el nuevo max-limit
            "burst-limit": "0/0", "burst-threshold": "0/0", "limit-at": "0/0",
        }
        if comentario:
            datos["comment"] = comentario[:100]
        try:
            if existente:
                datos[".id"] = existente[".id"]
                path.update(**datos)
                return "actualizada", f"{nombre} → {target} {max_limit}"
            path.add(**datos)
            return "creada", f"{nombre} → {target} {max_limit}"
        except TrapError as exc:
            raise MikrotikError(f"El router rechazó la cola: {exc}") from exc


def _split_par(valor):
    """'123/456' -> (123, 456) en enteros. Tolera vacío."""
    a, _, b = (valor or "0/0").partition("/")
    try:
        return int(a or 0), int(b or 0)
    except ValueError:
        return 0, 0


def consumo_de_ip(router, ip: str, muestra_segundos: float = 1.0) -> dict:
    """Mide el consumo del cliente cuya cola simple apunta a `ip`.

    Toma dos lecturas de bytes separadas `muestra_segundos` para calcular la
    velocidad instantánea. Devuelve bits/s y totales acumulados de la cola.
    """
    import time

    def _leer():
        with conectar(router) as api:
            for q in api.path("queue", "simple"):
                target = (q.get("target") or "").split(",")[0].split("/")[0].strip()
                if target == ip:
                    return q
        return None

    q1 = _leer()
    if q1 is None:
        raise MikrotikError(f"No hay una cola simple para la IP {ip} en {router.host}.")
    b1_sub, b1_baj = _split_par(q1.get("bytes"))

    time.sleep(muestra_segundos)

    q2 = _leer() or q1
    b2_sub, b2_baj = _split_par(q2.get("bytes"))

    dt = muestra_segundos or 1.0
    bps_sub = max(0, (b2_sub - b1_sub)) * 8 / dt
    bps_baj = max(0, (b2_baj - b1_baj)) * 8 / dt

    max_sub, max_baj = _split_par(q2.get("max-limit"))
    return {
        "nombre_cola": q2.get("name", ""),
        "subida_bps": bps_sub,
        "bajada_bps": bps_baj,
        "total_subida_bytes": b2_sub,
        "total_bajada_bytes": b2_baj,
        "limite_subida_bps": max_sub,
        "limite_bajada_bps": max_baj,
        "deshabilitada": str(q2.get("disabled", "")).lower() in ("true", "yes"),
    }
