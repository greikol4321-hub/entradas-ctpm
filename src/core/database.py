"""DB helpers — Pool Supavisor + g.pg_conn — ponytail: 1 pool, sin ORM"""
import os, time, json, hashlib, threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import g

try:
    import psycopg
    HAVE_PG = True
    try:
        from psycopg_pool import ConnectionPool
        HAVE_POOL = True
    except ImportError:
        HAVE_POOL = False
except ImportError:
    HAVE_PG = False
    HAVE_POOL = False
_PG_POOL = None
try:
    import mysql.connector
    HAVE_MY = True
except ImportError:
    HAVE_MY = False

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

# constantes compartidas
NUM_MESAS = 12
PRECIO_GRADAS_VAL = 5000
PRECIO_MESAS_VAL = 10000
PRECIO_GRADAS = "₡5.000"
PRECIO_MESAS = "₡10.000"

# cache helpers (se mantienen aquí por compatibilidad, pero finance_service es la fuente)
_FIN_CACHE = {"data": None, "ts": 0, "etag": None}
FIN_TTL = 45
_ENTRADAS_CACHE = {}
ENTRADAS_TTL = 15
_MESAS_CACHE = {"data": None, "ts": 0, "etag": None}
MESAS_TTL = 30

def _etag(data): return hashlib.md5(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:12]
def _fin_etag(data): return _etag(data)

def _pg_dsn():
    return os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")

def _is_pg():
    dsn = _pg_dsn()
    return bool(dsn) and HAVE_PG

def _get_pool():
    global _PG_POOL
    if not HAVE_PG or not HAVE_POOL:
        return None
    if _PG_POOL is not None:
        return _PG_POOL
    dsn = _pg_dsn()
    if not dsn:
        return None
    try:
        # Supavisor Transaction pooler (6543) — min 1 max 5, evita 800ms por checkout
        _PG_POOL = ConnectionPool(dsn, min_size=1, max_size=5, timeout=10, kwargs={"connect_timeout":10}, open=True)
        return _PG_POOL
    except Exception:
        return None

def _is_mysql():
    return HAVE_MY and bool(os.getenv("DB_HOST") or os.getenv("DB_USER"))

def db_kind():
    return "postgres" if _is_pg() else ("mysql" if _is_mysql() else "none")

def db():
    # intenta pool primero (Supavisor 6543, 1 pool por proceso)
    pool = _get_pool()
    if pool is not None:
        try:
            # getconn es sync; pool.connection() es context manager pero getconn permite close->putconn
            return pool.getconn()
        except: pass
    if _is_pg():
        dsn = _pg_dsn()
        try:
            conn = psycopg.connect(dsn, connect_timeout=10)
            return conn
        except Exception as e:
            try:
                from flask import current_app
                current_app.logger.error(f"[CTPM] db connect failed: {e}")
            except: pass
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

def _get_conn():
    try:
        if 'pg_conn' in g:
            c = g.pg_conn
            try:
                if c.closed == 0:
                    return c
            except: pass
        c = db()
        if c is not None:
            try: g.pg_conn = c
            except: pass
        return c
    except:
        return db()

def _close_conn_pooled(conn):
    # asegura transacción limpia antes de devolver al pool (evita "rolling back returned connection")
    try:
        if conn.closed == 0:
            try: conn.rollback()
            except: pass
    except: pass
    pool = _get_pool()
    if pool is not None and HAVE_POOL:
        try:
            pool.putconn(conn)
            return
        except: pass
    try: conn.close()
    except: pass

def _close_pg_conn(exc):
    try:
        c = g.pop('pg_conn', None)
        if c is not None:
            _close_conn_pooled(c)
    except: pass

def init_db(app):
    # ponytail: 1 conexión por request, teardown simple
    app.teardown_appcontext(_close_pg_conn)

def fetch_all(sql, params=()):
    conn = db()
    if conn is None: return []
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description] if cur.description else []
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close(); _close_conn_pooled(conn)
    return rows

def fetch_one(sql, params=()):
    conn = db()
    if conn is None: return None
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    cols = [c[0] for c in cur.description] if cur.description else []
    cur.close(); _close_conn_pooled(conn)
    return dict(zip(cols, row)) if row else None

def exec_sql(sql, params=()):
    conn = db()
    if conn is None: return None
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        conn.commit()
        rowcount = cur.rowcount
        cur.close(); _close_conn_pooled(conn)
        return {"ok": True, "rowcount": rowcount}
    except Exception as e:
        try: conn.rollback()
        except: pass
        cur.close(); _close_conn_pooled(conn)
        return e

