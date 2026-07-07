import os
from flask import Flask, jsonify, request, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# ── Configuration DB via variables d'environnement ──────────────
db_user = os.environ.get("POSTGRES_USER", "app_user")
db_password = os.environ.get("POSTGRES_PASSWORD", "app_password")
db_host = os.environ.get("POSTGRES_HOST", "db")
db_port = os.environ.get("POSTGRES_PORT", "5432")
db_name = os.environ.get("POSTGRES_DB", "app_db")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ── Modèle ────────────────────────────────────────────────────
class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "done": self.done,
            "created_at": self.created_at.isoformat(),
        }

    @property
    def ref(self):
        # ID façon numéro de conteneur, ex: TSK-0007
        return f"TSK-{self.id:04d}"


# ── Pages web (HTML) ─────────────────────────────────────────
@app.route("/")
def index():
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    total = len(tasks)
    done_count = sum(1 for t in tasks if t.done)
    pending_count = total - done_count
    return render_template(
        "index.html",
        tasks=tasks,
        total=total,
        done_count=done_count,
        pending_count=pending_count,
    )


@app.route("/tasks", methods=["POST"])
def web_create_task():
    title = request.form.get("title", "").strip()
    if title:
        db.session.add(Task(title=title))
        db.session.commit()
    return redirect(url_for("index"))


@app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
def web_toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    task.done = not task.done
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def web_delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for("index"))


# ── Healthcheck ──────────────────────────────────────────────
@app.route("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ok", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "error", "database": str(e)}), 503


# ── API JSON ─────────────────────────────────────────────────
@app.route("/api/tasks", methods=["GET"])
def api_list_tasks():
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    return jsonify([t.to_dict() for t in tasks])


@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    data = request.get_json(silent=True) or {}
    title = data.get("title")
    if not title:
        return jsonify({"error": "Le champ 'title' est requis"}), 400

    task = Task(title=title)
    db.session.add(task)
    db.session.commit()
    return jsonify(task.to_dict()), 201


@app.route("/api/tasks/<int:task_id>", methods=["GET"])
def api_get_task(task_id):
    task = Task.query.get_or_404(task_id)
    return jsonify(task.to_dict())


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def api_update_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.get_json(silent=True) or {}

    if "title" in data:
        task.title = data["title"]
    if "done" in data:
        task.done = bool(data["done"])

    db.session.commit()
    return jsonify(task.to_dict())


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return "", 204


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Ressource non trouvée"}), 404
    return render_template("404.html"), 404


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", 5000))
    app.run(host="0.0.0.0", port=port)
