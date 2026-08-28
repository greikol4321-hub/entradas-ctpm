"""
Sistema CTPM — Venta y validación de entradas
Soporta Postgres (Supabase) via DATABASE_URL o MySQL via variables DB_*
"""
import os, uuid, pathlib, functools
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_from_directory, url_for, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
from dotenv import load_dotenv
load_dotenv()

try:
    import psycopg
    from psycopg.rows import dict_row
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

SINPE_NUMERO = os.getenv("SINPE_NUMERO", "8888-8888")
SINPE_NOMBRE = os.getenv("SINPE_NOMBRE", "Asociación CTPM")
PRECIO_GRADAS = "₡5.000"
PRECIO_MESAS  = "₡10.000"
DEMO_USER = "admin"
DEMO_PASS = "admin123"

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
            conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=False, connect_timeout=3)
            return conn
        except Exception:
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
                return jsonify(ok=False, msg="Sin permiso"), 403 if request.path.startswith("/api/") else (render_template("403.html"), 403)
            return fn(*a, **kw)
        return wrapper
    return deco

def ensure_admin_user():
    """Crea admin por defecto si la tabla está vacía (Postgres o MySQL)."""
    try:
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

# --- Vistas ---
@app.get("/")
def index():
    return render_template("index.html", sinpe_numero=SINPE_NUMERO, sinpe_nombre=SINPE_NOMBRE,
                           precio_gradas=PRECIO_GRADAS, precio_mesas=PRECIO_MESAS)

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
    return render_template("admin.html")

@app.get("/scanner")
@login_required
def scanner():
    return render_template("scanner.html")

# --- API auth ---
@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or data.get("user") or "").strip()
    password = (data.get("password") or data.get("pass") or "")
    nxt = (data.get("nxt") or request.args.get("nxt") or "").strip()
    if not username or not password:
        return jsonify(ok=False, msg="Usuario y contraseña requeridos"), 400
    # intenta BD
    try:
        u = fetch_one("SELECT id, username, password_hash, rol FROM usuarios WHERE username=%s", (username,))
        if u and check_password_hash(u["password_hash"], password):
            session.permanent=True
            session["uid"]=u["id"]
            session["username"]=u["username"]
            session["rol"]=u["rol"]
            dest = nxt if nxt.startswith("/") else (url_for("admin") if u["rol"]=="admin" else url_for("scanner"))
            return jsonify(ok=True, msg="Bienvenido", rol=u["rol"], redirect=dest)
    except Exception:
        pass
    # acceso por defecto cuando no hay BD
    if username==DEMO_USER and password==DEMO_PASS:
        session.permanent=True
        session["uid"]="demo-admin"
        session["username"]=DEMO_USER
        session["rol"]="admin"
        dest = nxt if nxt.startswith("/") else url_for("admin")
        return jsonify(ok=True, msg="Bienvenido", rol="admin", redirect=dest)
    return jsonify(ok=False, msg="Credenciales inválidas"), 401

# --- API: compra ---
@app.post("/api/comprar")
def comprar():
    nombre = request.form.get("nombre","").strip()
    cedula = request.form.get("cedula","").strip()
    ubicacion = request.form.get("ubicacion","")
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
    eid = str(uuid.uuid4())
    ext = pathlib.Path(file.filename).suffix.lower()
    fname = f"{eid}{ext}"
    dest = UPLOAD_FOLDER / fname
    file.save(dest)
    rel = f"uploads/{fname}"
    try:
        if _is_pg():
            r = exec_sql(
                "INSERT INTO entradas (id, nombre_completo, cedula, ubicacion, telefono, comprobante_path) VALUES (%s,%s,%s,%s,%s,%s)",
                (eid, nombre, cedula, ubicacion, telefono, rel))
        else:
            r = exec_sql(
                "INSERT INTO entradas (id, nombre_completo, cedula, ubicacion, comprobante_path, telefono) VALUES (%s,%s,%s,%s,%s,%s)",
                (eid, nombre, cedula, ubicacion, rel, telefono))
        if isinstance(r, Exception):
            return jsonify(ok=False, msg="Error al guardar en base de datos", id=eid)
        if r is None:
            return jsonify(ok=False, msg="Base de datos no disponible", id=eid)
    except Exception:
        return jsonify(ok=False, msg="Error interno del servidor", id=eid)
    return jsonify(ok=True, msg="Comprobante recibido. Te enviaremos tu entrada por WhatsApp en máximo 48 horas.", id=eid)

