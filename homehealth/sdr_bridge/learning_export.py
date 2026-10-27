"""Roll Overseer decision logs into a shared synthetic update.

Later phases can read this file. It is local. It does not talk to another site.
Input is JSONL from a routing export (`context`) or the unified ledger
(`card_payload`). Both carry the home-health keys written at decision time.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

SCHEMA = "sdr.homehealth.learning.v1"

TRACKED = (
    "review_role",
    "review_action",
    "agent_refused",
    "refusal_reason",
    "revisit",
    "prior_decision",
    "new_evidence",
    "voi_observation",
    "voi_flip_route",
    "voi_flip_if",
    "goals_constraint",
    "goals_blocks_escalation",
    "goals_kind",
    "uncertainty_differential",
    "uncertainty_confidence",
    "act_under_uncertainty",
    "case_id",
    "route",
)


def load_records(path: Path) -> list[dict]:
    text = path.read_text().strip()
    if not text:
        return []
    if text[0] == "[":
        data = json.loads(text)
        return data if isinstance(data, list) else []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def payload_of(rec: dict) -> dict:
    if isinstance(rec.get("card_payload"), dict):
        payload = dict(rec["card_payload"])
    elif isinstance(rec.get("context"), dict):
        payload = dict(rec["context"])
    else:
        payload = {}
    human = rec.get("human_decision") if isinstance(rec.get("human_decision"), dict) else {}
    chosen = human.get("answer") or rec.get("routedAnswer") or rec.get("effectiveAnswer") or payload.get("route")
    gesture = human.get("gesture") or rec.get("gesture") or ""
    decided_by = human.get("decided_by") or rec.get("decidedBy") or ""
    case_id = payload.get("case_id") or rec.get("item_id") or rec.get("itemId") or ""
    payload["case_id"] = case_id
    payload["chosen_route"] = chosen or ""
    payload["gesture"] = gesture
    payload["decided_by"] = decided_by
    payload["review_role"] = payload.get("review_role") or "overseer"
    return payload


def _flag(payload: dict, key: str) -> bool:
    return str(payload.get(key) or "") == "1"


def _row(payload: dict, keys: tuple[str, ...]) -> dict:
    row = {k: payload.get(k) or "" for k in keys}
    row["case_id"] = payload.get("case_id") or ""
    row["review_role"] = payload.get("review_role") or ""
    row["review_action"] = payload.get("review_action") or ""
    row["chosen_route"] = payload.get("chosen_route") or ""
    return row


def _bucket(rows: list[dict]) -> dict:
    roles = Counter(r["review_role"] or "unknown" for r in rows)
    actions = Counter(r["review_action"] or "(none)" for r in rows)
    return {
        "n": len(rows),
        "by_review_role": dict(roles),
        "by_review_action": dict(actions),
    }


def rollup(records: list[dict]) -> dict:
    payloads = [payload_of(r) for r in records if isinstance(r, dict)]
    overseer = [p for p in payloads if p.get("review_role") == "overseer"]
    refusals = [_row(p, ("refusal_reason", "uncertainty_differential")) for p in payloads if _flag(p, "agent_refused") or p.get("review_action") == "human_after_refusal"]
    revisits = [_row(p, ("prior_decision", "new_evidence")) for p in payloads if _flag(p, "revisit") or p.get("review_action") == "revisit_prior"]
    waits = [_row(p, ("voi_observation", "voi_flip_route", "voi_flip_if")) for p in payloads if p.get("review_action") == "voi_wait" or p.get("voi_observation")]
    goals = [
        _row(p, ("goals_constraint", "goals_kind", "goals_blocks_escalation"))
        for p in payloads
        if p.get("goals_constraint") or _flag(p, "goals_blocks_escalation")
    ]
    uncertainty = [
        _row(p, ("uncertainty_differential", "uncertainty_confidence", "act_under_uncertainty"))
        for p in payloads
        if p.get("uncertainty_differential")
    ]
    return {
        "schema": SCHEMA,
        "synthetic": True,
        "loop": (
            "Overseer physician logs roll up into this shared update. "
            "Bedside and Nurse rows stay in the same file so a later phase can learn across roles. "
            "Local artifact only. No live multi-site service."
        ),
        "tracked_keys": list(TRACKED),
        "overseer": _bucket(overseer),
        "all_roles": _bucket(payloads),
        "shared_update": {
            "refusals": refusals,
            "revisits": revisits,
            "voi_waits": waits,
            "goals_constraints": goals,
            "uncertainty": uncertainty,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Roll home-health HITM logs into a shared update.")
    parser.add_argument("jsonl", type=Path, help="routing JSONL (context) or ledger JSONL (card_payload)")
    parser.add_argument("-o", "--out", type=Path, required=True, help="rollup JSON path")
    args = parser.parse_args(argv)
    artifact = rollup(load_records(args.jsonl))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2) + "\n")
    print(f"wrote {args.out} ({artifact['all_roles']['n']} decisions, {artifact['overseer']['n']} overseer)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
