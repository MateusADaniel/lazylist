import os

import jwt
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

AUTH_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:5001")
TASK_URL = os.environ.get("TASK_SERVICE_URL", "http://task-service:5002")
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"

app = Flask(__name__)
CORS(app)


def proxy(base_url, path):
    url = f"{base_url}/{path}"
    upstream = requests.request(
        method=request.method,
        url=url,
        headers={k: v for k, v in request.headers if k.lower() != "host"},
        data=request.get_data(),
        params=request.args,
        timeout=10,
    )
    return Response(
        upstream.content,
        status=upstream.status_code,
        content_type=upstream.headers.get("Content-Type", "application/json"),
    )


def valid_token():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    try:
        jwt.decode(header.split(" ", 1)[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except jwt.InvalidTokenError:
        return False


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/auth/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def auth_proxy(path):
    return proxy(AUTH_URL, f"auth/{path}")


@app.route("/api/tasks", defaults={"path": ""}, methods=["GET", "POST"])
@app.route("/api/tasks/<path:path>", methods=["GET", "PUT", "DELETE"])
def task_proxy(path):
    if not valid_token():
        return jsonify({"error": "token invalido ou ausente"}), 401
    target = f"tasks/{path}" if path else "tasks"
    return proxy(TASK_URL, target)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
