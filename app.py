"""
Sistema CTPM — shim de compatibilidad (modularizado)
Mantiene `from app import app` para Vercel/server.py y expone símbolos legacy
para que tests que hacen `import app as appmod; monkeypatch.setattr(appmod, "db", ...)` sigan pasando.

La lógica real vive en src/* (ponytail: 1 conexión, sin pool, sin deps nuevas).
"""
import os, sys, types, pathlib

# ponytail: propagación de monkeypatch app -> src (sin redis, sin pool)
class _PatchedModule(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        # propaga a todos los módulos src que tengan ese atributo (para que `monkeypatch.setattr(app, "db", fake)` afecte a src)
        for mod_name in (
            "src.core.database",
            "src.core.storage",
            "src.core.security",
            "src.core.logging",
            "src.services.ticket_service",
            "src.services.finance_service",
            "src.services.user_service",
            "src.services.qr_service",
            "src.routes.public_routes",
            "src.routes.admin_routes",
            "src.routes.scanner_routes",
            "src.schemas.ticket",
            "src.schemas.user",
        ):
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, name):
                try:
                    setattr(mod, name, value)
                except: pass

# convertir este módulo en PatchedModule para interceptar setattr de pytest monkeypatch
sys.modules[__name__].__class__ = _PatchedModule

from src import create_app
app = create_app()

# re-export para compatibilidad con tests y código legacy que hace `import app; app.db()`
# database
from src.core.database import (
    db, _get_conn, fetch_all, fetch_one, exec_sql, db_kind, _pg_dsn, _is_pg, _is_mysql,
    _load_finanzas_payload, to_cr_str, now_cr, log_audit,
    invalidate_all_cache, invalidate_fin_cache, _etag, _fin_etag,
    _FIN_CACHE, _ENTRADAS_CACHE, _MESAS_CACHE,
    NUM_MESAS, PRECIO_GRADAS_VAL, PRECIO_MESAS_VAL, PRECIO_GRADAS, PRECIO_MESAS,
    CR_TZ, FIN_TTL, ENTRADAS_TTL, MESAS_TTL, init_db,
    _refresh_fin_cache_bg, _refresh_entradas_bg, _refresh_mesas_bg, _warm_all_bg,
)
# storage
from src.core.storage import supabase_upload, supabase_delete, supabase_download, _supabase_headers, COMPROBANTES_BUCKET, SUPABASE_URL, SUPABASE_SERVICE_KEY
# security
from src.core.security import allow_rate, rate_limited, login_required, role_required, RATE_LIMIT, security_headers_middleware
# tickets
from src.services.ticket_service import generar_codigo, generar_codigo_unico

# constantes y helpers que estaban en app.py top-level y algunos tests los leen
import pathlib as _pl
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
    return _pl.Path(fname).suffix.lower() in ALLOWED_EXT

SINPE_NUMERO = os.getenv("SINPE_NUMERO", "8888-8888")
SINPE_NOMBRE = os.getenv("SINPE_NOMBRE", "Asociación CTPM")

# admin creds para compatibilidad (app.DEMO_USER no se usa directo, pero se expone)
DEMO_USER = app.config.get("DEMO_USER")
DEMO_PASS = app.config.get("DEMO_PASS")

# re-export ensure_admin
from src.services.user_service import ensure_admin_user

# alias para Vercel: server.py hace `from app import app` → ya está
# también exponer create_app para quien importe `from app import create_app`
create_app = create_app

if __name__ == "__main__":
    try:
        ensure_admin_user(DEMO_USER, DEMO_PASS, app.logger)
    except: pass
    app.logger.info(f"[CTPM] DB: {db_kind()}")
    app.run(debug=True, host="0.0.0.0", port=5000)
