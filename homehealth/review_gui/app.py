"""Loopback-only Flask application for reviewing synthetic corpus conversions."""

from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

from homehealth.aether_review.trigger_adapter import review_request_from_trigger_input

from .queue import QueueCase, load_queue
from .store import ReviewStore


def create_app(queue_path: Path | str, db_path: Path | str, params_path: Path | str) -> Flask:
    app = Flask(__name__)
    app.config.update(REVIEW_HOST="127.0.0.1", REVIEW_PORT=5000)
    queue = load_queue(queue_path)
    cases = {case.case_id: case for case in queue}
    app.config["CASES"] = cases
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
        computed = _computed_result(case, params_path)
        return render_template(
            "case.html",
            case=case,
            case_count=len(queue),
            computed=computed,
            status=store.status_for(case.case_id),
            audit_events=store.audit_for(case.case_id),
        )

    @app.post("/cases/<case_id>/agree")
    def agree(case_id: str):
        case = cases.get(case_id)
        if case is None:
            abort(404)
        reviewer = request.form.get("reviewer", "").strip()
        checks = ("check_synthetic", "check_source", "check_ruling", "check_expected", "check_recomputed")
        if not reviewer or any(request.form.get(check) != "on" for check in checks):
            abort(400, "reviewer and all five conversion checks are required")
        computed = _computed_result(case, params_path)
        if computed != case.expected:
            abort(400, "recomputed engine result does not match the preconfigured expectation")
        store.set_status(case_id, "approved")
        store.audit(case_id, reviewer, "approved_conversion", {"checks": list(checks), "computed": computed, "expected": case.expected})
        return redirect(url_for("case_detail", case_id=case_id))

    return app


def _computed_result(case: QueueCase, params_path: Path | str) -> dict:
    review_request = review_request_from_trigger_input(case.input, params_path)
    return {"tier": review_request.engine_tier, "rule": review_request.engine_reasons[-1] if len(review_request.engine_reasons) > 1 else ""}


def run_local() -> None:
    root = Path(__file__).resolve().parents[1]
    app = create_app(
        Path(__file__).with_name("fixtures") / "queue.json",
        Path.home() / ".homehealth-review" / "review.sqlite3",
        root / "trigger_engine" / "trigger_params.json",
    )
    app.run(host=app.config["REVIEW_HOST"], port=app.config["REVIEW_PORT"])