# --- API: listar ---
@app.get("/api/entradas")
@login_required
def listar():
    estado = request.args.get("estado","")
    try:
        if estado in ("Pendiente","Aprobada","Usada"):
            rows = fetch_all("SELECT id,nombre_completo,cedula,ubicacion,telefono,comprobante_path,qr_path,estado,fecha_compra,fecha_aprobacion,fecha_uso FROM entradas WHERE estado=%s ORDER BY fecha_compra DESC", (estado,))
        else:
            rows = fetch_all("SELECT id,nombre_completo,cedula,ubicacion,telefono,comprobante_path,qr_path,estado,fecha_compra,fecha_aprobacion,fecha_uso FROM entradas ORDER BY fecha_compra DESC")
        for r in rows:
            for k in ("fecha_compra","fecha_aprobacion","fecha_uso"):
                if r.get(k):
                    v = r[k]
                    if isinstance(v, datetime):
                        r[k] = v.strftime("%Y-%m-%d %H:%M")
        return jsonify(rows)
    except Exception:
        return jsonify([])

# --- API: aprobar + QR ---
@app.post("/api/aprobar/<eid>")
@login_required
@role_required("admin")
def aprobar(eid):
    try:
        row = fetch_one("SELECT * FROM entradas WHERE id=%s", (eid,))
        if not row: return jsonify(ok=False, msg="Entrada no existe"), 404
        if row["estado"] != "Pendiente":
            return jsonify(ok=False, msg=f"Ya está {row['estado']}"), 400
        img = qrcode.make(eid)
        qr_name = f"{eid}.png"
        qr_path = QR_FOLDER / qr_name
        img.save(qr_path)
        qr_rel = f"static/qrcodes/{qr_name}"
        exec_sql("UPDATE entradas SET estado='Aprobada', qr_path=%s, fecha_aprobacion=%s WHERE id=%s",
                 (qr_rel, datetime.now(), eid))
        return jsonify(ok=True, msg="Aprobada y QR generado",
                      qr_url=url_for("static", filename=f"qrcodes/{qr_name}"),
                      qr_path=qr_rel, id=eid)
    except Exception as e:
        return jsonify(ok=False, msg=f"Error: {e}"), 500

@app.post("/api/rechazar/<eid>")
@login_required
@role_required("admin")
def rechazar(eid):
    row = fetch_one("SELECT estado FROM entradas WHERE id=%s", (eid,))
    if not row: return jsonify(ok=False, msg="Entrada no existe"), 404
    if row["estado"] != "Pendiente":
        return jsonify(ok=False, msg=f"Ya está {row['estado']}"), 400
    r = exec_sql("DELETE FROM entradas WHERE id=%s", (eid,))
    if isinstance(r, Exception):
        return jsonify(ok=False, msg=str(r)), 500
    return jsonify(ok=True, msg="Eliminada")

# --- API: validar ---
@app.post("/api/validar")
@login_required
def validar():
    data = request.get_json(silent=True) or {}
    eid = (data.get("id") or request.form.get("id") or "").strip()
    if not eid: return jsonify(ok=False, estado="NO_EXISTE", msg="QR vacío"), 400
    try:
        row = fetch_one("SELECT * FROM entradas WHERE id=%s", (eid,))
        if not row: return jsonify(ok=False, estado="NO_EXISTE", msg="Entrada no existe"), 404
        if row["estado"] == "Usada":
            return jsonify(ok=False, estado="USADA", msg="Entrada YA USADA",
                          nombre=row["nombre_completo"], ubicacion=row["ubicacion"])
        if row["estado"] == "Pendiente":
            return jsonify(ok=False, estado="PENDIENTE", msg="Entrada pendiente de aprobación"), 403
        # Aprobada -> marcar Usada
        r = exec_sql("UPDATE entradas SET estado='Usada', fecha_uso=%s WHERE id=%s AND estado='Aprobada'",
                     (datetime.now(), eid))
        if isinstance(r, Exception):
            return jsonify(ok=False, estado="ERROR", msg=f"Error: {r}"), 500
        if r["rowcount"] == 0:
            row2 = fetch_one("SELECT estado FROM entradas WHERE id=%s", (eid,))
            if row2 and row2["estado"] == "Usada":
                return jsonify(ok=False, estado="USADA", msg="Ya fue usada (carrera)",
                              nombre=row["nombre_completo"], ubicacion=row["ubicacion"])
            return jsonify(ok=False, estado="PENDIENTE", msg="Entrada pendiente de aprobación",
                          nombre=row["nombre_completo"], ubicacion=row["ubicacion"])
        return jsonify(ok=True, estado="VALIDA", msg="¡ENTRADA VÁLIDA!",
                      nombre=row["nombre_completo"], ubicacion=row["ubicacion"], cedula=row["cedula"])
    except Exception as e:
        return jsonify(ok=False, estado="ERROR", msg=f"Error: {e}"), 500

@app.get("/uploads/<path:fname>")
@login_required
def uploads(fname):
    return send_from_directory(UPLOAD_FOLDER, fname)

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

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
