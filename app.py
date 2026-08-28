"""
Sistema CTPM — Venta y validación de entradas
Soporta Postgres (Supabase) via DATABASE_URL o MySQL via variables DB_*
Mesas numeradas + Finanzas
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
            conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=False, connect_timeout=10)
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
    if username==DEMO_USER and password==DEMO_PASS:
        session.permanent=True
        session["uid"]="demo-admin"
        session["username"]=DEMO_USER
        session["rol"]="admin"
        dest = nxt if nxt.startswith("/") else url_for("admin")
        return jsonify(ok=True, msg="Bienvenido", rol="admin", redirect=dest)
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
    ext = pathlib.Path(file.filename).suffix.lower()
    fname = f"{eid}{ext}"
    dest = UPLOAD_FOLDER / fname
    file.save(dest)
    rel = f"uploads/{fname}"
    try:
        if _is_pg():
            r = exec_sql(
                "INSERT INTO entradas (id, nombre_completo, cedula, ubicacion, mesa_numero, monto, telefono, comprobante_path) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (eid, nombre, cedula, ubicacion, mesa_numero, monto, telefono, rel))
        else:
            r = exec_sql(
                "INSERT INTO entradas (id, nombre_completo, cedula, ubicacion, mesa_numero, monto, telefono, comprobante_path) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (eid, nombre, cedula, ubicacion, mesa_numero, monto, telefono, rel))
        if isinstance(r, Exception):
            # Detectar violación de índice único de mesa
            msg = str(r)
            if "uq_mesa_ocupada" in msg or "Duplicate" in msg:
                return jsonify(ok=False, msg=f"Mesa {mesa_numero} ya fue tomada, elige otra"), 409
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
    ubicacion = request.args.get("ubicacion","")
    try:
        base = "SELECT id,nombre_completo,cedula,ubicacion,mesa_numero,monto,telefono,comprobante_path,qr_path,estado,fecha_compra,fecha_aprobacion,fecha_uso FROM entradas"
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
                if r.get(k):
                    v = r[k]
                    if isinstance(v, datetime):
                        r[k] = v.strftime("%Y-%m-%d %H:%M")
        return jsonify(rows)
    except Exception as e:
        import traceback
        print(f"[CTPM] listar error: {e}\n{traceback.format_exc()}")
        return jsonify([])

# --- API: finanzas ---
@app.get("/api/finanzas")
@login_required
@role_required("admin")
def finanzas():
    try:
        rows = fetch_all("SELECT estado, ubicacion, COUNT(*) as cnt, COALESCE(SUM(monto),0) as total FROM entradas GROUP BY estado, ubicacion")
        # Totales globales
        all_rows = fetch_all("SELECT COUNT(*) as total_entradas, COALESCE(SUM(CASE WHEN estado IN ('Aprobada','Usada') THEN monto ELSE 0 END),0) as recaudado, COALESCE(SUM(CASE WHEN estado='Pendiente' THEN monto ELSE 0 END),0) as por_confirmar, COALESCE(SUM(CASE WHEN estado='Usada' THEN 1 ELSE 0 END),0) as usadas FROM entradas")
        kpi = all_rows[0] if all_rows else {"total_entradas":0,"recaudado":0,"por_confirmar":0,"usadas":0}
        # Por zona
        zona = fetch_all("SELECT ubicacion, COUNT(*) as cnt, COALESCE(SUM(monto),0) as total FROM entradas GROUP BY ubicacion")
        # Mesas ocupadas/libres
        ocupadas = fetch_all("SELECT COUNT(*) as cnt FROM entradas WHERE ubicacion='Mesas' AND mesa_numero IS NOT NULL AND estado IN ('Pendiente','Aprobada')")
        ocup_cnt = ocupadas[0]["cnt"] if ocupadas else 0
        return jsonify(ok=True, agrupado=rows, kpi=kpi, por_zona=zona, mesas={"ocupadas": ocup_cnt, "libres": NUM_MESAS - ocup_cnt, "total": NUM_MESAS})
    except Exception as e:
        import traceback
        print(f"[CTPM] finanzas error: {e}\n{traceback.format_exc()}")
        return jsonify(ok=False, msg=str(e), tb=traceback.format_exc()), 500

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

@app.post("/api/desbloquear/<eid>")
@login_required
@role_required("admin")
def desbloquear(eid):
    # Libera mesa borrando la entrada (cualquier estado excepto Usada que ya liberó)
    row = fetch_one("SELECT estado, ubicacion, mesa_numero FROM entradas WHERE id=%s", (eid,))
    if not row: return jsonify(ok=False, msg="Entrada no existe"), 404
    if row["estado"] == "Usada":
        return jsonify(ok=False, msg="Entrada ya usada, no se puede desbloquear"), 400
    r = exec_sql("DELETE FROM entradas WHERE id=%s", (eid,))
    if isinstance(r, Exception):
        return jsonify(ok=False, msg=str(r)), 500
    return jsonify(ok=True, msg=f"Mesa {row.get('mesa_numero') or ''} liberada" if row.get("ubicacion")=="Mesas" else "Entrada eliminada")

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
                          nombre=row["nombre_completo"], ubicacion=row["ubicacion"], mesa_numero=row.get("mesa_numero"), monto=row.get("monto"))
        if row["estado"] == "Pendiente":
            return jsonify(ok=False, estado="PENDIENTE", msg="Entrada pendiente de aprobación"), 403
        r = exec_sql("UPDATE entradas SET estado='Usada', fecha_uso=%s WHERE id=%s AND estado='Aprobada'",
                     (datetime.now(), eid))
        if isinstance(r, Exception):
            return jsonify(ok=False, estado="ERROR", msg=f"Error: {r}"), 500
        if r["rowcount"] == 0:
            row2 = fetch_one("SELECT estado FROM entradas WHERE id=%s", (eid,))
            if row2 and row2["estado"] == "Usada":
                return jsonify(ok=False, estado="USADA", msg="Ya fue usada (carrera)",
                              nombre=row["nombre_completo"], ubicacion=row["ubicacion"], mesa_numero=row.get("mesa_numero"))
            return jsonify(ok=False, estado="PENDIENTE", msg="Entrada pendiente de aprobación",
                          nombre=row["nombre_completo"], ubicacion=row["ubicacion"])
        return jsonify(ok=True, estado="VALIDA", msg="¡ENTRADA VÁLIDA!",
                      nombre=row["nombre_completo"], ubicacion=row["ubicacion"], cedula=row["cedula"], mesa_numero=row.get("mesa_numero"), monto=row.get("monto"))
    except Exception as e:
        return jsonify(ok=False, estado="ERROR", msg=f"Error: {e}"), 500

@app.get("/uploads/<path:fname>")
@login_required
def uploads(fname):
    return send_from_directory(UPLOAD_FOLDER, fname)

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.get("/api/debug")
def debug():
    import traceback
    try:
        dsn = _pg_dsn() or ""
        safe = dsn.split("@")[-1] if "@" in dsn else dsn
        # raw psycopg without dict_row
        raw = {}
        try:
            import psycopg
            conn2 = psycopg.connect(dsn, connect_timeout=5)
            cur2 = conn2.cursor()
            cur2.execute("SELECT id, nombre_completo, cedula, ubicacion, mesa_numero, monto, estado FROM entradas ORDER BY fecha_compra DESC LIMIT 2")
            cols = [c[0] for c in cur2.description]
            fetched = cur2.fetchall()
            raw = {"cols": cols, "fetched": [list(r) for r in fetched], "fetched_str": str(fetched[:1])}
            cur2.close(); conn2.close()
        except Exception as e2:
            raw = {"err": str(e2), "tb": traceback.format_exc()}
        # also try via REST
        rest_rows = []
        rest_err = None
        try:
            import urllib.request, json as js
            url = "https://jyfmimxzhpvcezwilkdd.supabase.co/rest/v1/entradas?select=id,nombre_completo,cedula&limit=2"
            headers = {"apikey": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp5Zm1pbXh6aHB2Y2V6d2lsa2RkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc5NDQzMDEsImV4cCI6MjEwMzUyMDMwMX0.a1PvzU7FqTX8fgS7W_GI4ssd1JeGrRNiYbCOCp7G2Rc", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp5Zm1pbXh6aHB2Y2V6d2lsa2RkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc5NDQzMDEsImV4cCI6MjEwMzUyMDMwMX0.a1PvzU7FqTX8fgS7W_GI4ssd1JeGrRNiYbCOCp7G2Rc"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                rest_rows = js.loads(r.read().decode())
        except Exception as e3:
            rest_err = str(e3)
        rows = fetch_all("SELECT id, nombre_completo, cedula, ubicacion, mesa_numero, monto, estado FROM entradas ORDER BY fecha_compra DESC LIMIT 5")
        return jsonify(ok=True, rows=rows, count=len(rows), db=db_kind(), safe_dsn=safe, raw=raw, rest_rows=rest_rows, rest_err=rest_err)
    except Exception as e:
        return jsonify(ok=False, msg=str(e), tb=traceback.format_exc(), db=db_kind()), 500

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
