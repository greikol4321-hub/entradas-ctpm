"""Finance service — cache SWR finanzas — ponytail: dict en memoria, sin redis"""
import time, threading, os
import src.core.database as database

# re-export caches para compatibilidad con app.py (misma referencia)
_FIN_CACHE = database._FIN_CACHE
FIN_TTL = database.FIN_TTL
_ENTRADAS_CACHE = database._ENTRADAS_CACHE
ENTRADAS_TTL = database.ENTRADAS_TTL
_MESAS_CACHE = database._MESAS_CACHE
MESAS_TTL = database.MESAS_TTL

def get_finanzas_cached():
    # SWR: fresco <TTL → HIT, viejo → STALE sirve instant + refresca bg (Vercel: fresh directo)
    if _FIN_CACHE["data"] is not None:
        age = time.time() - _FIN_CACHE["ts"]
        if age < FIN_TTL:
            return _FIN_CACHE["data"], _FIN_CACHE["etag"], "HIT"
        else:
            if os.getenv("VERCEL"):
                pass  # ponytail: en Vercel sin bg thread, caer a MISS y traer DB fresca
            else:
                try: threading.Thread(target=database._refresh_fin_cache_bg, daemon=True).start()
                except: pass
                return _FIN_CACHE["data"], _FIN_CACHE["etag"], "STALE"
    # MISS memoria → probar Upstash (capa distribuida) antes de DB
    uhit = database.ucache_get("finanzas")
    if uhit:
        _FIN_CACHE["data"] = uhit
        _FIN_CACHE["ts"] = time.time()
        _FIN_CACHE["etag"] = database._etag(uhit)
        return uhit, _FIN_CACHE["etag"], "HIT-U"
    payload = database._load_finanzas_payload()
    _FIN_CACHE["data"] = payload
    _FIN_CACHE["ts"] = time.time()
    _FIN_CACHE["etag"] = database._etag(payload)
    try: threading.Thread(target=database.ucache_set, args=("finanzas", payload, FIN_TTL), daemon=True).start()
    except Exception: pass
    return payload, _FIN_CACHE["etag"], "MISS"

def get_mesas_cached():
    if _MESAS_CACHE["data"] is not None:
        age = time.time() - _MESAS_CACHE["ts"]
        if age < MESAS_TTL:
            return _MESAS_CACHE["data"], _MESAS_CACHE["etag"], "HIT"
        else:
            if os.getenv("VERCEL"):
                pass
            else:
                try: threading.Thread(target=database._refresh_mesas_bg, daemon=True).start()
                except: pass
                return _MESAS_CACHE["data"], _MESAS_CACHE["etag"], "STALE"
    uhit = database.ucache_get("mesas")
    if uhit:
        _MESAS_CACHE["data"] = uhit
        _MESAS_CACHE["ts"] = time.time()
        _MESAS_CACHE["etag"] = database._etag(uhit)
        return uhit, _MESAS_CACHE["etag"], "HIT-U"
    rows = database.fetch_all("SELECT mesa_numero FROM entradas WHERE ubicacion='Mesas' AND mesa_numero IS NOT NULL AND estado IN ('Pendiente','Aprobada','Usada')")
    ocupadas = [r["mesa_numero"] for r in rows if r.get("mesa_numero")]
    todas = list(range(1, database.NUM_MESAS+1))
    libres = [n for n in todas if n not in ocupadas]
    payload = {"ok": True, "ocupadas": ocupadas, "libres": libres, "total": database.NUM_MESAS}
    etag = database._etag(payload)
    _MESAS_CACHE["data"] = payload
    _MESAS_CACHE["ts"] = time.time()
    _MESAS_CACHE["etag"] = etag
    try: threading.Thread(target=database.ucache_set, args=("mesas", payload, MESAS_TTL), daemon=True).start()
    except Exception: pass
    return payload, etag, "MISS"

def get_entradas_cached(estado, ubicacion, page=1, limit=50):
    # ponytail: paginación para evitar OOM (50 por defecto)
    try: page = max(1, int(page))
    except: page = 1
    try: limit = min(100, max(1, int(limit)))
    except: limit = 50
    offset = (page - 1) * limit
    cache_key = f"{estado}:{ubicacion}:{page}:{limit}"
    ent = _ENTRADAS_CACHE.get(cache_key)
    if ent:
        age = time.time() - ent["ts"]
        if age < ENTRADAS_TTL:
            return ent["data"], ent["etag"], "HIT"
        else:
            if os.getenv("VERCEL"):
                pass
            else:
                try: threading.Thread(target=database._refresh_entradas_bg, args=(cache_key, estado, ubicacion), daemon=True).start()
                except: pass
                return ent["data"], ent["etag"], "STALE"
    # MISS memoria → Upstash (key incluye paginación)
    uhit = database.ucache_get(f"entradas:{cache_key}")
    if uhit:
        _ENTRADAS_CACHE[cache_key] = {"data": uhit, "ts": time.time(), "etag": database._etag(uhit)}
        return uhit, _ENTRADAS_CACHE[cache_key]["etag"], "HIT-U"
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
    sql += " ORDER BY fecha_compra DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    rows = database.fetch_all(sql, tuple(params))
    for r in rows:
        for k in ("fecha_compra","fecha_aprobacion","fecha_uso"):
            if r.get(k) and hasattr(r[k], "strftime"):
                from datetime import datetime
                if isinstance(r[k], datetime):
                    r[k] = database.to_cr_str(r[k])
    etag = database._etag(rows)
    _ENTRADAS_CACHE[cache_key] = {"data": rows, "ts": time.time(), "etag": etag}
    try: threading.Thread(target=database.ucache_set, args=(f"entradas:{cache_key}", rows, ENTRADAS_TTL), daemon=True).start()
    except Exception: pass
    return rows, etag, "MISS"
