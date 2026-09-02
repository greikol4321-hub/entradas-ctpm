"""User service — ensure_admin, CRUD — ponytail: sin ORM"""
from werkzeug.security import generate_password_hash
import src.core.database as database

def ensure_admin_user(DEMO_USER, DEMO_PASS, app_logger=None):
    if not DEMO_USER or not DEMO_PASS:
        if app_logger:
            app_logger.info("[CTPM] ensure_admin_user omitido: INITIAL_ADMIN_USER/PASSWORD no configurados")
        return
    try:
        cnt = database.fetch_one("SELECT COUNT(*) as c FROM usuarios WHERE rol='admin'")
        if cnt and cnt["c"] > 0:
            return
        u = database.fetch_one("SELECT id FROM usuarios WHERE username=%s LIMIT 1", (DEMO_USER,))
        if not u:
            h = generate_password_hash(DEMO_PASS)
            r = database.exec_sql("INSERT INTO usuarios (username, password_hash, rol) VALUES (%s,%s,%s)", (DEMO_USER, h, "admin"))
            if not r.get("ok", True):
                if app_logger: app_logger.error(f"[CTPM] ensure_admin_user error: {r.get('error', str(r))}")
            elif r.get("ok") and app_logger:
                app_logger.info(f"[CTPM] Usuario admin creado: {DEMO_USER} (password oculto)")
    except Exception as e:
        if app_logger:
            app_logger.warning(f"[CTPM] ensure_admin_user omitido: {e}")

def list_users():
    rows = database.fetch_all("SELECT id, username, rol, created_at FROM public.usuarios ORDER BY username")
    for r in rows:
        if r.get("created_at") and hasattr(r["created_at"], "strftime"):
            from datetime import datetime
            if isinstance(r["created_at"], datetime):
                r["created_at"] = database.to_cr_str(r["created_at"])
    return rows

def create_user(username, password, rol):
    if rol not in ("admin","portero"):
        return {"ok": False, "msg": "Rol inválido", "code": 400}
    if len(username) < 3 or len(password) < 4:
        return {"ok": False, "msg": "Usuario mínimo 3, contraseña mínimo 4", "code": 400}
    if database.fetch_one("SELECT id FROM public.usuarios WHERE username=%s", (username,)):
        return {"ok": False, "msg": "Usuario ya existe", "code": 409}
    h = generate_password_hash(password)
    r = database.exec_sql("INSERT INTO public.usuarios (username, password_hash, rol) VALUES (%s,%s,%s)", (username, h, rol))
    if not r.get("ok", True):
        return {"ok": False, "msg": r.get("error", str(r)), "code": 500}
    database.log_audit("crear_usuario", None, {"user": username, "rol": rol})
    return {"ok": True, "msg": "Usuario creado"}

def update_user(uid, username, password, rol):
    row = database.fetch_one("SELECT id, username FROM public.usuarios WHERE id=%s", (uid,))
    if not row:
        return {"ok": False, "msg": "Usuario no existe", "code": 404}
    if username and username != row["username"] and database.fetch_one("SELECT id FROM public.usuarios WHERE username=%s AND id!=%s", (username, uid)):
        return {"ok": False, "msg": "Nombre ya en uso", "code": 409}
    set_clauses = []
    params = []
    if username:
        if len(username) < 3:
            return {"ok": False, "msg": "Usuario mínimo 3", "code": 400}
        set_clauses.append("username = %s"); params.append(username)
    if rol:
        if rol not in ("admin","portero"):
            return {"ok": False, "msg": "Rol inválido", "code": 400}
        set_clauses.append("rol = %s"); params.append(rol)
    if password:
        if len(password) < 4:
            return {"ok": False, "msg": "Contraseña mínimo 4", "code": 400}
        set_clauses.append("password_hash = %s"); params.append(generate_password_hash(password))
    if not set_clauses:
        return {"ok": False, "msg": "Nada que actualizar", "code": 400}
    params.append(uid)
    sql = "UPDATE public.usuarios SET " + ", ".join(set_clauses) + " WHERE id=%s"
    r = database.exec_sql(sql, tuple(params))
    if not r.get("ok", True):
        return {"ok": False, "msg": r.get("error", str(r)), "code": 500}
    database.log_audit("editar_usuario", None, {"id": uid, "user": username or row["username"]})
    return {"ok": True, "msg": "Usuario actualizado"}

def delete_user(uid, current_uid, current_username):
    row = database.fetch_one("SELECT id, username FROM public.usuarios WHERE id=%s", (uid,))
    if not row:
        return {"ok": False, "msg": "Usuario no existe", "code": 404}
    if str(current_uid) == str(uid) or current_username == row["username"]:
        return {"ok": False, "msg": "No puedes borrar tu propio usuario", "code": 400}
    cnt = database.fetch_one("SELECT COUNT(*) as c FROM public.usuarios WHERE rol='admin'")
    is_admin = database.fetch_one("SELECT rol FROM public.usuarios WHERE id=%s", (uid,))
    if is_admin and is_admin["rol"] == "admin" and cnt and cnt["c"] <= 1:
        return {"ok": False, "msg": "Debe quedar al menos un admin", "code": 400}
    r = database.exec_sql("DELETE FROM public.usuarios WHERE id=%s", (uid,))
    if not r.get("ok", True):
        return {"ok": False, "msg": r.get("error", str(r)), "code": 500}
    database.log_audit("borrar_usuario", None, {"id": uid, "user": row["username"]})
    return {"ok": True, "msg": "Usuario eliminado"}
