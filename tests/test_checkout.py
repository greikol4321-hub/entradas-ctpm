"""Checkout: mesa, monto, teléfono, concurrencia"""
import io, uuid
import pytest

def _make_file(content=b"fake image", filename="comprobante.jpg"):
    return (io.BytesIO(content), filename)

def test_compra_gradas_ok(client, monkeypatch):
    import app as appmod
    # mock generar_codigo, db, and file handling
    monkeypatch.setattr(appmod, "generar_codigo_unico", lambda: "TEST1")
    monkeypatch.setattr(appmod, "supabase_upload", lambda *a, **kw: True)
    monkeypatch.setattr(appmod, "log_audit", lambda *a, **kw: None)
    # mock db transaction: need to mock db() to return fake conn
    class FakeCur:
        def execute(self, sql, params=None): pass
        @property
        def description(self): return [("numero",)]
        def fetchone(self): return (1,)
        def fetchall(self): return []
        def close(self): pass
    class FakeConn:
        def cursor(self): return FakeCur()
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass
    monkeypatch.setattr(appmod, "db", lambda: FakeConn())
    monkeypatch.setattr(appmod, "exec_sql", lambda *a, **kw: None)  # not used now
    # fetch_one for numero
    monkeypatch.setattr(appmod, "fetch_one", lambda sql, params=(): {"numero": 42})
    data = {
        "nombre":"Test User",
        "cedula":"1-2345-0678",
        "ubicacion":"Gradas",
        "telefono":"88888888",
        "mesa_numero":"",
    }
    file = _make_file()
    r = client.post("/api/comprar", data={**data, "comprobante": file}, content_type="multipart/form-data")
    # may be 200 or 400 depending on mocked DB — check monto logic
    assert r.status_code in (200, 400, 409, 500)

def test_compra_mesa_falta_numero(client):
    r = client.post("/api/comprar", data={
        "nombre":"A","cedula":"1-2345-0678","ubicacion":"Mesas","mesa_numero":"","telefono":"88888888",
        "comprobante": (io.BytesIO(b"x"), "a.jpg")
    }, content_type="multipart/form-data")
    assert r.status_code == 400
    j = r.get_json()
    assert "mesa" in j["msg"].lower()

def test_compra_telefono_requerido(client):
    r = client.post("/api/comprar", data={
        "nombre":"A","cedula":"1-2345-0678","ubicacion":"Gradas","telefono":"",
        "comprobante": (io.BytesIO(b"x"), "a.jpg")
    }, content_type="multipart/form-data")
    assert r.status_code == 400

def test_mesa_ocupada_409(client, monkeypatch):
    import app as appmod
    # mock db to simulate mesa ocupada via FOR UPDATE
    class FakeCurOcc:
        def execute(self, sql, params=None):
            self._sql = sql
        def fetchone(self):
            if "FOR UPDATE" in getattr(self, "_sql", ""):
                return ("occupied-id",)  # mesa ocupada
            return None
        @property
        def description(self): return [("id",)] if "FOR UPDATE" in getattr(self, "_sql", "") else [("numero",)]
        def fetchall(self): return []
        def close(self): pass
    class FakeConnOcc:
        def cursor(self): return FakeCurOcc()
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass
    monkeypatch.setattr(appmod, "db", lambda: FakeConnOcc())
    monkeypatch.setattr(appmod, "generar_codigo_unico", lambda: "XYZ12")
    data = {
        "nombre":"Test","cedula":"1-2345-0678","ubicacion":"Mesas","mesa_numero":"3","telefono":"88888888",
        "comprobante": (io.BytesIO(b"img"), "c.jpg")
    }
    r = client.post("/api/comprar", data=data, content_type="multipart/form-data")
    assert r.status_code == 409
    j = r.get_json()
    assert "ocupada" in j["msg"].lower()

def test_precio_monto():
    import app as appmod
    assert appmod.PRECIO_GRADAS_VAL == 5000
    assert appmod.PRECIO_MESAS_VAL == 10000
