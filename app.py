"""
Sistema CTPM — Venta y validación de entradas
Soporta Postgres (Supabase) via DATABASE_URL o MySQL via variables DB_*
Mesas numeradas + Finanzas
"""
import os, uuid, pathlib, functools, secrets, io, time, json, hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict, deque
CR_TZ = ZoneInfo("America/Costa_Rica")
def to_cr_str(dt, fmt="%Y-%m-%d %H:%M"):
    if dt is None:
        return None
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CR_TZ).strftime(fmt)
    except:
        return dt.strftime(fmt) if hasattr(dt, "strftime") else str(dt)
def now_cr():
    return datetime.now(CR_TZ)
from flask import Flask, request, jsonify, render_template, send_from_directory, send_file, url_for, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
from dotenv import load_dotenv
load_dotenv()

try:
    import psycopg
    HAVE_PG = True
except ImportError:
    HAVE_PG = False
try:
    import mysql.connector
    HAVE_MY = True
except ImportError:
    HAVE_MY = False

# --- Config ---
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET", "ctpm-dev-secret-cambia-en-produccion-2026")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
BASE = pathlib.Path(__file__).parent
if os.getenv("VERCEL"):
    UPLOAD_FOLDER = pathlib.Path("/tmp") / "uploads"
    QR_FOLDER = pathlib.Path("/tmp") / "qrcodes"
else:
    UPLOAD_FOLDER = BASE / "uploads"
    QR_FOLDER = BASE / "static" / "qrcodes"
UPLOAD_FOLDER.mkdir(exist_ok=True)
QR_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXT = {".jpg",".jpeg",".png",".webp",".pdf"}
def allowed(fname):
    return pathlib.Path(fname).suffix.lower() in ALLOWED_EXT

SINPE_NUMERO = os.getenv("SINPE_NUMERO", "8888-8888")
SINPE_NOMBRE = os.getenv("SINPE_NOMBRE", "Asociación CTPM")
PRECIO_GRADAS = "₡5.000"
PRECIO_MESAS  = "₡10.000"
PRECIO_GRADAS_VAL = 5000
PRECIO_MESAS_VAL = 10000
NUM_MESAS = 12
DEMO_USER = "admin"
DEMO_PASS = "admin123"
# ponytail: cache en memoria para /api/finanzas 45s — evita 4 queries por switch de pestaña (skill python-performance + kpi-dashboard)
_FIN_CACHE = {"data": None, "ts": 0, "etag": None}
FIN_TTL = 45
def _fin_etag(data): return hashlib.md5(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:12]
def invalidate_fin_cache():
    _FIN_CACHE["data"] = None
    _FIN_CACHE["ts"] = 0
    _FIN_CACHE["etag"] = None
app.config['SESSION_COOKIE_SECURE'] = bool(os.getenv("VERCEL"))  # True en prod HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# ponytail: rate-limit en memoria sin redis (suficiente para 12 mesas, sin deps nuevas)
RATE_LIMIT = defaultdict(deque)
def allow_rate(key, limit, window=60):
    now = time.time()
    q = RATE_LIMIT[key]
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True
def rate_limited(limit, window=60):
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **kw):
            ip = request.remote_addr or "unknown"
            k = f"{fn.__name__}:{ip}"
            if not allow_rate(k, limit, window):
                return jsonify(ok=False, msg="Demasiadas solicitudes, intenta en un minuto"), 429
            return fn(*a, **kw)
        return wrap
    return deco
