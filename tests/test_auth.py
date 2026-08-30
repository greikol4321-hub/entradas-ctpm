"""RBAC: portero no puede ver finanzas ni crear usuarios"""
def test_portero_no_finanzas(portero_client):
    r = portero_client.get("/api/finanzas")
    assert r.status_code in (403, 401)

def test_portero_no_usuarios(portero_client):
    r = portero_client.get("/api/usuarios")
    assert r.status_code in (403, 401)

def test_portero_no_crear_usuario(portero_client):
    r = portero_client.post("/api/usuarios", json={"username":"x","password":"y","rol":"admin"})
    assert r.status_code in (403, 401)

def test_admin_si_finanzas(admin_client, monkeypatch):
    # mock DB for finanzas to avoid real Supabase
    import app as appmod
    monkeypatch.setattr(appmod, "fetch_all", lambda *a, **kw: [])
    # finanzas does 4 fetch_all in one connection helper — mock _load_finanzas_payload
    monkeypatch.setattr(appmod, "_load_finanzas_payload", lambda: {"ok": True, "agrupado": [], "kpi": {"total_entradas":0,"recaudado":0,"por_confirmar":0,"usadas":0,"aprobadas":0,"pendientes":0}, "por_zona": [], "mesas": {"ocupadas":0,"libres":12,"total":12}})
    r = admin_client.get("/api/finanzas")
    # may be 200 with mocked payload or 304 if cached — accept both
    assert r.status_code in (200, 304)

def test_unauth_redirect(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code in (302, 401)
    # api should be 401 json
    r2 = client.get("/api/entradas")
    assert r2.status_code == 401