def _load_finanzas_payload():
    conn = db()
    if conn is None:
        raise Exception("DB no disponible")
    cur = conn.cursor()
    cur.execute("SELECT estado, ubicacion, COUNT(*) as cnt, COALESCE(SUM(monto),0) as total FROM entradas GROUP BY estado, ubicacion")
    cols = [c[0] for c in cur.description] if cur.description else []
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) as total_entradas, COALESCE(SUM(CASE WHEN estado IN ('Aprobada','Usada') THEN monto ELSE 0 END),0) as recaudado, COALESCE(SUM(CASE WHEN estado='Pendiente' THEN monto ELSE 0 END),0) as por_confirmar, COALESCE(SUM(CASE WHEN estado='Usada' THEN 1 ELSE 0 END),0) as usadas, COALESCE(SUM(CASE WHEN estado='Aprobada' THEN 1 ELSE 0 END),0) as aprobadas, COALESCE(SUM(CASE WHEN estado='Pendiente' THEN 1 ELSE 0 END),0) as pendientes FROM entradas")
    cols2 = [c[0] for c in cur.description] if cur.description else []
    all_rows = [dict(zip(cols2, r)) for r in cur.fetchall()]
    kpi = all_rows[0] if all_rows else {"total_entradas":0,"recaudado":0,"por_confirmar":0,"usadas":0,"aprobadas":0,"pendientes":0}
    cur.execute("SELECT ubicacion, COUNT(*) as cnt, COALESCE(SUM(monto),0) as total FROM entradas GROUP BY ubicacion")
    cols3 = [c[0] for c in cur.description] if cur.description else []
    zona = [dict(zip(cols3, r)) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) as cnt FROM entradas WHERE ubicacion='Mesas' AND mesa_numero IS NOT NULL AND estado IN ('Pendiente','Aprobada')")
    cols4 = [c[0] for c in cur.description] if cur.description else []
    ocupadas = [dict(zip(cols4, r)) for r in cur.fetchall()]
    ocup_cnt = ocupadas[0]["cnt"] if ocupadas else 0
    cur.close(); _close_conn_pooled(conn)
    return {"ok": True, "agrupado": rows, "kpi": kpi, "por_zona": zona, "mesas": {"ocupadas": ocup_cnt, "libres": NUM_MESAS - ocup_cnt, "total": NUM_MESAS}}

def log_audit(accion, entradas_id=None, detalle=None):
    try:
        from flask import request, session
        import json as _json
        ip = request.remote_addr if request else None
        actor = session.get("username") if session else None
        det = _json.dumps(detalle) if isinstance(detalle, dict) else (str(detalle) if detalle is not None else None)
        exec_sql("INSERT INTO public.auditoria (accion, entradas_id, actor, ip, detalle) VALUES (%s,%s,%s,%s,%s::jsonb)", (accion, entradas_id, actor, ip, det))
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.warning(f"[audit] {accion} err: {e}")
        except: pass

# warmup / caches compartidos para compatibilidad
def invalidate_fin_cache():
    if _FIN_CACHE["data"] is not None:
        _FIN_CACHE["ts"] = 0
        if not os.getenv("VERCEL"):
            try: threading.Thread(target=_refresh_fin_cache_bg, daemon=True).start()
            except: pass
    else:
        _FIN_CACHE["data"] = None
        _FIN_CACHE["ts"] = 0
        _FIN_CACHE["etag"] = None

def _refresh_fin_cache_bg():
    try:
        payload = _load_finanzas_payload()
        _FIN_CACHE["data"] = payload
        _FIN_CACHE["ts"] = time.time()
        _FIN_CACHE["etag"] = _etag(payload)
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.warning(f"[finanzas bg refresh] {e}")
        except: pass

def _refresh_entradas_bg(cache_key, estado, ubicacion):
    try:
        base = "SELECT id,numero,codigo,nombre_completo,cedula,ubicacion,mesa_numero,monto,telefono,comprobante_path,qr_path,estado,fecha_compra,fecha_aprobacion,fecha_uso FROM entradas"
        conds=[]; params=[]
        if estado in ("Pendiente","Aprobada","Usada"):
            conds.append("estado=%s"); params.append(estado)
        if ubicacion in ("Gradas","Mesas"):
            conds.append("ubicacion=%s"); params.append(ubicacion)
        sql=base
        if conds: sql+=" WHERE "+" AND ".join(conds)
        sql+=" ORDER BY fecha_compra DESC"
        rows=fetch_all(sql, tuple(params))
        for r in rows:
            for k in ("fecha_compra","fecha_aprobacion","fecha_uso"):
                if r.get(k) and isinstance(r[k], datetime):
                    r[k]=to_cr_str(r[k])
        etag=_etag(rows)
        _ENTRADAS_CACHE[cache_key]={"data": rows, "ts": time.time(), "etag": etag}
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.warning(f"[entradas bg refresh] {e}")
        except: pass

def _refresh_mesas_bg():
    try:
        rows=fetch_all("SELECT mesa_numero FROM entradas WHERE ubicacion='Mesas' AND mesa_numero IS NOT NULL AND estado IN ('Pendiente','Aprobada')")
        ocupadas=[r["mesa_numero"] for r in rows if r.get("mesa_numero")]
        todas=list(range(1, NUM_MESAS+1))
        libres=[n for n in todas if n not in ocupadas]
        payload={"ok": True, "ocupadas": ocupadas, "libres": libres, "total": NUM_MESAS}
        etag=_etag(payload)
        _MESAS_CACHE["data"]=payload
        _MESAS_CACHE["ts"]=time.time()
        _MESAS_CACHE["etag"]=etag
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.warning(f"[mesas bg refresh] {e}")
        except: pass

def invalidate_all_cache():
    invalidate_fin_cache()
    for k in list(_ENTRADAS_CACHE.keys()):
        _ENTRADAS_CACHE[k]["ts"]=0
        if not os.getenv("VERCEL"):
            try:
                estado, ubic=k.split(":")
                threading.Thread(target=_refresh_entradas_bg, args=(k, estado, ubic), daemon=True).start()
            except: pass
    if _MESAS_CACHE["data"] is not None:
        _MESAS_CACHE["ts"]=0
        if not os.getenv("VERCEL"):
            try: threading.Thread(target=_refresh_mesas_bg, daemon=True).start()
            except: pass
    else:
        _MESAS_CACHE["data"]=None
        _MESAS_CACHE["ts"]=0
        _MESAS_CACHE["etag"]=None

def _warm_all_bg():
    try: _refresh_fin_cache_bg()
    except: pass
    try: _refresh_entradas_bg(":", "", "")
    except: pass
    try: _refresh_mesas_bg()
    except: pass