@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # CSP mínima sin romper cdnjs/jspdf + google fonts
    resp.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://unpkg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self' https://*.supabase.co"
    if os.getenv("VERCEL"):
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # web-performance skill: cache estático 1 año inmmutable, API finanzas 45s private (evita hammer DB en live dashboard), otras APIs 10s
    try:
        p = request.path
        if p.startswith("/static/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            # version hint para Vercel CDN
            resp.headers["Vary"] = "Accept-Encoding"
        elif p == "/api/finanzas":
            # ETag ya puesto en handler si es HIT; si no, poner max-age por defecto
            if "Cache-Control" not in resp.headers:
                resp.headers["Cache-Control"] = "private, max-age=30, must-revalidate"
            resp.headers["Vary"] = "Cookie"
        elif p.startswith("/api/"):
            if "Cache-Control" not in resp.headers:
                resp.headers["Cache-Control"] = "private, max-age=10, must-revalidate"
            resp.headers["Vary"] = "Cookie"
    except: pass
    return resp

# --- Supabase Storage (para que "Ver" comprobante no 404 en Vercel /tmp efímero) ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://jyfmimxzhpvcezwilkdd.supabase.co")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SERVICE_ROLE_KEY")
# buckets creados en migración 20260104000000
COMPROBANTES_BUCKET = "comprobantes"

def _supabase_headers(ct="application/octet-stream"):
    if not SUPABASE_SERVICE_KEY: return {}
    return {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": ct}

def supabase_upload(bucket, fname, data_bytes, content_type="application/octet-stream"):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return False
    try:
        import urllib.request, urllib.error
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{fname}"
        req = urllib.request.Request(url, data=data_bytes, method="POST", headers=_supabase_headers(content_type))
        # si ya existe, intentar PUT (upsert)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200,201)
        except urllib.error.HTTPError as e:
            if e.code in (409, 400):  # ya existe, probar PUT
                req2 = urllib.request.Request(url, data=data_bytes, method="PUT", headers=_supabase_headers(content_type))
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    return resp2.status in (200,201)
            return False
    except Exception as e:
        print(f"[storage] upload {bucket}/{fname} err: {e}")
        return False

def supabase_download(bucket, fname):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    try:
        import urllib.request
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{fname}"
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read(), resp.headers.get_content_type() or "application/octet-stream"
    except Exception as e:
        # print(f"[storage] download {bucket}/{fname} err: {e}")
        return None

# --- Código corto fácil de escribir ---
# 6 chars, sin 0/O/1/I/L/U para evitar confusión, solo mayúsculas + 2-9. 32^6 = 1B combos.
_CODIGO_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODIGO_LEN = 5  # ponytail: 5 chars sobra (33M combos) para cientos de entradas, fácil de dictar. Sube a 6 si esperas >10k
def generar_codigo():
    return ''.join(secrets.choice(_CODIGO_ALPHABET) for _ in range(_CODIGO_LEN))
def generar_codigo_unico(max_intentos=12):
    for _ in range(max_intentos):
        c = generar_codigo()
        # case-insensitive check: upper
        exists = fetch_one("SELECT id FROM entradas WHERE codigo=%s", (c,))
        if not exists:
            return c
    # fallback improbable: uuid slice
    return uuid.uuid4().hex[:_CODIGO_LEN].upper().translate(str.maketrans('01IOUL','234567'))

# --- DB abstraction ---
def _pg_dsn():
    return os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")

def _is_pg():
    dsn = _pg_dsn()
    return bool(dsn) and HAVE_PG

def _is_mysql():
    return HAVE_MY and bool(os.getenv("DB_HOST") or os.getenv("DB_USER"))

def db_kind():
    return "postgres" if _is_pg() else ("mysql" if _is_mysql() else "none")

def db():
    if _is_pg():
        dsn = _pg_dsn()
        try:
            conn = psycopg.connect(dsn, connect_timeout=10)
            return conn
        except Exception as e:
            print(f"[CTPM] db connect failed: {e}")
            return None
    if _is_mysql():
        cfg = dict(host=os.getenv("DB_HOST","localhost"),
                   user=os.getenv("DB_USER","root"),
                   password=os.getenv("DB_PASSWORD",""),
                   database=os.getenv("DB_NAME","entradas_ctpm"),
                   port=int(os.getenv("DB_PORT","3306")))
        try:
            return mysql.connector.connect(**cfg)
        except Exception:
            return None
    return None

def fetch_all(sql, params=()):
    conn = db()
    if conn is None: return []
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description] if cur.description else []
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

def fetch_one(sql, params=()):
    conn = db()
    if conn is None: return None
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    cols = [c[0] for c in cur.description] if cur.description else []
    cur.close(); conn.close()
    return dict(zip(cols, row)) if row else None

def exec_sql(sql, params=()):
    conn = db()
    if conn is None: return None
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        conn.commit()
        rowcount = cur.rowcount
        cur.close(); conn.close()
        return {"ok": True, "rowcount": rowcount}
    except Exception as e:
        try: conn.rollback()
        except: pass
        cur.close(); conn.close()
        return e
def log_audit(accion, entradas_id=None, detalle=None):
    try:
        ip = request.remote_addr if request else None
        actor = session.get("username") if session else None
        det = json.dumps(detalle) if isinstance(detalle, dict) else (str(detalle) if detalle is not None else None)
        exec_sql("INSERT INTO public.auditoria (accion, entradas_id, actor, ip, detalle) VALUES (%s,%s,%s,%s,%s::jsonb)", (accion, entradas_id, actor, ip, det))
    except Exception as e:
        print(f"[audit] {accion} err: {e}")

# --- Auth helpers ---
def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("uid"):
            if request.path.startswith("/api/"):
                return jsonify(ok=False, msg="No autenticado — inicia sesión"), 401
            return redirect(url_for("login", nxt=request.path))
        return fn(*a, **kw)
    return wrapper

def role_required(*roles):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("uid"):
                if request.path.startswith("/api/"):
                    return jsonify(ok=False, msg="No autenticado"), 401
                return redirect(url_for("login"))
            if roles and session.get("rol") not in roles:
                if request.path.startswith("/api/"):
                    return jsonify(ok=False, msg="Sin permiso"), 403
                return render_template("403.html"), 403
            return fn(*a, **kw)
        return wrapper
    return deco

def ensure_admin_user():
    """Crea admin por defecto solo si no hay ningún admin (respeta si solo queda grei)."""
    try:
        cnt = fetch_one("SELECT COUNT(*) as c FROM usuarios WHERE rol='admin'")
        if cnt and cnt["c"] > 0:
            return
        u = fetch_one("SELECT id FROM usuarios WHERE username=%s LIMIT 1", (DEMO_USER,))
        if not u:
            h = generate_password_hash(DEMO_PASS)
            r = exec_sql("INSERT INTO usuarios (username, password_hash, rol) VALUES (%s,%s,%s)",
                         (DEMO_USER, h, "admin"))
            if isinstance(r, Exception):
                print(f"[CTPM] ensure_admin_user error: {r}")
            elif r is not None:
                print(f"[CTPM] Usuario admin creado: {DEMO_USER} / {DEMO_PASS}")
    except Exception as e:
        print(f"[CTPM] ensure_admin_user omitido: {e}")
# asegurar admin también en Vercel (import, no solo __main__)
try:
    ensure_admin_user()
except:
    pass

# --- Vistas ---
@app.get("/")
def index():
    return render_template("index.html", sinpe_numero=SINPE_NUMERO, sinpe_nombre=SINPE_NOMBRE,
                           precio_gradas=PRECIO_GRADAS, precio_mesas=PRECIO_MESAS, precio_gradas_val=PRECIO_GRADAS_VAL, precio_mesas_val=PRECIO_MESAS_VAL, num_mesas=NUM_MESAS)

@app.get("/login")
def login():
    if session.get("uid"):
        return redirect(url_for("admin") if session.get("rol")=="admin" else url_for("scanner"))
    return render_template("login.html", nxt=request.args.get("nxt",""))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.get("/api/me")
def me():
    if not session.get("uid"):
        return jsonify(logged=False)
    return jsonify(logged=True, username=session.get("username"), rol=session.get("rol"))

@app.get("/admin")
@login_required
@role_required("admin")
def admin():
    return render_template("admin.html", precio_gradas_val=PRECIO_GRADAS_VAL, precio_mesas_val=PRECIO_MESAS_VAL, num_mesas=NUM_MESAS)

@app.get("/scanner")
@login_required
@role_required("portero")
def scanner():
    return render_template("scanner.html")

# --- API auth ---
@app.post("/api/login")
@rate_limited(10, 60)
def api_login():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or data.get("user") or "").strip()
    password = (data.get("password") or data.get("pass") or "")
    nxt = (data.get("nxt") or request.args.get("nxt") or "").strip()
    if not username or not password:
        return jsonify(ok=False, msg="Usuario y contraseña requeridos"), 400
    try:
        u = fetch_one("SELECT id, username, password_hash, rol FROM usuarios WHERE username=%s", (username,))
        if u and check_password_hash(u["password_hash"], password):
            session.permanent=True
            session["uid"]=u["id"]
            session["username"]=u["username"]
            session["rol"]=u["rol"]
            dest = nxt if nxt.startswith("/") else (url_for("admin") if u["rol"]=="admin" else url_for("scanner"))
            log_audit("login_ok", None, {"user": username, "rol": u["rol"]})
            return jsonify(ok=True, msg="Bienvenido", rol=u["rol"], redirect=dest)
    except Exception as e:
        print(f"[CTPM] login db err: {e}")
    log_audit("login_fail", None, {"user": username})
    return jsonify(ok=False, msg="Credenciales inválidas"), 401

