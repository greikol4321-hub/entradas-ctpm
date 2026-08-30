"""Supabase Storage — extraído de app.py — ponytail: urllib stdlib, sin boto3/supabase-py"""
import os

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://jyfmimxzhpvcezwilkdd.supabase.co")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SERVICE_ROLE_KEY")
COMPROBANTES_BUCKET = "comprobantes"

def _supabase_headers(ct="application/octet-stream"):
    if not SUPABASE_SERVICE_KEY:
        return {}
    return {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": ct}

def supabase_upload(bucket, fname, data_bytes, content_type="application/octet-stream"):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return False
    try:
        import urllib.request, urllib.error
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{fname}"
        req = urllib.request.Request(url, data=data_bytes, method="POST", headers=_supabase_headers(content_type))
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 201)
        except urllib.error.HTTPError as e:
            if e.code in (409, 400):
                req2 = urllib.request.Request(url, data=data_bytes, method="PUT", headers=_supabase_headers(content_type))
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    return resp2.status in (200, 201)
            return False
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.warning(f"[storage] upload {bucket}/{fname} err: {e}")
        except: pass
        return False

def supabase_delete(bucket, fname):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return False
    try:
        import urllib.request
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{fname}"
        req = urllib.request.Request(url, method="DELETE", headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.warning(f"[storage] delete {bucket}/{fname} warn: {e}")
        except: pass
        return False

def supabase_download(bucket, fname):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    try:
        import urllib.request
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{fname}"
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read(), resp.headers.get_content_type() or "application/octet-stream"
    except Exception:
        return None
