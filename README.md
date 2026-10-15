# Gestor ISP

Sistema web para administrar un proveedor de internet (WISP): clientes, planes,
zonas, cobros, cortes por fecha vía Mikrotik y proveedores.

Construido con **Django 5** + Bootstrap. Uso interno.

## Estado del proyecto

| Fase | Módulo | Estado |
|---|---|---|
| 1 | Base: login, roles, zonas, planes, clientes | ✅ hecho |
| — | Panel con barra lateral estilo WispHub (simplificado) | ✅ hecho |
| — | Red: routers Mikrotik + importar clientes (API o archivo .rsc) | ✅ hecho |
| 2 | Facturación: cargos mensuales, pagos, morosos | siguiente |
| 4 | Automatización de cortes por fecha vía Mikrotik | pendiente |
| 5 | Proveedores y pagos a proveedor | pendiente |
| 6 | Dashboard avanzado, export Excel, notificaciones | pendiente |

Import de Mikrotik: pantalla **Importar de Mikrotik** en el panel, o
`python manage.py importar_mikrotik --archivo colas.rsc --fuente queues` (simula;
agrega `--commit` para aplicar).

## Requisitos

- Python 3.12+
- (Opcional para producción) PostgreSQL

## Instalación rápida (Windows)

1. Instala [Python](https://www.python.org/downloads/) marcando **Add Python to PATH**.
2. Descarga el proyecto: **Code → Download ZIP** y descomprímelo.
3. Doble clic en **`INICIAR.bat`**. Instala todo la primera vez, abre el navegador
   en http://127.0.0.1:8000/ (usuario `admin_isp`, contraseña `demo12345`).
   No cierres la ventana negra mientras uses el panel.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env       # y edita los valores
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py init_roles
.venv\Scripts\python.exe manage.py createsuperuser
```

Para datos de ejemplo:

```bash
.venv\Scripts\python.exe manage.py seed_demo
```

## Ejecutar

```bash
.venv\Scripts\python.exe manage.py runserver
```

- App: http://127.0.0.1:8000/
- Panel de administración Django: http://127.0.0.1:8000/admin/

### Usuarios de ejemplo (tras `seed_demo`)

| Usuario | Rol | Contraseña |
|---|---|---|
| `admin_isp` | Administración | `demo12345` |
| `cobranza1` | Cobranza | `demo12345` |
| `soporte1` | Soporte | `demo12345` |

## Roles

- **Administración**: acceso total (clientes, catálogo, usuarios, bitácora).
- **Cobranza**: ve y edita clientes; ve bitácora. (En fase 2 registrará pagos.)
- **Soporte**: da de alta y edita clientes.

Se definen en `core/management/commands/init_roles.py`. Al agregar modelos nuevos,
volver a ejecutar `python manage.py init_roles`.

## Estructura

```
config/        configuración del proyecto (settings, urls)
core/          base: dashboard, bitácora, roles, cifrado (crypto.py)
catalogo/      Zona, Plan
clientes/      Cliente (alta/edición/listado/detalle con historial)
templates/     plantillas Bootstrap
static/        CSS y Bootstrap servido localmente (sin CDN)
```

## Colas simples en Mikrotik

Las colas simples se evalúan de arriba hacia abajo y el tráfico se queda en la
primera que coincide. Si el router tiene una cola general (p. ej. `total megas`
con target en las VLAN de clientes) por encima de las de clientes, éstas no
limitan ni cuentan consumo. En **Red → Routers**, pon el nombre de esa cola en
**cola padre** y el sistema creará las colas de clientes como hijas suyas.

## Notas de configuración (.env)

- `FERNET_KEY`: clave para cifrar contraseñas de routers (fase 3). Generar con
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- `DB_ENGINE=postgres` + variables `DB_*` para usar PostgreSQL.
- `DJANGO_DEBUG=False` y `DJANGO_ALLOWED_HOSTS` en producción.
