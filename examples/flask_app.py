"""Example: adding sanadamaru to Flask.

    pip install flask
    SANADAMARU_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))") flask --app flask_app run

Run this file with `python examples/flask_app.py` to check how it behaves once installed (needs flask).
"""
from flask import Flask

from sanadamaru import Castle, SanadamaruWSGI, log_alert

castle = Castle.from_env(alert=log_alert)

app = Flask(__name__)


@app.get("/")
def index():
    return {"hello": "world"}


# Wrap Flask's core (wsgi_app) from the outside
app.wsgi_app = SanadamaruWSGI(app.wsgi_app, castle=castle)


if __name__ == "__main__":
    client = app.test_client()
    assert client.get("/").get_json() == {"hello": "world"}
    r = client.get("/.git/config")
    assert r.status_code == 200 and b"[remote" in r.data
    key = castle.bait_key("git", "deploy")
    assert client.get("/", headers={"X-Api-Key": key}).status_code == 403
    assert castle.report()["total"] == {"door": 1, "bait_key": 1}
    print("ok: Flask")
