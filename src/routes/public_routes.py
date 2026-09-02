"""Public routes — /, /api/mesas, /api/comprar, /health, /static/qrcodes, /uploads"""
import pathlib, hashlib, time, io
from flask import Blueprint, request, jsonify, render_template, send_from_directory, send_file, url_for, session
import src.core.database as database
import src.core.storage as storage
import src.core.security as security
import src.services.finance_service as finance_service

public_bp = Blueprint("public", __name__)

def init_public(app, upload_folder, qr_folder, sinpe_numero, sinpe_nombre):
    @public_bp.get("/")
    def index():
        return render_template("index.html", sinpe_numero=sinpe_numero, sinpe_nombre=sinpe_nombre,
                               precio_gradas=database.PRECIO_GRADAS, precio_mesas=database.PRECIO_MESAS,
                               precio_gradas_val=database.PRECIO_GRADAS_VAL, precio_mesas_val=database.PRECIO_MESAS_VAL, num_mesas=database.NUM_MESAS)

    @public_bp.get("/login")
    def login():
        if session.get("uid"):
            try:
                dest_a = url_for("admin.admin")
            except:
                dest_a = "/admin"
            try:
                dest_s = url_for("scanner.scanner")
            except:
                dest_s = "/scanner"
            return __import__("flask").redirect(dest_a if session.get("rol")=="admin" else dest_s)
        return render_template("login.html", nxt=request.args.get("nxt",""))

    @public_bp.get("/logout")
    def logout():
        session.clear()
        try:
            return __import__("flask").redirect(url_for("public.index"))
        except:
            return __import__("flask").redirect("/")

    @public_bp.get("/api/me")
    def me():
        if not session.get("uid"):
            return jsonify(logged=False)
        return jsonify(logged=True, username=session.get("username"), rol=session.get("rol"))

    @public_bp.get("/api/mesas")
    def mesas_disponibles():
        # usa finance_service cache
        if database._MESAS_CACHE["data"] is not None:
            age = time.time() - database._MESAS_CACHE["ts"]
            if age < database.MESAS_TTL:
                if request.headers.get("If-None-Match") == database._MESAS_CACHE["etag"]:
                    return "", 304, {"ETag": database._MESAS_CACHE["etag"], "Cache-Control": "public, max-age=30, must-revalidate", "X-Cache": "HIT"}
                resp = jsonify(database._MESAS_CACHE["data"])
                resp.headers["ETag"] = database._MESAS_CACHE["etag"]
                resp.headers["Cache-Control"] = "public, max-age=30, must-revalidate"
                resp.headers["X-Cache"] = "HIT"
                return resp
            else:
                if request.headers.get("If-None-Match") == database._MESAS_CACHE["etag"]:
                    import os, threading
                    if not os.getenv("VERCEL"):
                        try: threading.Thread(target=database._refresh_mesas_bg, daemon=True).start()
                        except: pass
                    return "", 304, {"ETag": database._MESAS_CACHE["etag"], "Cache-Control": "public, max-age=30, stale-while-revalidate=30", "X-Cache": "STALE"}
                resp = jsonify(database._MESAS_CACHE["data"])
                resp.headers["ETag"] = database._MESAS_CACHE["etag"]
                resp.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=30"
                resp.headers["X-Cache"] = "STALE"
                import os, threading
                if not os.getenv("VERCEL"):
                    try: threading.Thread(target=database._refresh_mesas_bg, daemon=True).start()
                    except: pass
                return resp
        try:
            payload, etag, _ = finance_service.get_mesas_cached()
            # get_mesas_cached already set cache, but handle MISS
            if request.headers.get("If-None-Match") == etag:
                return "", 304, {"ETag": etag, "Cache-Control": "public, max-age=30, must-revalidate", "X-Cache": "MISS"}
            resp = jsonify(payload)
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = "public, max-age=30, must-revalidate"
            resp.headers["X-Cache"] = "MISS"
            return resp
        except Exception as e:
            return jsonify(ok=False, msg=str(e)), 500

    @public_bp.post("/api/comprar")
    @security.rate_limited(5, 60)
    def comprar():
        # validación Pydantic + lógica comprar
        from src.schemas.ticket import CompraIn
        from pydantic import ValidationError
        nombre = request.form.get("nombre","").strip()
        cedula = request.form.get("cedula","").strip()
        ubicacion = request.form.get("ubicacion","")
        mesa_numero_raw = request.form.get("mesa_numero","").strip()
        telefono = request.form.get("telefono","").strip()
        file = request.files.get("comprobante")
        # checks rápidos antes de Pydantic (compat con tests)
        if not nombre or not cedula or ubicacion not in ("Gradas","Mesas"):
            return jsonify(ok=False, msg="Datos incompletos"), 400
        if not telefono:
            return jsonify(ok=False, msg="Ingresa tu número de WhatsApp"), 400
        if not file or file.filename == "":
            return jsonify(ok=False, msg="Sube el comprobante SINPE"), 400
        if pathlib.Path(file.filename).suffix.lower() not in {".jpg",".jpeg",".png",".webp",".pdf"}:
            return jsonify(ok=False, msg="Formato no permitido (jpg/png/webp/pdf)"), 400
        # ponytail: valida magic bytes, no solo extensión (evita polyglot)
        try:
            peek = file.stream.read(12); file.stream.seek(0)
            is_pdf = peek[:4] == b"%PDF"
            is_jpg = peek[:2] == b"\xff\xd8"
            is_png = peek[:8] == b"\x89PNG\r\n\x1a\n"
            is_webp = peek[:4] == b"RIFF" and b"WEBP" in peek
            if not (is_pdf or is_jpg or is_png or is_webp):
                return jsonify(ok=False, msg="Archivo no parece imagen/PDF válido"), 400
        except: pass
        # Pydantic validación extra
        try:
            CompraIn(nombre_completo=nombre, cedula=cedula, ubicacion=ubicacion, mesa_numero=mesa_numero_raw or None, telefono=telefono)
        except ValidationError as ve:
            # mapear a mensajes esperados por tests
            msg = str(ve.errors()[0].get("ctx",{}).get("error") or ve.errors()[0].get("msg"))
            if "cédula" in msg.lower():
                return jsonify(ok=False, msg=msg), 400
            if "teléfono" in msg.lower() or "telefono" in msg.lower():
                return jsonify(ok=False, msg=msg), 400
            if "mesa" in msg.lower():
                return jsonify(ok=False, msg=msg), 400
            return jsonify(ok=False, msg=msg), 400
        try:
            file_bytes = file.read()
            if not file_bytes:
                return jsonify(ok=False, msg="Comprobante vacío"), 400
            if len(file_bytes) > 8*1024*1024:
                return jsonify(ok=False, msg="Archivo muy grande"), 400
            # verify imagen real con Pillow cuando no es PDF
            if pathlib.Path(file.filename).suffix.lower() != ".pdf":
                try:
                    from PIL import Image
                    import io as _io
                    im = Image.open(_io.BytesIO(file_bytes))
                    im.verify()
                except Exception:
                    return jsonify(ok=False, msg="Imagen corrupta o no válida"), 400
        except Exception as e:
            if "corrupta" in str(e) or "válida" in str(e):
                return jsonify(ok=False, msg=str(e)), 400
            return jsonify(ok=False, msg="No se pudo leer el comprobante"), 400
        # delegar a ticket_service (usa 1 conexión FOR UPDATE)
        import src.services.ticket_service as ticket_service
        # para compatibilidad con tests que mockean generar_codigo_unico en app, ticket_service ya propaga
        result = ticket_service.comprar_ticket(nombre, cedula, ubicacion, mesa_numero_raw, telefono, file_bytes, file.filename, upload_folder)
        if not result["ok"]:
            return jsonify(ok=False, msg=result["msg"]), result.get("code", 400)
        return jsonify(ok=True, msg=f"Comprobante recibido. Tu código es {result['codigo']} · Entrada N° {result['numero'] or ''}. Te enviaremos tu QR por WhatsApp en máximo 48 horas.", id=result["id"], codigo=result["codigo"], numero=result["numero"])

    @public_bp.get("/static/qrcodes/<path:fname>")
    @public_bp.get("/qrcodes/<path:fname>")
    def serve_qr(fname):
        # ponytail: path traversal guard
        if ".." in fname or fname.startswith("/") or "\\" in fname:
            return "No encontrado", 404
        safe = pathlib.Path(fname).name
        if safe != fname and "/" in fname:
            return "No encontrado", 404
        import src.services.qr_service as qr_service
        return qr_service.serve_qr_logic(safe, qr_folder)

    @public_bp.get("/uploads/<path:fname>")
    @security.login_required
    def uploads(fname):
        if ".." in fname or fname.startswith("/") or "\\" in fname:
            return "No encontrado", 404
        safe = pathlib.Path(fname).name
        if safe != fname and "/" in fname:
            return "No encontrado", 404
        fpath = upload_folder / safe
        if fpath.exists():
            return send_from_directory(upload_folder, safe)
        data = storage.supabase_download(storage.COMPROBANTES_BUCKET, safe)
        if data:
            content, ctype = data
            return send_file(io.BytesIO(content), mimetype=ctype, download_name=safe)
        return "Comprobante no encontrado", 404

    @public_bp.get("/health")
    def health():
        conn = database.db()
        if conn is None: return jsonify(ok=True, db=database.db_kind())
        try: conn.close()
        except: pass
        return jsonify(ok=True, db=database.db_kind())

    @public_bp.get("/robots.txt")
    def robots():
        return send_from_directory("static", "robots.txt", mimetype="text/plain")

    @public_bp.get("/sitemap.xml")
    def sitemap():
        return send_from_directory("static", "sitemap.xml", mimetype="application/xml")

    app.register_blueprint(public_bp)
