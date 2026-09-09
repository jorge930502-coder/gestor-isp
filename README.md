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

## Notas de configuración (.env)

- `FERNET_KEY`: clave para cifrar contraseñas de routers (fase 3). Generar con
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- `DB_ENGINE=postgres` + variables `DB_*` para usar PostgreSQL.
- `DJANGO_DEBUG=False` y `DJANGO_ALLOWED_HOSTS` en producción.
