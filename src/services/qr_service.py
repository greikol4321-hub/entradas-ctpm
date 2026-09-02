"""QR service — generar y servir QR — ponytail: qrcode std, sin worker"""
import pathlib
from flask import send_from_directory

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
    # guard adicional aunque routes ya sanitiza
    if ".." in fname or "/" in fname or "\\" in fname:
        return "QR no encontrado", 404
    fname = pathlib.Path(fname).name
    fpath = qr_folder / fname
    if not fpath.exists():
        code = pathlib.Path(fname).stem
        import src.core.database as database
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
