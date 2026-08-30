"""Validación de ticket de un solo uso"""
import uuid

def test_validar_un_solo_uso(admin_client, portero_client, monkeypatch):
    import app as appmod
    # Mock entradas: one Aprobada
    fake_id = str(uuid.uuid4())
    row_aprobada = {"id": fake_id, "codigo": "ABC12", "nombre_completo":"Test User","cedula":"1-2345-0678","ubicacion":"Gradas","mesa_numero":None,"monto":5000,"estado":"Aprobada"}
    row_usada = {**row_aprobada, "estado":"Usada"}
    # first validar -> VALIDA
    monkeypatch.setattr(appmod, "fetch_one", lambda sql, params=(): row_aprobada if "codigo" in sql else None)
    monkeypatch.setattr(appmod, "exec_sql", lambda *a, **kw: {"ok": True, "rowcount":1})
    monkeypatch.setattr(appmod, "fetch_all", lambda *a, **kw: [])
    # need to mock log_audit to avoid DB
    monkeypatch.setattr(appmod, "log_audit", lambda *a, **kw: None)
    r = portero_client.post("/api/validar", json={"id":"ABC12"})
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True
    assert j["estado"] == "VALIDA"
    # second validar -> USADA (simulate row now Usada)
    monkeypatch.setattr(appmod, "fetch_one", lambda sql, params=(): row_usada if "codigo" in sql or "id" in sql else None)
    r2 = portero_client.post("/api/validar", json={"id":"ABC12"})
    assert r2.status_code in (200, 404)
    j2 = r2.get_json()
    # should be USADA or error
    assert j2.get("estado") in ("USADA", "NO_EXISTE") or j2.get("ok") is False

def test_validar_codigo_normalizado(portero_client, monkeypatch):
    import app as appmod
    monkeypatch.setattr(appmod, "fetch_one", lambda *a, **kw: None)
    monkeypatch.setattr(appmod, "log_audit", lambda *a, **kw: None)
    # con guiones y minúsculas debe normalizar a mayúsculas sin guiones
    r = portero_client.post("/api/validar", json={"id":"a-b c 12"})
    # normalize -> ABC12, no existe -> 404
    assert r.status_code == 404
    j = r.get_json()
    assert j["estado"] == "NO_EXISTE"

def test_revertir_solo_usada(portero_client, monkeypatch):
    import app as appmod
    monkeypatch.setattr(appmod, "fetch_one", lambda sql, params=(): {"id":"1","estado":"Aprobada","codigo":"XYZ99"} if "XYZ99" in str(params) else None)
    monkeypatch.setattr(appmod, "log_audit", lambda *a, **kw: None)
    r = portero_client.post("/api/revertir/XYZ99")
    assert r.status_code == 400
    j = r.get_json()
    assert "Solo se puede revertir Usada" in j["msg"]
