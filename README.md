# Sistema de Venta y Validación de Entradas — CTPM

Flask + MySQL + Vanilla JS + html5-qrcode + qrcode[pil]

## Estructura de carpetas (Flask estándar)
```
Entradas CTPM/
├── app.py               # Backend completo (rutas + MySQL + QR)
├── schema.sql           # CREATE DATABASE + tablas
├── requirements.txt
├── .env.example
├── uploads/             # comprobantes SINPE (se crea solo, .gitignore)
├── static/
│   ├── css/style.css    # CSS modular en un archivo (secciones comentadas)
│   ├── js/app.js
│   └── qrcodes/         # PNGs generados al aprobar (se crea solo)
└── templates/
    ├── base.html
    ├── index.html       # Flujo Cliente (pasos 1-5)
    ├── admin.html       # Flujo Admin (tabla + modal aprobar)
    └── scanner.html     # Flujo Portero (html5-qrcode)
```

## Instalación (5 min)

1. **MySQL**: ejecuta `schema.sql`
   ```bash
   mysql -u root -p < schema.sql
   # o abre MySQL Workbench y pega el contenido
   ```
2. **Python**
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```
3. **Configura DB** en `app.py` → `DB_CFG` (o usa `.env` si lo cableas con python-dotenv)
4. **Corre**
   ```bash
   python app.py
   # http://localhost:5000       → cliente
   # http://localhost:5000/admin → admin
   # http://localhost:5000/scanner → portero (requiere HTTPS o localhost para cámara)
   ```

## Flujos implementados

**Cliente** `GET /` + `POST /api/comprar`: formulario nombre/cédula/ubicación + instrucciones SINPE + `input file` comprobante. Guarda en `uploads/` y fila `Pendiente`. Respuesta: "En 48h se le notificará".

**Admin** `GET /admin` + `GET /api/entradas` + `POST /api/aprobar/:id`: tabla filtrable, link "Ver" comprobante, botón Aprobar abre modal que llama a Flask, genera QR (contenido = UUID), guarda en `static/qrcodes/:id.png`, actualiza `qr_path` y `estado='Aprobada'`.

**Portero** `GET /scanner` + `POST /api/validar`: `html5-qrcode` escanea, `fetch` al backend, backend verifica MySQL:
- `Aprobada` → `Usada` + pantalla VERDE
- `Usada` / `NO_EXISTE` → pantalla ROJA gigante
- `Pendiente` → 403

## Notas Ponytail
- Sin ORM, sin blueprint, sin auth: `mysql-connector` directo es lo más corto que funciona. Agrega Flask-Login + bcrypt cuando lo necesites, no antes.
- QR = UUID de la fila. No hay tabla `usuarios` obligatoria (está creada como opcional).
- `uploads/` y `qrcodes/` están en `.gitignore` por defecto.

## Próximos pasos (cuando duela, no antes)
- Auth real para `/admin` y `/scanner`
- Envío de QR por WhatsApp/Email (Twilio / SMTP)
- Rate limit en `/api/validar`
