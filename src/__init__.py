"""Factory create_app — Application Factory + Blueprints — ponytail: sin deps, 1 conexión"""
import os, pathlib, sys, json, time, uuid, logging as _logging
from datetime import timedelta
from flask import Flask, g, request

# constantes re-exportables para compatibilidad
from src.core.database import NUM_MESAS, PRECIO_GRADAS, PRECIO_MESAS, PRECIO_GRADAS_VAL, PRECIO_MESAS_VAL

def create_app():
    from dotenv import load_dotenv
    load_dotenv()
    app = Flask(__name__, template_folder=str(pathlib.Path(__file__).parent.parent / "templates"), static_folder=str(pathlib.Path(__file__).parent.parent / "static"))
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # Vercel es el único proxy — IP real para rate-limit
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
    _flask_secret = os.getenv("FLASK_SECRET")
    if not _flask_secret:
        if os.getenv("VERCEL") or os.getenv("FLASK_ENV") == "production":
            raise RuntimeError("FLASK_SECRET es obligatorio en producción — configúralo en Vercel env / .env")
        _flask_secret = "ctpm-dev-secret-cambia-en-produccion-2026"
    app.config['SECRET_KEY'] = _flask_secret
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
    app.config['SESSION_COOKIE_SECURE'] = bool(os.getenv("VERCEL"))
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # logging + request_id (antes core/logging.py, fusionado)
    _logging.basicConfig(level=_logging.INFO, format="%(message)s", stream=sys.stdout)
    for h in app.logger.handlers:
        h.setFormatter(_logging.Formatter("%(message)s"))
    try:
        sec = app.config.get("SECRET_KEY", "")
        if not sec or sec.startswith("ctpm-dev"):
            app.logger.warning(json.dumps({"event": "warn_flask_secret_dev", "request_id": "startup"}))
    except: pass

    @app.before_request
    def _set_request_id():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        g._t0 = time.time()

    @app.after_request
    def _log_request(resp):
        try:
            dur = int((time.time() - getattr(g, "_t0", time.time())) * 1000)
            app.logger.info(json.dumps({"event": "request", "request_id": getattr(g, "request_id", "-"), "method": request.method, "path": request.path, "status": resp.status_code, "duration_ms": dur, "ip": request.remote_addr, "user": __import__("flask").session.get("username")}))
        except: pass
        return resp

    # security headers
    from src.core.security import security_headers_middleware
    security_headers_middleware(app)

    # db teardown
    from src.core.database import init_db
    init_db(app)

    # folders
    BASE = pathlib.Path(__file__).parent.parent
    if os.getenv("VERCEL"):
        UPLOAD_FOLDER = pathlib.Path("/tmp") / "uploads"  # nosec B108 - Vercel serverless
        QR_FOLDER = pathlib.Path("/tmp") / "qrcodes"  # nosec B108 - Vercel serverless
    else:
        UPLOAD_FOLDER = BASE / "uploads"
        QR_FOLDER = BASE / "static" / "qrcodes"
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    QR_FOLDER.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
    app.config["QR_FOLDER"] = str(QR_FOLDER)
    # guardar referencias para compatibilidad
    app.UPLOAD_FOLDER = UPLOAD_FOLDER
    app.QR_FOLDER = QR_FOLDER

    SINPE_NUMERO = os.getenv("SINPE_NUMERO", "8888-8888")
    SINPE_NOMBRE = os.getenv("SINPE_NOMBRE", "Asociación CTPM")

    # credenciales admin (solo vía env en prod)
    _INITIAL_USER = os.getenv("INITIAL_ADMIN_USER") or os.getenv("DEMO_USER")
    _INITIAL_PASS = os.getenv("INITIAL_ADMIN_PASSWORD") or os.getenv("DEMO_PASS")
    if os.getenv("VERCEL"):
        DEMO_USER = _INITIAL_USER
        DEMO_PASS = _INITIAL_PASS
    else:
        DEMO_USER = _INITIAL_USER or "admin"
        DEMO_PASS = _INITIAL_PASS or "admin123"
        if not _INITIAL_USER:
            try: app.logger.warning(f"[WARN] INITIAL_ADMIN_USER no configurado — usando {DEMO_USER}/*** solo para desarrollo")
            except: pass
    app.config["DEMO_USER"] = DEMO_USER
    app.config["DEMO_PASS"] = DEMO_PASS

    # registrar blueprints
    from src.routes.public_routes import init_public
    from src.routes.admin_routes import init_admin
    from src.routes.scanner_routes import init_scanner
    init_public(app, UPLOAD_FOLDER, QR_FOLDER, SINPE_NUMERO, SINPE_NOMBRE)
    init_admin(app, QR_FOLDER)
    init_scanner(app)

    # 404 handler y health ya en public, pero añadimos 404 global si no registrado
    from flask import render_template
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    # warmup solo local
    if not os.getenv("VERCEL"):
        try:
            import threading
            from src.core.database import _warm_all_bg
            threading.Thread(target=_warm_all_bg, daemon=True).start()
        except: pass

    # ensure admin (import, no solo __main__)
    try:
        from src.services.user_service import ensure_admin_user
        ensure_admin_user(DEMO_USER, DEMO_PASS, app.logger)
    except:
        pass

    return app
