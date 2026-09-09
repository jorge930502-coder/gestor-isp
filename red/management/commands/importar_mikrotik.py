"""Importa clientes desde un Mikrotik (RouterOS) hacia la tabla Cliente.

Dos formas de leer los datos:

  A) Conectándose por API al router (necesita IP, usuario, contraseña y que el
     servicio 'api' esté activo y sea alcanzable desde esta PC).
  B) Desde un archivo exportado en el router. En New Terminal del Mikrotik:
         /queue simple export file=colas
     luego en Files bajas 'colas.rsc' y lo pasas aquí con --archivo.

Por defecto SIMULA (no guarda nada). Agrega --commit para escribir.

Ejemplos:

    python manage.py importar_mikrotik --archivo colas.rsc --fuente queues
    python manage.py importar_mikrotik --archivo colas.rsc --fuente queues --crear-planes --commit
    python manage.py importar_mikrotik --host 10.10.10.1 --user lector --password xxx --fuente queues
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalogo.models import Plan
from clientes.models import Cliente
from core.models import Bitacora, registrar
from red import mikrotik
from red.models import Router


IPV4 = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
DIA_PAGO = re.compile(r"\((\d{1,2})\)")


class _RouterAdHoc:
    def __init__(self, host, usuario, password, api_puerto, usa_tls):
        self.host = host
        self.usuario = usuario
        self._password = password
        self.api_puerto = api_puerto
        self.usa_tls = usa_tls

    @property
    def password(self):
        return self._password


def _parse_target(target: str) -> str | None:
    if not target:
        return None
    primero = target.split(",")[0].strip()
    if "/" in primero:
        ip, _, mask = primero.partition("/")
        if mask not in ("", "32"):
            return None
        return ip
    m = IPV4.search(primero)
    return m.group(1) if m else None


def _mbps(valor: str) -> Decimal:
    if not valor:
        return Decimal(0)
    valor = valor.strip()
    mult = 1
    if valor[-1:].lower() == "k":
        mult, valor = 1_000, valor[:-1]
    elif valor[-1:].lower() == "m":
        mult, valor = 1_000_000, valor[:-1]
    elif valor[-1:].lower() == "g":
        mult, valor = 1_000_000_000, valor[:-1]
    try:
        bits = Decimal(valor) * mult
    except Exception:
        return Decimal(0)
    return (bits / Decimal(1_000_000)).quantize(Decimal("0.1"))


def interpretar_nombre(texto: str):
    """De un nombre de cola como 'AICARDO VELASCO (5) pago' saca:
    nombre limpio, día de pago (o None), estado sugerido y etiquetas.
    """
    original = (texto or "").strip()
    bajo = original.lower()

    dia = None
    m = DIA_PAGO.search(original)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 28:
            dia = n

    estado = Cliente.Estado.ACTIVO
    etiquetas = []
    if "retir" in bajo or "cancel" in bajo:
        estado = Cliente.Estado.CANCELADO
        etiquetas.append("retirada/cancelada")
    elif "gratis" in bajo:
        estado = Cliente.Estado.GRATIS
        etiquetas.append("servicio gratis")
    elif "suspend" in bajo or "corte" in bajo or "cortado" in bajo:
        estado = Cliente.Estado.SUSPENDIDO
        etiquetas.append("suspendido")
    if any(p in bajo for p in ("debe", "abono", "mora", "moroso", "pendiente")):
        etiquetas.append("deuda")

    # Nombre limpio: quita "(N)" y la palabra suelta "pago" al final.
    limpio = DIA_PAGO.sub("", original)
    limpio = re.sub(r"\b[Pp][Aa][Gg][Oo]\b", "", limpio)
    limpio = re.sub(r"\s{2,}", " ", limpio).strip(" -\t")
    if not limpio:
        limpio = original

    return limpio, dia, estado, etiquetas


# --------------------------------------------------------------------------- #
#  Lectura desde archivo .rsc  ( /queue simple export )
# --------------------------------------------------------------------------- #

def _leer_rsc_queues(ruta: Path):
    """Parsea líneas 'add ... name="X" target=IP max-limit=U/D disabled=yes' de un
    export de RouterOS. Devuelve dicts con las mismas llaves que la API.
    """
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    # RouterOS parte comandos largos con '\' + salto de línea.
    texto = texto.replace("\\\n", " ").replace("\\\r\n", " ")
    filas = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea.startswith("add "):
            continue
        campos = dict(re.findall(r'([a-zA-Z0-9-]+)=("[^"]*"|\S+)', linea))
        for k, v in campos.items():
            campos[k] = v.strip('"')
        filas.append(campos)
    return filas


class Command(BaseCommand):
    help = "Importa clientes desde un Mikrotik (colas simples, PPPoE o leases DHCP)."

    def add_arguments(self, parser):
        parser.add_argument("--router", help="Nombre o ID de un Router guardado.")
        parser.add_argument("--host", help="IP/host del router.")
        parser.add_argument("--user", help="Usuario del router.")
        parser.add_argument("--password", help="Contraseña del router.")
        parser.add_argument("--port", type=int, default=8728)
        parser.add_argument("--tls", action="store_true", help="API con TLS (8729).")
        parser.add_argument(
            "--archivo", help="Ruta a un .rsc exportado del router (en vez de conectar)."
        )
        parser.add_argument(
            "--fuente", choices=["ppp", "queues", "dhcp"], default="queues",
            help="De dónde leer los clientes (por defecto: queues).",
        )
        parser.add_argument("--commit", action="store_true", help="Escribe los cambios.")
        parser.add_argument(
            "--crear-planes", action="store_true",
            help="Crea planes según la velocidad de la cola o el perfil PPPoE.",
        )
        parser.add_argument("--limite", type=int, default=0, help="Procesa solo N filas.")

    # ------------------------------------------------------------------

    def _get_router(self, opts):
        if opts["router"]:
            r = None
            if opts["router"].isdigit():
                r = Router.objects.filter(pk=int(opts["router"])).first()
            if r is None:
                r = Router.objects.filter(nombre__iexact=opts["router"]).first()
            if r is None:
                raise CommandError(f"No hay un Router llamado '{opts['router']}'.")
            return r
        if not (opts["host"] and opts["user"]):
            raise CommandError("Usa --archivo, o --router, o --host y --user.")
        return _RouterAdHoc(
            opts["host"], opts["user"], opts["password"] or "", opts["port"], opts["tls"]
        )

    def _filas_crudas(self, opts):
        fuente = opts["fuente"]
        if opts["archivo"]:
            ruta = Path(opts["archivo"])
            if not ruta.exists():
                raise CommandError(f"No existe el archivo: {ruta}")
            if fuente != "queues":
                raise CommandError("Con --archivo solo se admite --fuente queues por ahora.")
            self.stdout.write(f"Leyendo archivo {ruta} ...")
            return _leer_rsc_queues(ruta)

        router = self._get_router(opts)
        if isinstance(router, Router):
            self.router_obj = router
        self.stdout.write(f"Conectando a {router.host}:{router.api_puerto} ...")
        try:
            info = mikrotik.probar_conexion(router)
        except mikrotik.MikrotikError as exc:
            raise CommandError(str(exc))
        self.stdout.write(
            self.style.SUCCESS(f"OK — {info['identidad']} (RouterOS {info['version']})")
        )
        if fuente == "ppp":
            return mikrotik.listar_ppp_secrets(router)
        if fuente == "dhcp":
            return mikrotik.listar_dhcp_leases(router)
        return mikrotik.listar_queues_simple(router)

    def _normalizar(self, cruda, fuente):
        """Lleva una fila cruda (API o rsc) al formato interno."""
        if fuente == "ppp":
            texto = cruda.get("comment") or cruda.get("name") or ""
            ip = cruda.get("remote-address") or None
            ml = ""
            subida = bajada = None
            login = cruda.get("name", "")
            plan_hint = cruda.get("profile", "")
        elif fuente == "dhcp":
            texto = cruda.get("comment") or cruda.get("host-name") or cruda.get("mac-address") or ""
            ip = cruda.get("address") or None
            ml = ""
            subida = bajada = None
            login = cruda.get("mac-address", "")
            plan_hint = ""
        else:  # queues
            texto = cruda.get("comment") or cruda.get("name") or ""
            ip = _parse_target(cruda.get("target", ""))
            ml = cruda.get("max-limit", "") or ""
            subida = bajada = None
            if "/" in ml:
                a, _, b = ml.partition("/")
                subida, bajada = _mbps(a), _mbps(b)
            login = cruda.get("name", "")
            plan_hint = ml

        limpio, dia, estado_txt, etiquetas = interpretar_nombre(texto)
        disabled = str(cruda.get("disabled", "")).lower() in ("true", "yes")
        estado = Cliente.Estado.SUSPENDIDO if disabled else estado_txt

        return {
            "nombre": limpio,
            "original": texto.strip(),
            "login": login,
            "ip": ip,
            "plan_hint": plan_hint,
            "subida": subida, "bajada": bajada,
            "dia": dia,
            "estado": estado,
            "etiquetas": etiquetas,
            "disabled": disabled,
        }

    def _plan_para(self, fila):
        if fila["bajada"] is not None and fila["bajada"] > 0:
            nombre = f"{fila['bajada']:g}/{fila['subida']:g} Mbps"
            plan, _ = Plan.objects.get_or_create(
                nombre=nombre,
                defaults=dict(
                    mbps_bajada=int(fila["bajada"] or 0),
                    mbps_subida=int(fila["subida"] or 0),
                    precio_mensual=Decimal("0.00"),
                    descripcion="Creado al importar del Mikrotik",
                ),
            )
            return plan
        hint = (fila["plan_hint"] or "").strip()
        if hint and "/" not in hint:
            plan, _ = Plan.objects.get_or_create(
                nombre=hint,
                defaults=dict(
                    mbps_bajada=0, mbps_subida=0, precio_mensual=Decimal("0.00"),
                    descripcion="Perfil PPPoE importado del Mikrotik",
                ),
            )
            return plan
        return None

    # ------------------------------------------------------------------

    def handle(self, *args, **opts):
        self.router_obj = None
        fuente = opts["fuente"]
        crudas = list(self._filas_crudas(opts))
        filas = [self._normalizar(c, fuente) for c in crudas]
        if opts["limite"]:
            filas = filas[: opts["limite"]]

        validas = [f for f in filas if f["ip"]]
        sin_ip = len(filas) - len(validas)
        self.stdout.write(
            f"\nFuente '{fuente}': {len(filas)} entradas, "
            f"{len(validas)} con IP, {sin_ip} sin IP (separadores/etiquetas).\n"
        )

        nuevos = actualizados = sin_cambio = 0
        commit = opts["commit"]

        with transaction.atomic():
            for f in validas:
                existente = Cliente.objects.filter(ip=f["ip"]).first()
                if existente is None and f["nombre"]:
                    existente = Cliente.objects.filter(
                        nombre__iexact=f["nombre"], ip__isnull=True
                    ).first()

                plan = self._plan_para(f) if (commit and opts["crear_planes"]) else None
                nota = f"Importado de Mikrotik ({fuente}). Cola: \"{f['original']}\"."
                if f["etiquetas"]:
                    nota += " Marcas: " + ", ".join(f["etiquetas"]) + "."
                if f["plan_hint"]:
                    nota += f" Límite: {f['plan_hint']}."

                if existente is None:
                    nuevos += 1
                    marca = "NUEVO"
                    if commit:
                        Cliente.objects.create(
                            nombre=f["nombre"] or f["login"] or f["ip"],
                            ip=f["ip"],
                            nombre_cola=f["original"] or f["login"],
                            estado=f["estado"],
                            dia_de_pago=f["dia"] or 1,
                            plan=plan,
                            router=self.router_obj,
                            notas=nota,
                        )
                else:
                    cambios = []
                    if not existente.ip:
                        cambios.append("ip")
                    if existente.estado != f["estado"]:
                        cambios.append(f"estado→{f['estado']}")
                    if f["dia"] and existente.dia_de_pago != f["dia"]:
                        cambios.append(f"día pago→{f['dia']}")
                    if commit:
                        existente.ip = f["ip"]
                        existente.estado = f["estado"]
                        if self.router_obj and not existente.router_id:
                            existente.router = self.router_obj
                        if not existente.nombre_cola:
                            existente.nombre_cola = f["original"] or f["login"]
                        if f["dia"]:
                            existente.dia_de_pago = f["dia"]
                        if plan and not existente.plan_id:
                            existente.plan = plan
                            cambios.append("plan")
                        if "Importado de Mikrotik" not in (existente.notas or ""):
                            existente.notas = (existente.notas + "\n" + nota).strip()
                        existente.save()
                    if cambios:
                        actualizados += 1
                        marca = "ACTUALIZA"
                    else:
                        sin_cambio += 1
                        marca = "igual"

                dia_txt = f"pago día {f['dia']}" if f["dia"] else "sin día"
                self.stdout.write(
                    f"  [{marca:9}] {f['ip']:15} {(f['nombre'] or '')[:34]:34} "
                    f"{dia_txt:12} {f['estado']}"
                )

            if not commit:
                transaction.set_rollback(True)

        resumen = (
            f"nuevos={nuevos}  actualizados={actualizados}  sin cambio={sin_cambio}  "
            f"sin IP={sin_ip}"
        )
        self.stdout.write("")
        if commit:
            self.stdout.write(self.style.SUCCESS(f"HECHO. {resumen}"))
            registrar(
                None, Bitacora.Accion.OTRO, objeto="Importación Mikrotik",
                detalle=f"Fuente {fuente}. {resumen}",
            )
        else:
            self.stdout.write(self.style.WARNING(f"SIMULACIÓN — nada se guardó. {resumen}"))
            self.stdout.write("Repite el comando agregando  --commit  para aplicar.")
