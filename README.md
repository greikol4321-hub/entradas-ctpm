# 🎟️ Entradas CTPM — Venta con QR y SINPE Móvil

Vende entradas para el Gran Baile de Gala del CTP Matapalo sin filas ni enredos. El que compra paga por SINPE, sube el comprobante y en 48h recibe su entrada con QR por WhatsApp. En la puerta, el QR se valida una sola vez.

**Hecho para familias y personal del colegio, no para revender.**

[![Deploy](https://img.shields.io/badge/deploy-Vercel-black?style=flat-square)](https://entradas-ctpm.vercel.app)
[![Stack](https://img.shields.io/badge/Flask-3.1-000000?style=flat-square)](#stack)
[![DB](https://img.shields.io/badge/Supabase-Postgres-3ECF8E?style=flat-square)](#stack)

---

### Cómo funciona, en 3 pasos

**1. El cliente compra** en `/` — elige Gradas (₡5.000) o Mesas (₡10.000), toca su mesa en el mapa del gimnasio (las sillas miran a la mesa, verde disponible / rojo ocupada / naranja seleccionada), paga por SINPE con referencia `CTPM-NOMBRE-XXXX-MESAS-M3` y sube la captura. No ve la entrada todavía, solo un recibo: “Comprobante recibido — te escribimos por WhatsApp”.

**2. El admin revisa** en `/admin` — filtra por estado (Pendiente/Pagada/Usada) y zona, ve el comprobante, aprueba y se genera el ticket vertical (360×520) con QR de 5 letras (`QJPFG`). Lo descarga como `QJPFG_Maria-Rojas-Mora_001.png` o PDF y lo manda por WhatsApp. No se autogenera para el cliente.

**3. El portero valida** en `/scanner` — abre la cámara, escanea, ve pantalla verde “VÁLIDA” o roja “USADA / NO EXISTE / PENDIENTE”. Una entrada = un uso.

---

### Mapa de mesas VIP — solo mesas

12 mesas, 6 sillas cada una (icono de silla real del MCP `lucide:armchair`, giradas 0°–300° mirando al centro). Responsive: 4 columnas en PC, 3 en tablet, 2 en móvil. Demo local: `preview-mesas.html` o directo en el paso 2 del wizard.

> Antes era una grilla de botones `Mesa 1…12`. Ahora es el plano del gimnasio con `ESCENARIO — VIP` arriba y `GENERAL` abajo, para que nadie se pierda.

### Stack

- **Backend:** Flask 3.1 + `psycopg` (Supabase Postgres pooler) + `qrcode[pil]` + `Pillow`
- **Frontend:** Jinja + Vanilla JS, CSS con tokens `--ink:#0a4c23` (verde institucional), sin frameworks
- **Infra:** Vercel (serverless), Supabase Storage `comprobantes`/`qrcodes` (privados), `SESSION_COOKIE_SECURE` solo en prod
- **Seguridad:** `esc()` para XSS en `admin.html`, rate-limit en memoria (5/min comprar, 10/min login), headers `CSP/HSTS/X-Frame`, RLS `authenticated,service_role`, auditoría en `public.auditoria`

### Estructura

```
Entradas CTPM/
├── app.py                 # Flask, QR, validación, rate-limit
├── supabase/migrations/   # 00000_init → 00006_auditoria
├── templates/
│   ├── index.html         # wizard 4 pasos + mapa mesas
│   ├── admin.html         # tabla + modal ticket vertical + finanzas
│   └── scanner.html       # validación con html5-qrcode
├── static/css/style.css   # mapa, tickets, responsive
└── uploads/ static/qrcodes/  # .gitignore, viven en /tmp en Vercel
```

### Correr local

```bash
# 1. DB: ya está en Supabase, solo poné tu .env con DATABASE_URL
# 2. Python
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt  # todas pineadas ==

# 3. Corre
python app.py  # http://localhost:5000
# /admin → admin/admin123  |  /scanner → valida
```

Variables en Vercel (Production): `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `FLASK_SECRET`, `SINPE_NUMERO`, `SINPE_NOMBRE`. En local basta con `.env`.

### Notas cortas

- `uploads/` y `qrcodes/` están en `.gitignore` — en Vercel viven en `/tmp`.
- QR = código de 5 chars (`23456789ABCDEFGHJKMNPQRSTVWXYZ` sin 0/O/I), fácil de dictar si no carga la imagen.
- `Dependabot` activo (pip semanal) — te abre PRs si hay CVE.

Hecho con cuidado para el CTP Matapalo — si algo no se entiende, se cambia el texto, no se añade un manual.
