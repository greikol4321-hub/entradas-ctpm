"""Ticket service — comprar, validar, revertir, generar_codigo, QR — ponytail: 1 conexión con FOR UPDATE"""
import secrets, uuid, pathlib, hashlib

# usamos import de módulo para que monkeypatch en app propague a src (ver app.py PatchedModule)
import src.core.database as database
import src.core.storage as storage

_CODIGO_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODIGO_LEN = 5

def generar_codigo():
    return ''.join(secrets.choice(_CODIGO_ALPHABET) for _ in range(_CODIGO_LEN))

def generar_codigo_unico(max_intentos=12):
    for _ in range(max_intentos):
        c = generar_codigo()
        exists = database.fetch_one("SELECT id FROM entradas WHERE codigo=%s", (c,))
        if not exists:
            return c
    return uuid.uuid4().hex[:_CODIGO_LEN].upper().translate(str.maketrans('01IOUL','234567'))

def comprar_ticket(nombre, cedula, ubicacion, mesa_numero_raw, telefono, file_bytes, filename, upload_folder):
    # validación básica (el schema Pydantic se usa en routes)
    if ubicacion == "Mesas":
        if not mesa_numero_raw:
            return {"ok": False, "msg": "Elige el número de mesa", "code": 400}
        try:
            mesa_numero = int(mesa_numero_raw)
        except:
            return {"ok": False, "msg": "Mesa inválida", "code": 400}
        if not (1 <= mesa_numero <= database.NUM_MESAS):
            return {"ok": False, "msg": f"Mesa debe ser 1 a {database.NUM_MESAS}", "code": 400}
    else:
        mesa_numero = None
    monto = database.PRECIO_GRADAS_VAL if ubicacion == "Gradas" else database.PRECIO_MESAS_VAL
    eid = str(uuid.uuid4())
    codigo = generar_codigo_unico()
    comprobante_sha = hashlib.sha256(file_bytes).hexdigest()
    # alerta: mismo recibo ya usado en otra compra
    dup = database.fetch_one("SELECT id, nombre_completo, codigo FROM entradas WHERE comprobante_sha=%s LIMIT 1", (comprobante_sha,))
    ext = pathlib.Path(filename).suffix.lower()
    fname = f"{eid}{ext}"
    # inserción atómica con FOR UPDATE — evita TOCTOU
    conn = database.db()
    if conn is None:
        return {"ok": False, "msg": "Base de datos no disponible", "id": eid, "code": 503}
    cur = conn.cursor()
    try:
        if ubicacion == "Gradas":
            cur.execute("SELECT COUNT(*) FROM entradas WHERE ubicacion='Gradas' AND estado IN ('Pendiente','Aprobada')")
            if (cur.fetchone() or [0])[0] >= database.CAP_GRADAS:
                conn.rollback()
                cur.close(); conn.close()
                return {"ok": False, "msg": "Gradas agotadas", "code": 409}
        if ubicacion == "Mesas" and mesa_numero is not None:
            cur.execute("SELECT id FROM entradas WHERE ubicacion='Mesas' AND mesa_numero=%s AND estado IN ('Pendiente','Aprobada','Usada') FOR UPDATE", (mesa_numero,))
            if cur.fetchone():
                conn.rollback()
                cur.close(); conn.close()
                return {"ok": False, "msg": f"Mesa {mesa_numero} ya está ocupada", "code": 409}
        cur.execute("INSERT INTO entradas (id, codigo, nombre_completo, cedula, ubicacion, mesa_numero, monto, telefono, comprobante_path, comprobante_sha) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (eid, codigo, nombre, cedula, ubicacion, mesa_numero, monto, telefono, f"uploads/{fname}", comprobante_sha))
        conn.commit()
    except Exception as e:
        try: conn.rollback()
        except: pass
        cur.close(); conn.close()
        msg = str(e)
        if "uq_mesa_ocupada" in msg or "Duplicate" in msg or "unique" in msg.lower():
            return {"ok": False, "msg": f"Mesa {mesa_numero} ya fue tomada, elige otra", "code": 409}
        return {"ok": False, "msg": "Error al guardar en base de datos", "id": eid, "code": 500}
    cur2 = conn.cursor()
    cur2.execute("SELECT numero FROM entradas WHERE id=%s", (eid,))
    row_num = cur2.fetchone()
    cols = [c[0] for c in cur2.description] if cur2.description else []
    row_dict = dict(zip(cols, row_num)) if row_num else None
    numero = row_dict.get("numero") if row_dict else None
    cur2.close(); conn.close()
    # guardar archivo local y subir a supabase solo tras commit
    try:
        dest = upload_folder / fname
        dest.write_bytes(file_bytes)
    except Exception as e:
        try: database.exec_sql("DELETE FROM entradas WHERE id=%s", (eid,))
        except: pass
        return {"ok": False, "msg": "Error al guardar comprobante", "code": 500}
    try:
        ct = "image/jpeg" if ext in (".jpg",".jpeg") else "image/png" if ext==".png" else "image/webp" if ext==".webp" else "application/pdf" if ext==".pdf" else "application/octet-stream"
        storage.supabase_upload(storage.COMPROBANTES_BUCKET, fname, file_bytes, ct)
    except: pass
    database.log_audit("comprar", eid, {"numero": numero, "codigo": codigo, "ubicacion": ubicacion, "mesa": mesa_numero, "monto": monto, "comprobante_dup": bool(dup), "dup_de": dup.get("codigo") if dup else None})
    database.invalidate_all_cache()
    out = {"ok": True, "id": eid, "codigo": codigo, "numero": numero, "monto": monto, "mesa": mesa_numero}
    if dup:
        out["advertencia"] = f"Comprobante ya usado en {dup.get('codigo')} ({dup.get('nombre_completo')}) — revisar"
    return out

def validar_ticket(code_raw, raw_original):
    code = code_raw.replace(" ", "").replace("-", "").upper()
    if not code:
        return {"ok": False, "estado": "NO_EXISTE", "msg": "QR vacío", "code": 400}
    row = database.fetch_one("SELECT * FROM entradas WHERE codigo=%s OR id::text=%s", (code, raw_original))
    if not row:
        return {"ok": False, "estado": "NO_EXISTE", "msg": "Entrada no existe", "code": 404}
    if row["estado"] == "Usada":
        return {"ok": False, "estado": "USADA", "msg": "Entrada YA USADA", "row": row, "code": 200}
    if row["estado"] == "Pendiente":
        return {"ok": False, "estado": "PENDIENTE", "msg": "Entrada pendiente de aprobación", "code": 403}
    rid = row["id"]
    r = database.exec_sql("UPDATE entradas SET estado='Usada', fecha_uso=%s WHERE id=%s AND estado='Aprobada'", (database.now_cr(), rid))
    if not r.get("ok", True):
        return {"ok": False, "estado": "ERROR", "msg": r.get("error", "Error"), "code": 500}
    if r["rowcount"] == 0:
        row2 = database.fetch_one("SELECT estado FROM entradas WHERE id=%s", (rid,))
        if row2 and row2["estado"] == "Usada":
            return {"ok": False, "estado": "USADA", "msg": "Ya fue usada (carrera)", "row": row, "code": 200}
        return {"ok": False, "estado": "PENDIENTE", "msg": "Entrada pendiente de aprobación", "row": row, "code": 200}
    database.log_audit("validar", rid, {"codigo": row.get("codigo"), "numero": row.get("numero"), "resultado": "VALIDA"})
    database.invalidate_all_cache()
    return {"ok": True, "estado": "VALIDA", "msg": "¡ENTRADA VÁLIDA!", "row": row}

def revertir_ticket(codigo, motivo=""):
    code = codigo.strip().upper()
    if not motivo or not motivo.strip():
        return {"ok": False, "msg": "Motivo es requerido", "code": 400}
    row = database.fetch_one("SELECT id, estado, codigo FROM entradas WHERE codigo=%s", (code,))
    if not row:
        return {"ok": False, "msg": "Código no encontrado", "code": 404}
    if row["estado"] != "Usada":
        return {"ok": False, "msg": f"Solo se puede revertir Usada, está {row['estado']}", "code": 400}
    r = database.exec_sql("UPDATE entradas SET estado='Aprobada', fecha_uso=NULL WHERE id=%s AND estado='Usada'", (row["id"],))
    if not r.get("ok", True):
        return {"ok": False, "msg": r.get("error", str(r)), "code": 500}
    if r.get("rowcount", 1) == 0:
        return {"ok": False, "msg": "Ya fue revertida (carrera)", "code": 409}
    database.log_audit("revertir", row["id"], {"codigo": code, "motivo": motivo.strip()})
    database.invalidate_all_cache()
    return {"ok": True, "msg": f"Código {code} revertido a Aprobada"}

# QR — generar y servir (antes qr_service.py, fusionado)
def generar_qr(codigo, qr_folder):
    import qrcode
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=12, border=6)
    qr.add_data(codigo)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    qr_name = f"{codigo}.png"
    qr_path = qr_folder / qr_name
    qr_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(qr_path, "PNG")
    return qr_name, f"static/qrcodes/{qr_name}"

def serve_qr_logic(fname, qr_folder):
    from flask import send_from_directory
    # guard adicional aunque routes ya sanitiza
    if ".." in fname or "/" in fname or "\\" in fname:
        return "QR no encontrado", 404
    fname = pathlib.Path(fname).name
    fpath = qr_folder / fname
    if not fpath.exists():
        code = pathlib.Path(fname).stem
        row = database.fetch_one("SELECT id,codigo FROM entradas WHERE codigo=%s OR id::text=%s", (code, code))
        if row:
            data = (row.get("codigo") or row["id"])
            try:
                import qrcode
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=12, border=6)
                qr.add_data(data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
                fpath.parent.mkdir(parents=True, exist_ok=True)
                img.save(fpath)
            except: pass
    if fpath.exists():
        return send_from_directory(qr_folder, fname)
    return "QR no encontrado", 404
