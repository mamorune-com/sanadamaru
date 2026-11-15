"""Example: adding sanadamaru to FastAPI.

    pip install fastapi uvicorn
    SANADAMARU_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))") ADMIN_KEY=... uvicorn fastapi_app:app

Run this file with `python examples/fastapi_app.py` to check how it behaves once installed (needs fastapi and httpx).
"""
import hmac
import os

from fastapi import FastAPI, Header, HTTPException

from sanadamaru import Castle, SanadamaruMiddleware, log_alert

# Endpoints that must keep working even while blocking is on (health checks, emergency endpoints) go in never_block
castle = Castle.from_env(never_block=("/health", "/api/sos"), alert=log_alert)

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def index():
    return {"hello": "world"}


@app.get("/admin/sanadamaru")
def sanadamaru_report(x_admin_key: str = Header(default="")):
    """The records. They contain full source addresses, so they sit behind an admin key (closed if no key is set)."""
    expected = os.environ.get("ADMIN_KEY", "")
    if not expected or not hmac.compare_digest(x_admin_key.encode(), expected.encode()):
        raise HTTPException(status_code=403)
    return castle.report()


# Added after (last) all other middleware so that it is the outermost layer
app.add_middleware(SanadamaruMiddleware, castle=castle)


if __name__ == "__main__":
    from fastapi.testclient import TestClient

    os.environ.setdefault("ADMIN_KEY", "example-admin-key-for-the-self-check")
    client = TestClient(app)
    assert client.get("/").json() == {"hello": "world"}
    r = client.get("/.env")
    assert r.status_code == 200 and "DB_PASSWORD=" in r.text
    key = castle.bait_key("env", "db")
    assert client.get("/", headers={"Authorization": f"Bearer {key}"}).status_code == 403
    assert client.get("/admin/sanadamaru").status_code == 403
    report = client.get("/admin/sanadamaru", headers={"X-Admin-Key": os.environ["ADMIN_KEY"]}).json()
    assert report["total"] == {"door": 1, "bait_key": 1}, report["total"]
    print("ok: FastAPI")
