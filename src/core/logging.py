"""Logging estructurado + X-Request-ID + Sentry — extraído de app.py"""
import os, sys, json, time, uuid, logging as _logging
from flask import g, request

def setup_logging(app):
    _logging.basicConfig(level=_logging.INFO, format="%(message)s", stream=sys.stdout)
    for h in app.logger.handlers:
        h.setFormatter(_logging.Formatter("%(message)s"))
    # warning si secret dev
    try:
        sec = app.config.get("SECRET_KEY", "")
        if not sec or sec.startswith("ctpm-dev"):
            app.logger.warning(json.dumps({"event": "warn_flask_secret_dev", "request_id": "startup"}))
    except: pass
    if os.getenv("SENTRY_DSN"):
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), integrations=[FlaskIntegration()], traces_sample_rate=0.1, environment=os.getenv("VERCEL_ENV", "production"))
            app.logger.info(json.dumps({"event": "sentry_init", "request_id": "startup"}))
        except Exception as e:
            app.logger.warning(json.dumps({"event": "sentry_init_failed", "error": str(e), "request_id": "startup"}))

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

# ponytail: JsonFormatter simple — sin deps, usa json.dumps
class JsonFormatter(_logging.Formatter):
    def format(self, record):
        try:
            return json.dumps({"level": record.levelname, "msg": record.getMessage(), "time": self.formatTime(record)})
        except:
            return super().format(record)
