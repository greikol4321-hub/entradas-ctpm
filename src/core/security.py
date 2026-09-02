"""Security: SECRET_KEY check, rate limit, permissions — Upstash Redis distribuido + fallback in-memory"""
import os, time, functools, json
from collections import defaultdict, deque
from flask import request, jsonify, session, redirect, url_for, render_template

# fallback in-memory (local dev / si Upstash no configurado)
RATE_LIMIT = defaultdict(deque)

def _upstash_allow_rate(key, limit, window):
    url = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None  # no configurado → fallback
    try:
        import urllib.request, urllib.error
        # INCR + EXPIRE vía pipeline REST: https://upstash.com/docs/redis/features/restapi
        # Usamos EVAL con script deslizante si disponible, fallback a INCR
        full_key = f"ratelimit:{key}"
        # INCR
        req = urllib.request.Request(f"{url}/incr/{full_key}", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            count = int(data.get("result", 1))
            if count == 1:
                # primera vez → EXPIRE
                req2 = urllib.request.Request(f"{url}/expire/{full_key}/{window}", headers={"Authorization": f"Bearer {token}"})
                try: urllib.request.urlopen(req2, timeout=2).read()
                except: pass
            return count <= limit
    except Exception:
        return None  # fallback a memoria

def allow_rate(key, limit, window=60):
    # intenta Upstash distribuido primero (Vercel multi-instancia)
    up = _upstash_allow_rate(key, limit, window)
    if up is not None:
        return up
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

def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("uid"):
            if request.path.startswith("/api/"):
                return jsonify(ok=False, msg="No autenticado — inicia sesión"), 401
            # ponytail: endpoint con blueprint es public.login, fallback a login legacy
            try:
                return redirect(url_for("public.login", nxt=request.path))
            except:
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
                try:
                    return redirect(url_for("public.login"))
                except:
                    return redirect(url_for("login"))
            if roles and session.get("rol") not in roles:
                if request.path.startswith("/api/"):
                    return jsonify(ok=False, msg="Sin permiso"), 403
                return render_template("403.html"), 403
            return fn(*a, **kw)
        return wrapper
    return deco

def security_headers_middleware(app):
    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self' https://*.supabase.co; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if os.getenv("VERCEL"):
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # web-performance: cache
        try:
            import hashlib
            p = request.path
            ctype = resp.headers.get("Content-Type", "")
            if p.startswith("/static/"):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                resp.headers["Vary"] = "Accept-Encoding"
            elif p == "/api/finanzas":
                if "Cache-Control" not in resp.headers:
                    resp.headers["Cache-Control"] = "private, max-age=30, must-revalidate"
                resp.headers["Vary"] = "Cookie"
            elif p.startswith("/api/"):
                if "Cache-Control" not in resp.headers:
                    resp.headers["Cache-Control"] = "private, max-age=10, must-revalidate"
                resp.headers["Vary"] = "Cookie"
            elif "text/html" in ctype and resp.status_code == 200:
                body = resp.get_data()
                etag = hashlib.md5(body).hexdigest()[:12]
                if request.headers.get("If-None-Match") == etag:
                    return app.response_class("", 304, headers={"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate", "Vary": "Cookie"})
                resp.headers["ETag"] = etag
                if "Cache-Control" not in resp.headers:
                    resp.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
                resp.headers["Vary"] = "Cookie"
        except: pass
        return resp
