import logging
import os
import time
from functools import wraps

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

import jwt
from flask import Flask, request, jsonify

from models import db, Task

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"


def build_db_uri():
    return (
        f"mysql+pymysql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '3306')}"
        f"/{os.environ['DB_NAME']}"
    )


MIGRATIONS = [
    ("priority",  "VARCHAR(10) NOT NULL DEFAULT 'media'"),
    ("done",      "TINYINT(1) NOT NULL DEFAULT 0"),
    ("category",  "VARCHAR(100) NULL"),
]


def run_migrations(app):
    with app.app_context():
        conn = db.engine.connect()
        for col_name, col_def in MIGRATIONS:
            result = conn.execute(
                db.text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = 'tasks' "
                    "AND COLUMN_NAME = :col"
                ),
                {"col": col_name},
            )
            if result.scalar() == 0:
                conn.execute(db.text(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def}"))
                conn.commit()
                logging.info(f"migration: added column '{col_name}'")
        conn.close()


def init_db(app, retries=10, delay=3):
    with app.app_context():
        for attempt in range(retries):
            try:
                db.create_all()
                run_migrations(app)
                return
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(delay)


def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "token ausente"}), 401
        try:
            payload = jwt.decode(header.split(" ", 1)[1], JWT_SECRET,
                                 algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "token expirado"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "token invalido"}), 401
        request.user_id = int(payload["sub"])
        request.user_role = payload["role"]
        return f(*args, **kwargs)
    return wrapper


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = build_db_uri()
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "ssl": {
            "fake_flag_to_force_disable": True  # Force bypass if driver tries to enforce TLS
         }
        }
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    init_db(app)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    from datetime import date

    def parse_due_date(value):
        if not value:
            return None, None
        try:
            return date.fromisoformat(value), None
        except ValueError:
            return None, "due_date invalida (use YYYY-MM-DD)"
    #
    # STRIDE Information Disclosure: controle de acesso por dono
    def get_accessible_task(task_id):
        task = Task.query.get(task_id)
        if not task:
            return None, (jsonify({"error": "tarefa nao encontrada"}), 404)
        if request.user_role != "admin" and task.user_id != request.user_id:
            return None, (jsonify({"error": "acesso negado"}), 403)
        return task, None

    VALID_PRIORITIES = {"baixa", "media", "alta"}

    @app.post("/tasks")                  # RF04
    @token_required
    def create_task():
        data = request.get_json(silent=True) or {}
        if not data.get("title"):
            return jsonify({"error": "title obrigatorio"}), 400
        due, err = parse_due_date(data.get("due_date"))
        if err:
            return jsonify({"error": err}), 400
        priority = data.get("priority", "media")
        if priority not in VALID_PRIORITIES:
            return jsonify({"error": "priority deve ser baixa, media ou alta"}), 400
        task = Task(
            user_id=request.user_id,
            title=data["title"],
            description=data.get("description", ""),
            due_date=due,
            priority=priority,
            done=bool(data.get("done", False)),
            category=data.get("category"),
        )
        db.session.add(task)
        db.session.commit()
        app.logger.info(f"task_create user_id={request.user_id} task_id={task.id}")
        return jsonify(task.to_dict()), 201

    @app.get("/tasks")                   # RF05 + RF08
    @token_required
    def list_tasks():
        from sqlalchemy import case, or_
        query = Task.query
        if request.user_role != "admin":
            query = query.filter_by(user_id=request.user_id)

        # Legacy single-date filter (mantido para compatibilidade)
        date_filter = request.args.get("date")
        if date_filter:
            due, err = parse_due_date(date_filter)
            if err:
                return jsonify({"error": err}), 400
            query = query.filter_by(due_date=due)

        # Filtro por status
        status = request.args.get("status")
        if status == "pendentes":
            query = query.filter_by(done=False)
        elif status == "concluidas":
            query = query.filter_by(done=True)

        # Filtro por prioridade
        prio = request.args.get("priority")
        if prio in VALID_PRIORITIES:
            query = query.filter_by(priority=prio)

        # Intervalo de datas
        date_from = request.args.get("date_from")
        date_to   = request.args.get("date_to")
        if date_from:
            d, err = parse_due_date(date_from)
            if err:
                return jsonify({"error": err}), 400
            query = query.filter(Task.due_date >= d)
        if date_to:
            d, err = parse_due_date(date_to)
            if err:
                return jsonify({"error": err}), 400
            query = query.filter(Task.due_date <= d)

        # Busca textual
        search = request.args.get("search", "").strip()
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(Task.title.ilike(pattern), Task.description.ilike(pattern))
            )

        # Ordenação
        sort = request.args.get("sort", "due_date")
        if sort == "priority":
            priority_order = case(
                (Task.priority == "alta",  1),
                (Task.priority == "media", 2),
                (Task.priority == "baixa", 3),
                else_=4,
            )
            query = query.order_by(priority_order)
        elif sort == "created_at":
            query = query.order_by(Task.created_at.desc())
        else:
            query = query.order_by(Task.due_date)

        return jsonify([t.to_dict() for t in query.all()])

    @app.get("/tasks/<int:task_id>")     # RF09
    @token_required
    def get_task(task_id):
        task, error = get_accessible_task(task_id)
        if error:
            return error
        return jsonify(task.to_dict())

    @app.put("/tasks/<int:task_id>")     # RF06
    @token_required
    def update_task(task_id):
        task, error = get_accessible_task(task_id)
        if error:
            return error
        data = request.get_json(silent=True) or {}
        if "title" in data:
            task.title = data["title"]
        if "description" in data:
            task.description = data["description"]
        if "due_date" in data:
            due, err = parse_due_date(data["due_date"])
            if err:
                return jsonify({"error": err}), 400
            task.due_date = due
        if "priority" in data:
            if data["priority"] not in VALID_PRIORITIES:
                return jsonify({"error": "priority deve ser baixa, media ou alta"}), 400
            task.priority = data["priority"]
        if "done" in data:
            task.done = bool(data["done"])
        if "category" in data:
            task.category = data["category"]
        db.session.commit()
        return jsonify(task.to_dict())

    @app.patch("/tasks/<int:task_id>/done")
    @token_required
    def toggle_done(task_id):
        task, error = get_accessible_task(task_id)
        if error:
            return error
        task.done = not task.done
        db.session.commit()
        return jsonify(task.to_dict())

    @app.delete("/tasks/<int:task_id>")  # RF07
    @token_required
    def delete_task(task_id):
        task, error = get_accessible_task(task_id)
        if error:
            return error
        db.session.delete(task)
        db.session.commit()
        app.logger.info(f"task_delete user_id={request.user_id} task_id={task_id}")
        return jsonify({"message": "tarefa removida"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
