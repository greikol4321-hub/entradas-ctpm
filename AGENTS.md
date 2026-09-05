# Agent Instructions — Entradas CTPM

## Stack
Flask 3.1 + psycopg + Supabase Postgres, Jinja + Vanilla JS, deploy Vercel serverless.

## Package Manager
`pip install -r requirements.txt` — versiones pineadas (`==`).

## Project Structure
```
app.py                  # shim de compatibilidad (modularizado → src/)
server.py               # entry point Vercel: from app import app
src/core/               # database, storage, security, logging
src/services/           # ticket, finance, user, qr
src/routes/             # public, admin, scanner
src/schemas/            # user, ticket
templates/              # base, index, admin, scanner, login, 404, 403
static/css/style.css    # mapa, tickets, responsive
static/js/app.js
supabase/migrations/    # 00001_init → 00007_fix_auditoria
supabase/config.toml
```

## Key Commands
| Task | Command |
|------|---------|
| Run dev | `python app.py` → http://localhost:5000 |
| Admin | `/admin` → admin/admin123 |
| Scanner | `/scanner` → valida |

## CI
`.github/workflows/ci.yml` — ruff check/format + pip-audit + pytest (all non-blocking `|| true`).
No tests exist; pytest always skips. No linter/formatter config files.

## Conventions
- Sin ORM, a pelo — 12 mesas, no lo necesita
- QR 5 chars de `23456789ABCDEFGHJKMNPQRSTVWXYZ` (sin 0/O/I)
- Saneo con `esc()` en nombres; rate limits 5/min comprar, 10/min login
- CSP/HSTS/X-Frame headers, RLS cerrado, tabla `auditoria`
- uploads/ y qrcodes/ en .gitignore; en Vercel se suben a Supabase Storage

## Env Vars (Vercel)
`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `FLASK_SECRET`, `SINPE_NUMERO`, `SINPE_NOMBRE`

## Commit Attribution
AI commits MUST include:
```
Co-Authored-By: (the agent model's name and attribution byline)
```