# --- API: mesas disponibles ---
@app.get("/api/mesas")
def mesas_disponibles():
    try:
        rows = fetch_all("SELECT mesa_numero FROM entradas WHERE ubicacion='Mesas' AND mesa_numero IS NOT NULL AND estado IN ('Pendiente','Aprobada')")
        ocupadas = [r["mesa_numero"] for r in rows if r.get("mesa_numero")]
        todas = list(range(1, NUM_MESAS+1))
        libres = [n for n in todas if n not in ocupadas]
        return jsonify(ok=True, ocupadas=ocupadas, libres=libres, total=NUM_MESAS)
    except Exception as e:
        return jsonify(ok=False, msg=str(e)), 500

# --- API: compra ---
@app.post("/api/comprar")
@rate_limited(5, 60)
def comprar():
    nombre = request.form.get("nombre","").strip()
    cedula = request.form.get("cedula","").strip()
    ubicacion = request.form.get("ubicacion","")
    mesa_numero_raw = request.form.get("mesa_numero","").strip()
    telefono = request.form.get("telefono","").strip()
    file = request.files.get("comprobante")
    if not nombre or not cedula or ubicacion not in ("Gradas","Mesas"):
        return jsonify(ok=False, msg="Datos incompletos"), 400
    if not telefono:
        return jsonify(ok=False, msg="Ingresa tu número de WhatsApp"), 400
    if not file or file.filename == "":
        return jsonify(ok=False, msg="Sube el comprobante SINPE"), 400
    if not allowed(file.filename):
        return jsonify(ok=False, msg="Formato no permitido (jpg/png/webp/pdf)"), 400
    # Validar mesa
    mesa_numero = None
    monto = PRECIO_GRADAS_VAL if ubicacion=="Gradas" else PRECIO_MESAS_VAL
    if ubicacion == "Mesas":
        if not mesa_numero_raw:
            return jsonify(ok=False, msg="Elige el número de mesa"), 400
        try:
            mesa_numero = int(mesa_numero_raw)
        except:
            return jsonify(ok=False, msg="Mesa inválida"), 400
        if not (1 <= mesa_numero <= NUM_MESAS):
            return jsonify(ok=False, msg=f"Mesa debe ser 1 a {NUM_MESAS}"), 400
        # Verificar disponibilidad
        ocup = fetch_all("SELECT id FROM entradas WHERE ubicacion='Mesas' AND mesa_numero=%s AND estado IN ('Pendiente','Aprobada')", (mesa_numero,))
        if ocup:
            return jsonify(ok=False, msg=f"Mesa {mesa_numero} ya está ocupada"), 409
    else:
        mesa_numero = None
    eid = str(uuid.uuid4())
    codigo = generar_codigo_unico()
    ext = pathlib.Path(file.filename).suffix.lower()
    fname = f"{eid}{ext}"
    dest = UPLOAD_FOLDER / fname
    file.save(dest)
    rel = f"uploads/{fname}"
    # subir a Supabase Storage para que "Ver" no 404 en Vercel (/tmp efímero) — fallback silencioso si no hay keys
    try:
        # leer bytes del archivo guardado (file ya guardado, pero también intentar file.read)
        data_bytes = dest.read_bytes() if dest.exists() else None
        if data_bytes:
            ct = "image/jpeg" if ext in (".jpg",".jpeg") else "image/png" if ext==".png" else "image/webp" if ext==".webp" else "application/pdf" if ext==".pdf" else "application/octet-stream"
            supabase_upload(COMPROBANTES_BUCKET, fname, data_bytes, ct)
    except Exception as e:
        print(f"[comprar] supabase upload warn: {e}")
    try:
        if _is_pg():
            r = exec_sql(
                "INSERT INTO entradas (id, codigo, nombre_completo, cedula, ubicacion, mesa_numero, monto, telefono, comprobante_path) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (eid, codigo, nombre, cedula, ubicacion, mesa_numero, monto, telefono, rel))
        else:
            r = exec_sql(
                "INSERT INTO entradas (id, codigo, nombre_completo, cedula, ubicacion, mesa_numero, monto, telefono, comprobante_path) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (eid, codigo, nombre, cedula, ubicacion, mesa_numero, monto, telefono, rel))
        if isinstance(r, Exception):
            # Detectar violación de índice único de mesa
            msg = str(r)
            if "uq_mesa_ocupada" in msg or "Duplicate" in msg:
                return jsonify(ok=False, msg=f"Mesa {mesa_numero} ya fue tomada, elige otra"), 409
            return jsonify(ok=False, msg="Error al guardar en base de datos", id=eid)
        if r is None:
            return jsonify(ok=False, msg="Base de datos no disponible", id=eid)
        # obtener numero correlativo generado por DB
        row_num = fetch_one("SELECT numero FROM entradas WHERE id=%s", (eid,))
        numero = row_num.get("numero") if row_num else None
    except Exception:
        return jsonify(ok=False, msg="Error interno del servidor", id=eid)
    log_audit("comprar", eid, {"numero": numero, "codigo": codigo, "ubicacion": ubicacion, "mesa": mesa_numero, "monto": monto})
    invalidate_fin_cache()
    return jsonify(ok=True, msg=f"Comprobante recibido. Tu código es {codigo} · Entrada N° {numero or ''}. Te enviaremos tu QR por WhatsApp en máximo 48 horas.", id=eid, codigo=codigo, numero=numero)

# --- API: listar ---
@app.get("/api/entradas")
@login_required
@role_required("admin")
def listar():
    estado = request.args.get("estado","")
    ubicacion = request.args.get("ubicacion","")
    try:
        base = "SELECT id,numero,codigo,nombre_completo,cedula,ubicacion,mesa_numero,monto,telefono,comprobante_path,qr_path,estado,fecha_compra,fecha_aprobacion,fecha_uso FROM entradas"
        conds = []
        params = []
        if estado in ("Pendiente","Aprobada","Usada"):
            conds.append("estado=%s"); params.append(estado)
        if ubicacion in ("Gradas","Mesas"):
            conds.append("ubicacion=%s"); params.append(ubicacion)
        sql = base
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY fecha_compra DESC"
        rows = fetch_all(sql, tuple(params))
        for r in rows:
            for k in ("fecha_compra","fecha_aprobacion","fecha_uso"):
                if r.get(k) and isinstance(r[k], datetime):
                    r[k] = to_cr_str(r[k])
        return jsonify(rows)
    except Exception as e:
        import traceback
        print(f"[CTPM] listar error: {e}\n{traceback.format_exc()}")
        return jsonify([])

# --- API: finanzas ---  # kpi-dashboard: OLAP cache 45s evita hammer DB en dashboard en vivo
@app.get("/api/finanzas")
@login_required
@role_required("admin")
def finanzas():
    # HIT rápido sin tocar DB
    if _FIN_CACHE["data"] is not None and time.time() - _FIN_CACHE["ts"] < FIN_TTL:
        etag = _FIN_CACHE["etag"]
        if request.headers.get("If-None-Match") == etag:
            return "", 304, {"ETag": etag, "Cache-Control": "private, max-age=30, must-revalidate", "X-Cache": "HIT"}
        resp = jsonify(_FIN_CACHE["data"])
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "private, max-age=30, must-revalidate"
        resp.headers["X-Cache"] = "HIT"
        return resp
    try:
        rows = fetch_all("SELECT estado, ubicacion, COUNT(*) as cnt, COALESCE(SUM(monto),0) as total FROM entradas GROUP BY estado, ubicacion")
        all_rows = fetch_all("SELECT COUNT(*) as total_entradas, COALESCE(SUM(CASE WHEN estado IN ('Aprobada','Usada') THEN monto ELSE 0 END),0) as recaudado, COALESCE(SUM(CASE WHEN estado='Pendiente' THEN monto ELSE 0 END),0) as por_confirmar, COALESCE(SUM(CASE WHEN estado='Usada' THEN 1 ELSE 0 END),0) as usadas, COALESCE(SUM(CASE WHEN estado='Aprobada' THEN 1 ELSE 0 END),0) as aprobadas, COALESCE(SUM(CASE WHEN estado='Pendiente' THEN 1 ELSE 0 END),0) as pendientes FROM entradas")
        kpi = all_rows[0] if all_rows else {"total_entradas":0,"recaudado":0,"por_confirmar":0,"usadas":0,"aprobadas":0,"pendientes":0}
        zona = fetch_all("SELECT ubicacion, COUNT(*) as cnt, COALESCE(SUM(monto),0) as total FROM entradas GROUP BY ubicacion")
        ocupadas = fetch_all("SELECT COUNT(*) as cnt FROM entradas WHERE ubicacion='Mesas' AND mesa_numero IS NOT NULL AND estado IN ('Pendiente','Aprobada')")
        ocup_cnt = ocupadas[0]["cnt"] if ocupadas else 0
        payload = {"ok": True, "agrupado": rows, "kpi": kpi, "por_zona": zona, "mesas": {"ocupadas": ocup_cnt, "libres": NUM_MESAS - ocup_cnt, "total": NUM_MESAS}}
        # guardar
        _FIN_CACHE["data"] = payload
        _FIN_CACHE["ts"] = time.time()
        _FIN_CACHE["etag"] = _fin_etag(payload)
        resp = jsonify(payload)
        resp.headers["ETag"] = _FIN_CACHE["etag"]
        resp.headers["Cache-Control"] = "private, max-age=30, must-revalidate"
        resp.headers["X-Cache"] = "MISS"
        return resp
    except Exception as e:
        import traceback
        print(f"[CTPM] finanzas error: {e}\n{traceback.format_exc()}")
        return jsonify(ok=False, msg=str(e), tb=traceback.format_exc()), 500

# --- API: usuarios (solo admin) ---
@app.get("/api/usuarios")
@login_required
@role_required("admin")
def listar_usuarios():
    rows = fetch_all("SELECT id, username, rol, created_at FROM public.usuarios ORDER BY username")
    for r in rows:
        if r.get("created_at") and isinstance(r["created_at"], datetime):
            r["created_at"] = to_cr_str(r["created_at"])
    return jsonify(rows)

@app.post("/api/usuarios")
@login_required
@role_required("admin")
@rate_limited(10, 60)
def crear_usuario():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    rol = (data.get("rol") or "admin").strip()
    if not username or not password:
        return jsonify(ok=False, msg="Usuario y contraseña requeridos"), 400
    if rol not in ("admin","portero"):
        return jsonify(ok=False, msg="Rol inválido"), 400
    if len(username) < 3 or len(password) < 4:
        return jsonify(ok=False, msg="Usuario mínimo 3, contraseña mínimo 4"), 400
    if fetch_one("SELECT id FROM public.usuarios WHERE username=%s", (username,)):
        return jsonify(ok=False, msg="Usuario ya existe"), 409
    h = generate_password_hash(password)
    r = exec_sql("INSERT INTO public.usuarios (username, password_hash, rol) VALUES (%s,%s,%s)", (username, h, rol))
    if isinstance(r, Exception):
        return jsonify(ok=False, msg=str(r)), 500
    log_audit("crear_usuario", None, {"user": username, "rol": rol})
    return jsonify(ok=True, msg="Usuario creado")

@app.put("/api/usuarios/<int:uid>")
@login_required
@role_required("admin")
def editar_usuario(uid):
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    rol = (data.get("rol") or "").strip()
    row = fetch_one("SELECT id, username FROM public.usuarios WHERE id=%s", (uid,))
    if not row:
        return jsonify(ok=False, msg="Usuario no existe"), 404
    if username and username != row["username"] and fetch_one("SELECT id FROM public.usuarios WHERE username=%s AND id!=%s", (username, uid)):
        return jsonify(ok=False, msg="Nombre ya en uso"), 409
    sets = []
    params = []
    if username:
        if len(username) < 3:
            return jsonify(ok=False, msg="Usuario mínimo 3"), 400
        sets.append("username=%s"); params.append(username)
    if rol:
        if rol not in ("admin","portero"):
            return jsonify(ok=False, msg="Rol inválido"), 400
        sets.append("rol=%s"); params.append(rol)
    if password:
        if len(password) < 4:
            return jsonify(ok=False, msg="Contraseña mínimo 4"), 400
        sets.append("password_hash=%s"); params.append(generate_password_hash(password))
    if not sets:
        return jsonify(ok=False, msg="Nada que actualizar"), 400
    params.append(uid)
    r = exec_sql(f"UPDATE public.usuarios SET {', '.join(sets)} WHERE id=%s", tuple(params))
    if isinstance(r, Exception):
        return jsonify(ok=False, msg=str(r)), 500
    log_audit("editar_usuario", None, {"id": uid, "user": username or row["username"]})
    return jsonify(ok=True, msg="Usuario actualizado")

@app.get("/api/auditoria")
@login_required
@role_required("admin")
def listar_auditoria():
    rows = fetch_all("SELECT id, accion, entradas_id, actor, ip, detalle, created_at FROM public.auditoria ORDER BY created_at DESC LIMIT 50")
    for r in rows:
        if r.get("created_at") and isinstance(r["created_at"], datetime):
            r["created_at"] = to_cr_str(r["created_at"], "%Y-%m-%d %H:%M:%S")
        # detalle es jsonb, psycopg lo devuelve como dict o str según driver
        if isinstance(r.get("detalle"), str):
            try:
                r["detalle"] = json.loads(r["detalle"])
            except:
                pass
    return jsonify(rows)

@app.delete("/api/usuarios/<int:uid>")
@login_required
@role_required("admin")
def borrar_usuario(uid):
    row = fetch_one("SELECT id, username FROM public.usuarios WHERE id=%s", (uid,))
    if not row:
        return jsonify(ok=False, msg="Usuario no existe"), 404
    if str(session.get("uid")) == str(uid) or session.get("username") == row["username"]:
        return jsonify(ok=False, msg="No puedes borrar tu propio usuario"), 400
    cnt = fetch_one("SELECT COUNT(*) as c FROM public.usuarios WHERE rol='admin'")
    is_admin = fetch_one("SELECT rol FROM public.usuarios WHERE id=%s", (uid,))
    if is_admin and is_admin["rol"] == "admin" and cnt and cnt["c"] <= 1:
        return jsonify(ok=False, msg="Debe quedar al menos un admin"), 400
    r = exec_sql("DELETE FROM public.usuarios WHERE id=%s", (uid,))
    if isinstance(r, Exception):
        return jsonify(ok=False, msg=str(r)), 500
    log_audit("borrar_usuario", None, {"id": uid, "user": row["username"]})
    return jsonify(ok=True, msg="Usuario eliminado")

# --- QR servir en Vercel (/tmp) y local (static) ---
@app.get("/static/qrcodes/<path:fname>")
@app.get("/qrcodes/<path:fname>")
def serve_qr(fname):
    # Vercel guarda en /tmp/qrcodes, local en static/qrcodes — servir desde QR_FOLDER y regenerar si falta
    fpath = QR_FOLDER / fname
    if not fpath.exists():
        code = pathlib.Path(fname).stem
        # buscar por codigo o id::text para evitar error UUID con códigos cortos
        row = fetch_one("SELECT id,codigo FROM entradas WHERE codigo=%s OR id::text=%s", (code, code))
        if row:
            data = (row.get("codigo") or row["id"])
            try:
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=12, border=6)
                qr.add_data(data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
                fpath.parent.mkdir(parents=True, exist_ok=True)
                img.save(fpath)
            except Exception:
                pass
    if fpath.exists():
        return send_from_directory(QR_FOLDER, fname)
    return "QR no encontrado", 404

# --- API: aprobar + QR ---
@app.post("/api/aprobar/<eid>")
@login_required
@role_required("admin")
@rate_limited(20, 60)
def aprobar(eid):
    try:
        # aceptar id o codigo corto — id::text evita error UUID con códigos cortos
        row = fetch_one("SELECT * FROM entradas WHERE codigo=%s OR id::text=%s", (eid, eid))
        if not row: return jsonify(ok=False, msg="Entrada no existe"), 404
        if row["estado"] != "Pendiente":
            return jsonify(ok=False, msg=f"Ya está {row['estado']}"), 400
        # asegurar codigo corto si fila vieja sin codigo
        codigo = row.get("codigo")
        if not codigo:
            codigo = generar_codigo_unico()
            exec_sql("UPDATE entradas SET codigo=%s WHERE id=%s", (codigo, row["id"]))
            row["codigo"] = codigo
        qr_data = codigo
        # QR alta calidad: H, box 12, borde 6, fit — ahora 5 chars, QR más pequeño y rápido de escanear
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=12, border=6)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        qr_name = f"{codigo}.png"
        qr_path = QR_FOLDER / qr_name
        qr_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(qr_path, "PNG")
        qr_rel = f"static/qrcodes/{qr_name}"
        exec_sql("UPDATE entradas SET estado='Aprobada', qr_path=%s, fecha_aprobacion=%s WHERE id=%s",
                 (qr_rel, now_cr(), row["id"]))
        log_audit("aprobar", row["id"], {"codigo": codigo, "numero": row.get("numero")})
        invalidate_fin_cache()
        return jsonify(ok=True, msg=f"Aprobada — N° {row.get('numero')} · código {codigo}",
                      qr_url=url_for("serve_qr", fname=qr_name),
                      qr_path=qr_rel, id=row["id"], codigo=codigo, numero=row.get("numero"))
    except Exception as e:
        return jsonify(ok=False, msg=f"Error: {e}"), 500

@app.post("/api/rechazar/<eid>")
@login_required
@role_required("admin")
@rate_limited(20, 60)
def rechazar(eid):
    row = fetch_one("SELECT id, estado FROM entradas WHERE codigo=%s OR id::text=%s", (eid, eid))
    if not row: return jsonify(ok=False, msg="Entrada no existe"), 404
    if row["estado"] != "Pendiente":
        return jsonify(ok=False, msg=f"Ya está {row['estado']}"), 400
    r = exec_sql("DELETE FROM entradas WHERE id=%s", (row["id"],))
    if isinstance(r, Exception):
        return jsonify(ok=False, msg=str(r)), 500
    log_audit("rechazar", row["id"], {"codigo": row.get("codigo")})
    invalidate_fin_cache()
    return jsonify(ok=True, msg="Eliminada")

@app.post("/api/desbloquear/<eid>")
@login_required
@role_required("admin")
@rate_limited(20, 60)
def desbloquear(eid):
    # Libera mesa borrando la entrada (cualquier estado excepto Usada que ya liberó)
    row = fetch_one("SELECT id, estado, ubicacion, mesa_numero FROM entradas WHERE codigo=%s OR id::text=%s", (eid, eid))
    if not row: return jsonify(ok=False, msg="Entrada no existe"), 404
    if row["estado"] == "Usada":
        return jsonify(ok=False, msg="Entrada ya usada, no se puede desbloquear"), 400
    r = exec_sql("DELETE FROM entradas WHERE id=%s", (row["id"],))
    if isinstance(r, Exception):
        return jsonify(ok=False, msg=str(r)), 500
    log_audit("desbloquear", row["id"], {"mesa": row.get("mesa_numero"), "ubicacion": row.get("ubicacion")})
    invalidate_fin_cache()
    return jsonify(ok=True, msg=f"Mesa {row.get('mesa_numero') or ''} liberada" if row.get("ubicacion")=="Mesas" else "Entrada eliminada")

# --- API: validar ---
@app.post("/api/validar")
@login_required
@role_required("portero")
@rate_limited(30, 60)
def validar():
    data = request.get_json(silent=True) or {}
    raw = (data.get("id") or data.get("codigo") or request.form.get("id") or request.form.get("codigo") or "").strip()
    # normalizar código corto: sin espacios/guiones, mayúsculas
    code = raw.replace(" ", "").replace("-", "").upper()
    if not code: return jsonify(ok=False, estado="NO_EXISTE", msg="QR vacío"), 400
    try:
        # buscar por codigo (nuevo, 5 chars) o por id::text (compatibilidad vieja) — id::text evita error UUID
        row = fetch_one("SELECT * FROM entradas WHERE codigo=%s OR id::text=%s", (code, raw))
        if not row: return jsonify(ok=False, estado="NO_EXISTE", msg="Entrada no existe"), 404
        if row["estado"] == "Usada":
            return jsonify(ok=False, estado="USADA", msg="Entrada YA USADA",
                          nombre=row["nombre_completo"], ubicacion=row["ubicacion"], mesa_numero=row.get("mesa_numero"), monto=row.get("monto"), codigo=row.get("codigo"), numero=row.get("numero"))
        if row["estado"] == "Pendiente":
            return jsonify(ok=False, estado="PENDIENTE", msg="Entrada pendiente de aprobación"), 403
        # usar id interno para update (codigo es solo alias humano)
        rid = row["id"]
        r = exec_sql("UPDATE entradas SET estado='Usada', fecha_uso=%s WHERE id=%s AND estado='Aprobada'",
                     (now_cr(), rid))
        if isinstance(r, Exception):
            return jsonify(ok=False, estado="ERROR", msg=f"Error: {r}"), 500
        if r["rowcount"] == 0:
            row2 = fetch_one("SELECT estado FROM entradas WHERE id=%s", (rid,))
            if row2 and row2["estado"] == "Usada":
                return jsonify(ok=False, estado="USADA", msg="Ya fue usada (carrera)",
                              nombre=row["nombre_completo"], ubicacion=row["ubicacion"], mesa_numero=row.get("mesa_numero"))
            return jsonify(ok=False, estado="PENDIENTE", msg="Entrada pendiente de aprobación",
                          nombre=row["nombre_completo"], ubicacion=row["ubicacion"])
        log_audit("validar", rid, {"codigo": row.get("codigo"), "numero": row.get("numero"), "resultado": "VALIDA"})
        invalidate_fin_cache()
        return jsonify(ok=True, estado="VALIDA", msg="¡ENTRADA VÁLIDA!",
                      nombre=row["nombre_completo"], ubicacion=row["ubicacion"], cedula=row["cedula"], mesa_numero=row.get("mesa_numero"), monto=row.get("monto"), codigo=row.get("codigo"), numero=row.get("numero"))
    except Exception as e:
        return jsonify(ok=False, estado="ERROR", msg=f"Error: {e}"), 500

@app.get("/api/historial")
@login_required
@role_required("portero")
def historial():
    if session.get("rol") not in ("portero",):
        return jsonify(ok=False, msg="No autorizado"), 403
    rows = fetch_all("SELECT id, codigo, nombre_completo, cedula, ubicacion, mesa_numero, fecha_uso FROM entradas WHERE estado='Usada' ORDER BY fecha_uso DESC LIMIT 20")
    for r in rows:
        if r.get("fecha_uso") and isinstance(r["fecha_uso"], datetime):
            r["fecha_uso"] = to_cr_str(r["fecha_uso"])
    return jsonify(rows)

@app.post("/api/revertir/<codigo>")
@login_required
@role_required("portero")
def revertir(codigo):
    if session.get("rol") not in ("portero",):
        return jsonify(ok=False, msg="No autorizado"), 403
    code = codigo.strip().upper()
    row = fetch_one("SELECT id, estado, codigo FROM entradas WHERE codigo=%s", (code,))
    if not row:
        return jsonify(ok=False, msg="Código no encontrado"), 404
    if row["estado"] != "Usada":
        return jsonify(ok=False, msg=f"Solo se puede revertir Usada, está {row['estado']}"), 400
    r = exec_sql("UPDATE entradas SET estado='Aprobada', fecha_uso=NULL WHERE id=%s", (row["id"],))
    if isinstance(r, Exception):
        return jsonify(ok=False, msg=str(r)), 500
    log_audit("revertir", row["id"], {"codigo": code})
    invalidate_fin_cache()
    return jsonify(ok=True, msg=f"Código {code} revertido a Aprobada")

@app.get("/uploads/<path:fname>")
@login_required
def uploads(fname):
    # 1) intentar local (/tmp o static)
    fpath = UPLOAD_FOLDER / fname
    if fpath.exists():
        return send_from_directory(UPLOAD_FOLDER, fname)
    # 2) fallback Supabase Storage (fix "Ver" 404 en Vercel)
    data = supabase_download(COMPROBANTES_BUCKET, fname)
    if data:
        content, ctype = data
        return send_file(io.BytesIO(content), mimetype=ctype, download_name=fname)
    return "Comprobante no encontrado", 404

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.get("/robots.txt")
def robots():
    return send_from_directory("static", "robots.txt", mimetype="text/plain")

@app.get("/sitemap.xml")
def sitemap():
    return send_from_directory("static", "sitemap.xml", mimetype="application/xml")

@app.get("/health")
def health():
    conn = db()
    if conn is None: return jsonify(ok=True, db=db_kind())
    try: conn.close()
    except: pass
    return jsonify(ok=True, db=db_kind())

if __name__ == "__main__":
    ensure_admin_user()
    print(f"[CTPM] DB: {db_kind()}")
    app.run(debug=True, host="0.0.0.0", port=5000)
