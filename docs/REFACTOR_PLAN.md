# Plan de Modularización — app.py (1025→capas) — Audit 2.3

> **Estado:** Plan aprobado, no refactorizado aún. `app.py` sigue monolito funcional para no romper deploy. Este doc es la hoja de ruta cuando el equipo crezca >2 devs o se añadan 2+ features mayores.

## Objetivo
Separar `app.py` monolito (config + SQL directo + Jinja + Storage + QR + auth) en capas testeables, con validación Pydantic y Blueprints.

## Estructura propuesta (Application Factory)

```
src/
  __init__.py          # create_app() factory
  core/
    database.py        # db(), get_conn(), g.db, teardown, psycopg_pool
    security.py        # SECRET_KEY check, rate_limit (Upstash Redis), permissions
    storage.py         # supabase_upload/delete , local fallback
    logging.py         # JsonFormatter + X-Request-ID
  services/
    ticket_service.py  # comprar, validar, revertir, generar_codigo_unico, FOR UPDATE mesa
    qr_service.py      # generar QR, serve_qr, regenerar si falta
    finance_service.py # _load_finanzas_payload, cache SWR, warmup
    user_service.py    # ensure_admin, CRUD usuarios
  schemas/
    ticket.py          # Pydantic v2: CedulaCR, TelefonoCR, Ubicacion, Mesa 1..12, Monto 5000|10000
    user.py            # username 3..32, password 4..128, rol admin|portero
  routes/
    public_routes.py   # /, /api/mesas, /api/comprar
    admin_routes.py    # /admin, /api/entradas, /api/finanzas, /api/usuarios, /api/auditoria, /api/aprobar, /api/rechazar, /api/desbloquear
    scanner_routes.py  # /scanner, /api/validar, /api/historial, /api/revertir
  templates/           # mover desde /templates
  static/              # mover desde /static
```

## Pasos (orden impacto, no los 4 de golpe)

1. **Extraer `core/database.py`** — mover `db()`, `fetch_*`, `exec_sql`, `g.db` + `teardown`. Añadir `psycopg_pool.ConnectionPool` con `DATABASE_URL` pooler :6543, `min_size=1 max_size=5`, `check` cada request.
2. **Extraer `core/security.py`** — `SECRET_KEY` obligatorio, `Permissions-Policy`, `rate_limit` con Upstash Redis REST (`upstash-redis` vía `fetch`, sin lib pesada), fallback a in-memory en local.
3. **Pydantic `schemas/ticket.py`**:
   ```python
   from pydantic import BaseModel, Field, field_validator
   import re
   class CompraIn(BaseModel):
     nombre_completo: str = Field(min_length=3, max_length=80)
     cedula: str
     ubicacion: str = Field(pattern="^(Gradas|Mesas)$")
     mesa_numero: int | None = Field(None, ge=1, le=12)
     telefono: str = Field(pattern=r"^\+?506?\d{8}$")  # +50688888888 o 88888888
     @field_validator("cedula")
     def cedula_cr(cls, v):
       d = re.sub(r"\D","",v)
       if not 9 <= len(d) <= 12: raise ValueError("cédula 9-12 dígitos")
       return v
   ```
   Reemplaza validación manual en `comprar()` y `crear_usuario()`.
4. **Mover rutas a Blueprints**: `admin_bp = Blueprint("admin", url_prefix="/api")`, registrar en `create_app()`. Cada blueprint importa su `service`.
5. **Tests**: ya existe `tests/` con 13 tests; añadir `tests/test_ticket_service.py` para `ticket_service.comprar` con DB transaccional y `test_finance_service.py` para cache SWR.

## Decisión (3 alternativas)

| Opción | Pros | Contras | Cuándo |
|---|---|---|---|
| **A. Factory + Blueprints + Pydantic (recomendado)** | Testeable, DI, validación central, escala equipo | Requiere mover 400 líneas, riesgo regresión si se hace de golpe | Cuando se añada 2ª feature grande |
| B. Solo extraer `core/database.py` y `core/storage.py` | 80% win con 20% churn, mantiene `app.py` como orquestador | Sigue monolito | Para próximo sprint |
| C. Microservicios (API + worker QR) | Escala independiente | Overkill 15 entradas, Vercel ya es serverless | No ahora |

Elegida **B para inmediato, A cuando haya 2 devs**.

## Criterio de corte
No refactorizar ahora completo: `app.py` funciona, tests pasan, deploy verde. Refactor cuando `pytest --cov` <70% o se añada `feature: pagos múltiples`.

## Dependencias nuevas (solo si se ejecuta)
- `pydantic==2.*`
- `psycopg[binary,pool]==3.*`
