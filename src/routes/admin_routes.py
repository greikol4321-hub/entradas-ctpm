"""Admin routes — /admin, /api/entradas, /api/finanzas, /api/usuarios, /api/auditoria, /api/aprobar, etc."""
import time, json, hashlib
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, url_for, session
from werkzeug.security import generate_password_hash
import src.core.database as database
import src.core.security as security
import src.services.finance_service as finance_service
import src.services.user_service as user_service

admin_bp = Blueprint("admin", __name__)

def init_admin(app, qr_folder):
    @admin_bp.get("/admin")
    @security.login_required
    @security.role_required("admin")
    def admin():
        return render_template("admin.html", precio_gradas_val=database.PRECIO_GRADAS_VAL, precio_mesas_val=database.PRECIO_MESAS_VAL, num_mesas=database.NUM_MESAS)

    @admin_bp.post("/api/login")
    @security.rate_limited(10, 60)
    def api_login():
        data = request.get_json(silent=True) or request.form
        username = (data.get("username") or data.get("user") or "").strip()
        password = (data.get("password") or data.get("pass") or "")
        nxt = (data.get("nxt") or request.args.get("nxt") or "").strip()
        if not username or not password:
            return jsonify(ok=False, msg="Usuario y contraseña requeridos"), 400
        try:
            u = database.fetch_one("SELECT id, username, password_hash, rol FROM usuarios WHERE username=%s", (username,))
            from werkzeug.security import check_password_hash
            if u and check_password_hash(u["password_hash"], password):
                session.permanent=True
                session["uid"]=u["id"]
                session["username"]=u["username"]
                session["rol"]=u["rol"]
                # url_for con blueprint: admin.admin / scanner.scanner, fallback a path
                try:
                    dest_a = url_for("admin.admin")
                except:
                    dest_a = "/admin"
                try:
                    dest_s = url_for("scanner.scanner")
                except:
                    dest_s = "/scanner"
                dest = nxt if nxt.startswith("/") else (dest_a if u["rol"]=="admin" else dest_s)
                database.log_audit("login_ok", None, {"user": username, "rol": u["rol"]})
                return jsonify(ok=True, msg="Bienvenido", rol=u["rol"], redirect=dest)
        except Exception as e:
            try: app.logger.warning(f"[CTPM] login db err: {e}")
            except: pass
        database.log_audit("login_fail", None, {"user": username})
        return jsonify(ok=False, msg="Credenciales inválidas"), 401

    @admin_bp.get("/api/entradas")
    @security.login_required
    @security.role_required("admin")
    def listar():
        estado = request.args.get("estado","")
        ubicacion = request.args.get("ubicacion","")
        cache_key = f"{estado}:{ubicacion}"
        ent = database._ENTRADAS_CACHE.get(cache_key)
        if ent:
            age = time.time() - ent["ts"]
            if age < database.ENTRADAS_TTL:
                if request.headers.get("If-None-Match") == ent["etag"]:
                    return "", 304, {"ETag": ent["etag"], "Cache-Control": "private, max-age=10, must-revalidate", "X-Cache": "HIT"}
                resp = jsonify(ent["data"])
                resp.headers["ETag"] = ent["etag"]
                resp.headers["Cache-Control"] = "private, max-age=10, must-revalidate"
                resp.headers["X-Cache"] = "HIT"
                return resp
            else:
                import os, threading
                if os.getenv("VERCEL"):
                    pass  # ponytail: en Vercel sin bg, no servir STALE — caer a MISS fresco
                else:
                    if request.headers.get("If-None-Match") == ent["etag"]:
                        try: threading.Thread(target=database._refresh_entradas_bg, args=(cache_key, estado, ubicacion), daemon=True).start()
                        except: pass
                        return "", 304, {"ETag": ent["etag"], "Cache-Control": "private, max-age=10, stale-while-revalidate=15", "X-Cache": "STALE"}
                    resp = jsonify(ent["data"])
                    resp.headers["ETag"] = ent["etag"]
                    resp.headers["Cache-Control"] = "private, max-age=10, stale-while-revalidate=15"
                    resp.headers["X-Cache"] = "STALE"
                    try: threading.Thread(target=database._refresh_entradas_bg, args=(cache_key, estado, ubicacion), daemon=True).start()
                    except: pass
                    return resp
        try:
            rows, etag, _ = finance_service.get_entradas_cached(estado, ubicacion)
            resp = jsonify(rows)
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = "private, max-age=10, must-revalidate"
            resp.headers["X-Cache"] = "MISS"
            return resp
        except Exception as e:
            import traceback
            try: app.logger.error(f"[CTPM] listar error: {e}\n{traceback.format_exc()}")
            except: pass
            return jsonify([])

    @admin_bp.get("/api/finanzas")
    @security.login_required
    @security.role_required("admin")
    def finanzas():
        if database._FIN_CACHE["data"] is not None:
            etag = database._FIN_CACHE["etag"]
            age = time.time() - database._FIN_CACHE["ts"]
            if age < database.FIN_TTL:
                if request.headers.get("If-None-Match") == etag:
                    return "", 304, {"ETag": etag, "Cache-Control": "private, max-age=30, must-revalidate", "X-Cache": "HIT"}
                resp = jsonify(database._FIN_CACHE["data"])
                resp.headers["ETag"] = etag
                resp.headers["Cache-Control"] = "private, max-age=30, must-revalidate"
                resp.headers["X-Cache"] = "HIT"
                return resp
            else:
                import os, threading
                if os.getenv("VERCEL"):
                    pass  # ponytail: en Vercel caer a MISS fresco, no STALE congelado
                else:
                    if request.headers.get("If-None-Match") == etag:
                        try: threading.Thread(target=database._refresh_fin_cache_bg, daemon=True).start()
                        except: pass
                        return "", 304, {"ETag": etag, "Cache-Control": "private, max-age=30, stale-while-revalidate=30", "X-Cache": "STALE"}
                    resp = jsonify(database._FIN_CACHE["data"])
                    resp.headers["ETag"] = etag
                    resp.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=30"
                    resp.headers["X-Cache"] = "STALE"
                    try: threading.Thread(target=database._refresh_fin_cache_bg, daemon=True).start()
                    except: pass
                    return resp
        try:
            payload, etag, _ = finance_service.get_finanzas_cached()
            resp = jsonify(payload)
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = "private, max-age=30, must-revalidate"
            resp.headers["X-Cache"] = "MISS"
            return resp
        except Exception as e:
            import traceback
            try: app.logger.error(f"[CTPM] finanzas error: {e}\n{traceback.format_exc()}")
            except: pass
            return jsonify(ok=False, msg=str(e), tb=traceback.format_exc()), 500

    @admin_bp.get("/api/usuarios")
    @security.login_required
    @security.role_required("admin")
    def listar_usuarios():
        rows = user_service.list_users()
        return jsonify(rows)

    @admin_bp.post("/api/usuarios")
    @security.login_required
    @security.role_required("admin")
    @security.rate_limited(10, 60)
    def crear_usuario():
        data = request.get_json() or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        rol = (data.get("rol") or "admin").strip()
        # validación Pydantic
        try:
            from src.schemas.user import UserCreate
            UserCreate(username=username, password=password, rol=rol)
        except Exception as e:
            # extraer mensaje
            try:
                from pydantic import ValidationError
                if isinstance(e, ValidationError):
                    return jsonify(ok=False, msg=str(e.errors()[0].get("msg"))), 400
            except: pass
            return jsonify(ok=False, msg=str(e)), 400
        r = user_service.create_user(username, password, rol)
        if not r["ok"]:
            return jsonify(ok=False, msg=r["msg"]), r["code"]
        return jsonify(ok=True, msg="Usuario creado")

    @admin_bp.put("/api/usuarios/<int:uid>")
    @security.login_required
    @security.role_required("admin")
    def editar_usuario(uid):
        data = request.get_json() or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        rol = (data.get("rol") or "").strip()
        r = user_service.update_user(uid, username or None, password or None, rol or None)
        if not r["ok"]:
            return jsonify(ok=False, msg=r["msg"]), r["code"]
        return jsonify(ok=True, msg="Usuario actualizado")

    @admin_bp.delete("/api/usuarios/<int:uid>")
    @security.login_required
    @security.role_required("admin")
    def borrar_usuario(uid):
        r = user_service.delete_user(uid, session.get("uid"), session.get("username"))
        if not r["ok"]:
            return jsonify(ok=False, msg=r["msg"]), r["code"]
        return jsonify(ok=True, msg="Usuario eliminado")

    @admin_bp.get("/api/auditoria")
    @security.login_required
    @security.role_required("admin")
    def listar_auditoria():
        # solo 3 eventos clave: aprobar (admin) + validar (escaneo portero) + revertir — con hora y quien
        rows = database.fetch_all("SELECT id, accion, entradas_id, actor, detalle, created_at FROM public.auditoria WHERE accion IN ('aprobar','validar','revertir') ORDER BY created_at DESC LIMIT 50")
        for r in rows:
            if r.get("created_at") and isinstance(r["created_at"], datetime):
                r["created_at"] = database.to_cr_str(r["created_at"], "%Y-%m-%d %H:%M")
            if isinstance(r.get("detalle"), str):
                try: r["detalle"] = json.loads(r["detalle"])
                except: pass
        return jsonify(rows)

    @admin_bp.post("/api/aprobar/<eid>")
    @security.login_required
    @security.role_required("admin")
    @security.rate_limited(20, 60)
    def aprobar(eid):
        try:
            row = database.fetch_one("SELECT * FROM entradas WHERE codigo=%s OR id::text=%s", (eid, eid))
            if not row: return jsonify(ok=False, msg="Entrada no existe"), 404
            if row["estado"] != "Pendiente":
                return jsonify(ok=False, msg=f"Ya está {row['estado']}"), 400
            codigo = row.get("codigo")
            if not codigo:
                import src.services.ticket_service as ts
                codigo = ts.generar_codigo_unico()
                database.exec_sql("UPDATE entradas SET codigo=%s WHERE id=%s", (codigo, row["id"]))
                row["codigo"] = codigo
            import src.services.qr_service as qr_service
            qr_name, qr_rel = qr_service.generar_qr(codigo, qr_folder)
            database.exec_sql("UPDATE entradas SET estado='Aprobada', qr_path=%s, fecha_aprobacion=%s WHERE id=%s", (qr_rel, database.now_cr(), row["id"]))
            database.log_audit("aprobar", row["id"], {"codigo": codigo, "numero": row.get("numero")})
            database.invalidate_all_cache()
            try:
                qr_url = url_for("public.serve_qr", fname=qr_name)
            except:
                qr_url = f"/static/qrcodes/{qr_name}"
            return jsonify(ok=True, msg=f"Aprobada — N° {row.get('numero')} · código {codigo}", qr_url=qr_url, qr_path=qr_rel, id=row["id"], codigo=codigo, numero=row.get("numero"))
        except Exception as e:
            return jsonify(ok=False, msg=f"Error: {e}"), 500

    @admin_bp.post("/api/rechazar/<eid>")
    @security.login_required
    @security.role_required("admin")
    @security.rate_limited(20, 60)
    def rechazar(eid):
        row = database.fetch_one("SELECT id, estado FROM entradas WHERE codigo=%s OR id::text=%s", (eid, eid))
        if not row: return jsonify(ok=False, msg="Entrada no existe"), 404
        if row["estado"] != "Pendiente":
            return jsonify(ok=False, msg=f"Ya está {row['estado']}"), 400
        r = database.exec_sql("DELETE FROM entradas WHERE id=%s", (row["id"],))
        if isinstance(r, Exception):
            return jsonify(ok=False, msg=str(r)), 500
        database.log_audit("rechazar", row["id"], {"codigo": row.get("codigo")})
        database.invalidate_all_cache()
        return jsonify(ok=True, msg="Eliminada")

    @admin_bp.post("/api/desbloquear/<eid>")
    @security.login_required
    @security.role_required("admin")
    @security.rate_limited(20, 60)
    def desbloquear(eid):
        row = database.fetch_one("SELECT id, estado, ubicacion, mesa_numero FROM entradas WHERE codigo=%s OR id::text=%s", (eid, eid))
        if not row: return jsonify(ok=False, msg="Entrada no existe"), 404
        if row["estado"] == "Usada":
            return jsonify(ok=False, msg="Entrada ya usada, no se puede desbloquear"), 400
        r = database.exec_sql("DELETE FROM entradas WHERE id=%s", (row["id"],))
        if isinstance(r, Exception):
            return jsonify(ok=False, msg=str(r)), 500
        database.log_audit("desbloquear", row["id"], {"mesa": row.get("mesa_numero"), "ubicacion": row.get("ubicacion")})
        database.invalidate_all_cache()
        return jsonify(ok=True, msg=f"Mesa {row.get('mesa_numero') or ''} liberada" if row.get("ubicacion")=="Mesas" else "Entrada eliminada")

    app.register_blueprint(admin_bp)
