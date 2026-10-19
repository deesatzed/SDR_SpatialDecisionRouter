"""Loopback-only Flask application for reviewing synthetic corpus conversions."""

import copy
import math
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

from homehealth.aether_review.trigger_adapter import review_request_from_trigger_input
from homehealth.jev_baseline.phi_guard import phi_hits

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
        payload = _payload_with_draft(case, store.draft_for(case.case_id))
        computed = _computed_result(case, params_path, payload)
        return render_template(
            "case.html",
            case=case,
            case_count=len(queue),
            case_position=queue.index(case) + 1,
            computed=computed,
            status=store.status_for(case.case_id),
            audit_events=store.audit_for(case.case_id),
            payload=payload,
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
        computed = _computed_result(case, params_path, _payload_with_draft(case, store.draft_for(case_id)))
        if computed != case.expected:
            abort(400, "recomputed engine result does not match the preconfigured expectation")
        store.set_status(case_id, "approved")
        store.audit(case_id, reviewer, "approved_conversion", {"checks": list(checks), "computed": computed, "expected": case.expected})
        return redirect(url_for("case_detail", case_id=case_id))

    @app.post("/cases/<case_id>/edit")
    def edit(case_id: str):
        case = cases.get(case_id)
        if case is None:
            abort(404)
        reviewer = request.form.get("reviewer", "").strip()
        if not reviewer:
            abort(400, "reviewer is required")
        try:
            draft = {
                "reading_value": _finite_number(request.form.get("reading_value")),
                "fingerstick_value": _finite_number(request.form.get("fingerstick_value")),
            }
        except ValueError as error:
            abort(400, str(error))
        store.set_draft(case_id, draft)
        store.set_status(case_id, "edited")
        store.audit(case_id, reviewer, "edited_conversion", {"changed_fields": list(draft)})
        return redirect(url_for("case_detail", case_id=case_id))

    @app.post("/cases/<case_id>/disposition")
    def disposition(case_id: str):
        if case_id not in cases:
            abort(404)
        reviewer = request.form.get("reviewer", "").strip()
        action = request.form.get("action", "")
        note = request.form.get("note", "").strip()
        allowed = {"needs_clinician_review", "excluded"}
        if not reviewer or action not in allowed or not note:
            abort(400, "reviewer, supported disposition, and reason are required")
        if phi_hits(note):
            abort(400, "reason contains PHI-like input")
        store.set_status(case_id, action)
        store.audit(case_id, reviewer, action, {"reason": note})
        return redirect(url_for("case_detail", case_id=case_id))

    return app


def _computed_result(case: QueueCase, params_path: Path | str, payload: dict | None = None) -> dict:
    review_request = review_request_from_trigger_input(payload or case.input, params_path)
    return {"tier": review_request.engine_tier, "rule": review_request.engine_reasons[-1] if len(review_request.engine_reasons) > 1 else ""}


def _payload_with_draft(case: QueueCase, draft: dict) -> dict:
    payload = copy.deepcopy(case.input)
    if not draft:
        return payload
    payload["reading"]["value"] = draft["reading_value"]
    fingerstick = payload["reading"].get("cgm", {}).get("fingerstick")
    if fingerstick is not None:
        fingerstick["value"] = draft["fingerstick_value"]
    return payload


def _finite_number(value: str | None) -> float:
    try:
        result = float(value or "")
    except ValueError as error:
        raise ValueError("edited values must be finite numbers") from error
    if not math.isfinite(result):
        raise ValueError("edited values must be finite numbers")
    return result


def run_local() -> None:
    root = Path(__file__).resolve().parents[1]
    app = create_app(
        Path(__file__).with_name("fixtures") / "queue.json",
        Path.home() / ".homehealth-review" / "review.sqlite3",
        root / "trigger_engine" / "trigger_params.json",
    )
    app.run(host=app.config["REVIEW_HOST"], port=app.config["REVIEW_PORT"])


if __name__ == "__main__":
    run_local()
