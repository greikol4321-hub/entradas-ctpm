"""Scanner routes — /scanner, /api/validar, /api/historial, /api/revertir"""
from flask import Blueprint, request, jsonify, render_template, session
import src.core.database as database
import src.core.security as security

scanner_bp = Blueprint("scanner", __name__)

def init_scanner(app):
    @scanner_bp.get("/scanner")
    @security.login_required
    @security.role_required("portero")
    def scanner():
        return render_template("scanner.html")

    @scanner_bp.post("/api/validar")
    @security.login_required
    @security.role_required("portero")
    @security.rate_limited(30, 60)
    def validar():
        data = request.get_json(silent=True) or {}
        raw = (data.get("id") or data.get("codigo") or request.form.get("id") or request.form.get("codigo") or "").strip()
        code = raw.replace(" ", "").replace("-", "").upper()
        if not code: return jsonify(ok=False, estado="NO_EXISTE", msg="QR vacío"), 400
        try:
            import src.services.ticket_service as ticket_service
            result = ticket_service.validar_ticket(code, raw)
            if not result["ok"]:
                # mapear a respuesta HTTP como en monolito
                row = result.get("row")
                if result["estado"] == "USADA":
                    return jsonify(ok=False, estado="USADA", msg="Entrada YA USADA", nombre=row["nombre_completo"] if row else None, ubicacion=row["ubicacion"] if row else None, mesa_numero=row.get("mesa_numero") if row else None, monto=row.get("monto") if row else None, codigo=row.get("codigo") if row else None, numero=row.get("numero") if row else None), 200
                if result["estado"] == "PENDIENTE":
                    return jsonify(ok=False, estado="PENDIENTE", msg="Entrada pendiente de aprobación"), 403
                if result["estado"] == "NO_EXISTE":
                    return jsonify(ok=False, estado="NO_EXISTE", msg="Entrada no existe"), 404
                return jsonify(ok=False, estado=result["estado"], msg=result["msg"]), result.get("code", 500)
            row = result["row"]
            return jsonify(ok=True, estado="VALIDA", msg="¡ENTRADA VÁLIDA!", nombre=row["nombre_completo"], ubicacion=row["ubicacion"], cedula=row["cedula"], mesa_numero=row.get("mesa_numero"), monto=row.get("monto"), codigo=row.get("codigo"), numero=row.get("numero"))
        except Exception as e:
            return jsonify(ok=False, estado="ERROR", msg=f"Error: {e}"), 500

    @scanner_bp.get("/api/historial")
    @security.login_required
    @security.role_required("portero")
    def historial():
        if session.get("rol") not in ("portero",):
            return jsonify(ok=False, msg="No autorizado"), 403
        rows = database.fetch_all("SELECT id, codigo, nombre_completo, cedula, ubicacion, mesa_numero, fecha_uso FROM entradas WHERE estado='Usada' ORDER BY fecha_uso DESC LIMIT 20")
        for r in rows:
            if r.get("fecha_uso") and hasattr(r["fecha_uso"], "strftime"):
                from datetime import datetime
                if isinstance(r["fecha_uso"], datetime):
                    r["fecha_uso"] = database.to_cr_str(r["fecha_uso"])
        return jsonify(rows)

    @scanner_bp.post("/api/revertir/<codigo>")
    @security.login_required
    @security.role_required("portero")
    def revertir(codigo):
        if session.get("rol") not in ("portero",):
            return jsonify(ok=False, msg="No autorizado"), 403
        import src.services.ticket_service as ticket_service
        r = ticket_service.revertir_ticket(codigo)
        if not r["ok"]:
            return jsonify(ok=False, msg=r["msg"]), r["code"]
        return jsonify(ok=True, msg=r["msg"])

    app.register_blueprint(scanner_bp)
