"""Flask に真田丸を入れる例。

    pip install flask
    SANADAMARU_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))") flask --app flask_app run

このファイルを `python examples/flask_app.py` で動かすと、入れた後の動きを確かめます（要 flask）。
"""
from flask import Flask

from sanadamaru import Castle, SanadamaruWSGI, log_alert

castle = Castle.from_env(alert=log_alert)

app = Flask(__name__)


@app.get("/")
def index():
    return {"hello": "world"}


# Flask の本体（wsgi_app）を、外側から包みます
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
