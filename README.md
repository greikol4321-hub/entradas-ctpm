# Entradas CTPM — Venta con QR y SINPE Móvil

Vende entradas para el Gran Baile de Gala del CTP Matapalo sin filas. Sin enredos. La persona elige si quiere Gradas o Mesas, paga por SINPE Móvil con una referencia que ya lleva su nombre y su mesa, sube la captura y listo. Eso sí, no ve la entrada al instante. La verdad es que preferimos revisarla antes. En 48 horas como mucho le llega el QR por WhatsApp y en la puerta se valida una sola vez, nada de reventa.

Hecho para familias y para el personal del colegio. Al fin y al cabo es una fiesta del cole, no una boletera.

[![Deploy](https://img.shields.io/badge/deploy-Vercel-black?style=flat-square)](https://entradas-ctpm.vercel.app)
[![Stack](https://img.shields.io/badge/Flask-3.1-000000?style=flat-square)](#stack)
[![DB](https://img.shields.io/badge/Supabase-Postgres-3ECF8E?style=flat-square)](#stack)

---

### Cómo funciona

No hay mucho misterio, son tres momentos y ya está.

**1. Compra en `/`.** El cliente entra, pone nombre, cédula — solo tiene que escribir números, los guiones salen solos tipo `1-2345-0678` — elige Gradas (₡5.000) o Mesas (₡10.000). Si toca Mesas se abre el plano real del gimnasio, con 12 mesas y cada una con 6 sillas que miran al centro. Verde es disponible, rojo ocupada, naranja la que acabas de tocar. Paga por SINPE con algo así como `CTPM-GREIKOL-0347-MESAS-M3` y sube la foto del comprobante. Le queda un recibo que dice “Comprobante recibido — te escribimos por WhatsApp”, no la entrada. A propósito.

**2. Revisión en `/admin`.** Mira, ahí el admin filtra por Pendiente, Pagada o Usada, y por zona. Abre el comprobante, si todo cuadra le da a Aprobar. En ese instante se genera el ticket vertical — 360 por 520, más o menos como una tarjeta, con el QR de 5 letras tipo `QJPFG` bien grande — y lo deja listo para descargar como `QJPFG_Maria-Rojas-Mora_001.png` o PDF. Después lo manda a mano por WhatsApp. No se autogenera nada para el cliente, nos parecía más seguro así.

**3. Validación en `/scanner`.** El portero abre la cámara del celular, escanea y la pantalla canta: verde “VÁLIDA” o roja “USADA / NO EXISTE / PENDIENTE”. Una entrada, un uso. Vamos, sin segundas vueltas.

---

### El mapa — solo mesas, pero bien hecho

Antes eran 12 botones grises que decían Mesa 1, Mesa 2... funcionaba, aunque claro, nadie se ubicaba. Ahora es el plano del gimnasio de Matapalo con el `ESCENARIO — VIP` arriba y `GENERAL` abajo. Cada mesa es un círculo crema con 6 sillas de verdad — icono `lucide:armchair` del MCP, giradas para que miren al centro (0° a 300°). En PC se ven 4 por fila, en tablet 3 y en móvil 2. Sin librerías raras, solo CSS.

### Con qué está hecho

- **Backend:** Flask 3.1 con `psycopg` al pooler de Supabase Postgres, `qrcode[pil]` y `Pillow` para el QR. Sin ORM, a pelo, porque para 12 mesas no hace falta más.
- **Frontend:** Jinja y Vanilla JS. El CSS vive en un solo archivo con tokens tipo `--ink:#0a4c23`, ese verde del colegio que ya conoces.
- **Infra:** Vercel serverless. Los comprobantes y los QR quedan en Supabase Storage, en buckets privados `comprobantes`/`qrcodes`; en Vercel viven un rato en `/tmp` y ya está.
- **Seguridad, lo justo:** saneo con `esc()` en `admin.html` para no comerse un XSS si alguien pone `<img>` en el nombre, rate-limit en memoria (5 intentos por minuto para comprar, 10 para login), cabeceras `CSP/HSTS/X-Frame`, RLS cerrado a `authenticated/service_role` y una tablita `auditoria` donde queda quién aprobó o validó qué.

### Cómo está ordenado

```
Entradas CTPM/
├── app.py                 # todo el Flask — rutas, QR, validación, límites
├── supabase/migrations/   # 00001_init → 00006_auditoria
├── templates/
│   ├── index.html         # wizard de 4 pasos + mapa
│   ├── admin.html         # tabla, modal vertical y finanzas sin Chart.js
│   └── scanner.html       # html5-qrcode
├── static/css/style.css   # mapa, tickets, responsive
└── uploads/ static/qrcodes/  # ignorados en git, en Vercel van a /tmp
```

### Para correrlo acá

```bash
# 1. La base ya está en Supabase, solo poné tu .env con DATABASE_URL
# 2. Python
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt  # todo pineado con == , 99/100 en audit

# 3. Dale
python app.py  # http://localhost:5000
# /admin → admin/admin123  |  /scanner → valida (necesita https o localhost para la cámara)
```

En Vercel (Production) van `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `FLASK_SECRET`, `SINPE_NUMERO` y `SINPE_NOMBRE`. En local con `.env` alcanza.

### Detalles que importan

- `uploads/` y `qrcodes/` están en `.gitignore`; en Vercel no hay disco, por eso se suben a Supabase al vuelo.
- El QR no es un UUID largo, son 5 caracteres de `23456789ABCDEFGHJKMNPQRSTVWXYZ` — sin 0, O, I, para no confundirse. Sobran, son 33 millones de combinaciones para un baile de cientos.
- Dependabot está activo, cada lunes te propone bump de `Pillow` o lo que toque si hay CVE. No hace ruido si no hace falta.

Hecho con cuidado para el CTP Matapalo. Si algo no se entiende a la primera, es que hay que reescribirlo, no añadirle otro párrafo.
