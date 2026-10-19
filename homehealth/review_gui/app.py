"""Loopback-only Flask application for reviewing synthetic corpus conversions."""

from pathlib import Path

from flask import Flask, abort, redirect, render_template, url_for

from homehealth.aether_review.trigger_adapter import review_request_from_trigger_input

from .queue import QueueCase, load_queue
from .store import ReviewStore


def create_app(queue_path: Path | str, db_path: Path | str, params_path: Path | str) -> Flask:
    app = Flask(__name__)
    app.config.update(REVIEW_HOST="127.0.0.1", REVIEW_PORT=5000)
    queue = load_queue(queue_path)
    cases = {case.case_id: case for case in queue}
    store = ReviewStore(db_path)
    for case in queue:
        store.ensure_case(case.case_id)

    @app.get("/")
    def index():
        if not queue:
            return render_template("empty.html")
        return redirect(url_for("case_detail", case_id=queue[0].case_id))

    @app.get("/cases/<case_id>")
    def case_detail(case_id: str):
        case = cases.get(case_id)
        if case is None:
            abort(404)
        request = review_request_from_trigger_input(case.input, params_path)
        computed = {"tier": request.engine_tier, "rule": request.engine_reasons[-1] if len(request.engine_reasons) > 1 else ""}
        return render_template(
            "case.html",
            case=case,
            case_count=len(queue),
            computed=computed,
            status=store.status_for(case.case_id),
        )

    return app


def run_local() -> None:
    root = Path(__file__).resolve().parents[1]
    app = create_app(
        Path(__file__).with_name("fixtures") / "queue.json",
        Path.home() / ".homehealth-review" / "review.sqlite3",
        root / "trigger_engine" / "trigger_params.json",
    )
    app.run(host=app.config["REVIEW_HOST"], port=app.config["REVIEW_PORT"])
