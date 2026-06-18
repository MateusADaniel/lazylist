import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, RevokedToken

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_EXP_MINUTES = int(os.environ.get("JWT_EXP_MINUTES", "60"))


def encode_token(user):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXP_MINUTES),
    }
    #
    # STRIDE Spoofing/Tampering: token assinado com chave secreta (HS256), impede forjar ou alterar o payload
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "token ausente"}), 401
        token = header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "token expirado"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "token invalido"}), 401
        if RevokedToken.query.filter_by(jti=payload["jti"]).first():
            return jsonify({"error": "token revogado"}), 401
        request.user_id = int(payload["sub"])
        request.user_role = payload["role"]
        request.token_jti = payload["jti"]
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    @token_required
    def wrapper(*args, **kwargs):
        #
        # STRIDE Elevation of Privilege: só admin passa; cliente recebe 403
        if request.user_role != "admin":
            return jsonify({"error": "acesso negado"}), 403
        return f(*args, **kwargs)
    return wrapper


def seed_admin(app):
    """Cria um admin inicial a partir de variáveis de ambiente, se não existir."""
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if not email or not password:
        return
    with app.app_context():
        if not User.query.filter_by(email=email).first():
            db.session.add(User(
                username="admin",
                email=email,
                password_hash=generate_password_hash(password),
                role="admin",
            ))
            db.session.commit()


def build_db_uri():
    return (
        f"mysql+pymysql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '3306')}"
        f"/{os.environ['DB_NAME']}"
    )


def init_db(app, retries=10, delay=3):
    """Tenta criar as tabelas, aguardando o MySQL ficar pronto."""
    with app.app_context():
        for attempt in range(retries):
            try:
                db.create_all()
                return
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(delay)


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = build_db_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "ssl": {
            "fake_flag_to_force_disable": True  # Force bypass if driver tries to enforce TLS
         }
        }
    }
    db.init_app(app)
    init_db(app)
    seed_admin(app)

    # 
    # STRIDE Denial of Service: limite global de requisições por IP
    limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/auth/register")          # RF01
    #
    # STRIDE Denial of Service: limita criação de contas em massa
    @limiter.limit("10 per minute")
    def register():
        data = request.get_json(silent=True) or {}
        for field in ("username", "email", "password"):
            if not data.get(field):
                return jsonify({"error": f"campo {field} obrigatorio"}), 400
        if User.query.filter_by(email=data["email"]).first():
            return jsonify({"error": "email ja cadastrado"}), 409
        user = User(
            username=data["username"],
            email=data["email"],
            #
            # STRIDE Information Disclosure: senha nunca salva em texto puro, apenas o hash
            password_hash=generate_password_hash(data["password"]),  
            #
            # STRIDE Elevation of Privilege: cadastro público sempre cria cliente, nunca admin
            role="cliente",
        )
        db.session.add(user)
        db.session.commit()
        #
        # STRIDE Repudiation: registra o cadastro para trilha de auditoria
        app.logger.info(f"register user_id={user.id} email={user.email}")
        return jsonify({"id": user.id, "username": user.username}), 201

    @app.post("/auth/login")             # RF02
    #
    # STRIDE Denial of Service: limita tentativas de login (anti força-bruta de senha)
    @limiter.limit("5 per minute")
    def login():
        data = request.get_json(silent=True) or {}
        user = User.query.filter_by(email=data.get("email")).first()
        #
        # STRIDE Information Disclosure: compara hash sem expor a senha; erro genérico não revela se o email existe
        if not user or not check_password_hash(user.password_hash, data.get("password", "")):
            return jsonify({"error": "credenciais invalidas"}), 401
        #
        # STRIDE Repudiation: registra o login para trilha de auditoria
        app.logger.info(f"login user_id={user.id}")
        return jsonify({"access_token": encode_token(user)})

    @app.post("/auth/logout")            # RF03
    @token_required
    def logout():
        db.session.add(RevokedToken(jti=request.token_jti))
        db.session.commit()
        return jsonify({"message": "logout realizado"})

    @app.get("/auth/users")              # RF10
    @admin_required
    def list_users():
        return jsonify([u.to_dict() for u in User.query.all()])

    @app.delete("/auth/users/<int:user_id>")   # RF10
    @admin_required
    def delete_user(user_id):
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "usuario nao encontrado"}), 404
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "usuario removido"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
