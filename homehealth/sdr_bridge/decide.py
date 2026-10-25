"""Build the headset review pack and run Layer 1 on it.

SYNTHETIC only. Fact text is copied from the case library. Decisions come from
layer1_adapter (trigger params 0.14.4-placeholder, engine v1.14.4). This module
does not call OpenRouter or any other model. Jev is not consulted: jev_pick is None,
which is the headset path (Layer 1 alone).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JEV = ROOT / "homehealth" / "jev_baseline"
if str(JEV) not in sys.path:
    sys.path.insert(0, str(JEV))

import layer1_adapter as L  # noqa: E402
import routes as RT  # noqa: E402

ENGINE = "homehealth-layer1"
ENGINE_VERSION = "v1.14.4"
PACK_PATH = ROOT / "SpatialDecisionRouter" / "Domains" / "HomeHealth" / "homehealth_vignettes.json"

# Existing library cases only. Order is the review order on the headset.
PACK = (
    ("homehealth/library/library_v2_smart_accepted.json", "ST1-002"),
    ("homehealth/library_expansion_v2/library_expansion_v2_accepted.json", "LX12-007"),
    ("homehealth/library_expansion_v2/library_expansion_v2_accepted.json", "LX12-008"),
    ("homehealth/library/library_v2_smart_accepted.json", "NV6-001"),
    ("homehealth/library_expansion_v1/library_expansion_v1_accepted.json", "LX4-009"),
    ("homehealth/library/library_v2_smart_accepted.json", "HK6-007"),
)

CLIN = ("nurse_task", "provider_task", "urgent_page")


def _s(v) -> str:
    if v is None:
        return ""
    return str(v)


def _join(xs) -> str:
    if not xs:
        return "none"
    if isinstance(xs, list):
        return ", ".join(_s(x) for x in xs if _s(x)) or "none"
    return _s(xs) or "none"


def _meds(meds) -> str:
    if not meds:
        return "none"
    parts = []
    for m in meds:
        if isinstance(m, dict):
            parts.append((_s(m.get("name")) + " " + _s(m.get("dose"))).strip())
        elif _s(m):
            parts.append(_s(m))
    return "; ".join(p for p in parts if p) or "none"


def _baseline(b) -> str:
    if not isinstance(b, dict):
        return "not recorded"
    bits = [f"{k} {v}" for k, v in b.items() if v is not None and v != ""]
    return ", ".join(bits) if bits else "not recorded"


def _flags(dq) -> str:
    if not isinstance(dq, dict):
        return "none"
    flags = dq.get("artifact_flags") or []
    return "; ".join(_s(x) for x in flags if _s(x)) or "none"


def _status(s) -> str:
    if not isinstance(s, dict):
        return "not recorded"
    bits = []
    if s.get("phase"):
        bits.append(_s(s.get("phase")))
    if s.get("monitoring_day") is not None:
        bits.append(f"monitoring day {s.get('monitoring_day')}")
    return ", ".join(bits) if bits else "not recorded"


def _discharge(d) -> str:
    if not d:
        return "none"
    if isinstance(d, dict):
        if d.get("day") is None and not d.get("reason"):
            return "none"
        bits = []
        if d.get("day") is not None:
            bits.append(f"day {d.get('day')}")
        if d.get("reason"):
            bits.append(_s(d.get("reason")))
        return ", ".join(bits) if bits else "none"
    return _s(d)


def facts_of(case: dict) -> dict:
    """Structured fact fields only. Label / answer fields are not copied."""
    return {k: case.get(k) for k in L.FACT_FIELDS}


def decision_for(case: dict) -> dict:
    """Layer 1 route and optional device ticket. jev_pick is None (no cloud model)."""
    d = L.evaluate_case(case)
    route, owner = L.route(d, None)
    raw = d.get("device_ticket")
    ticket = None
    ticket_note = None
    if route == "silent_log":
        shown = L.V141.final_ticket(d, route)
        if shown:
            ticket = {"type": shown.get("type"), "detail": shown.get("detail"), "rule": shown.get("rule")}
    elif route in CLIN:
        ticket = None
    elif route is None and raw and raw.get("ticket_if_route") == "silent_log":
        ticket_note = (
            "A device ticket is conditional on silent_log. Layer 1 did not own the route, "
            "and this headset does not call Jev."
        )
    elif raw:
        shown = L.V141.final_ticket(d, route or "silent_log")
        if shown and route not in CLIN:
            ticket = {"type": shown.get("type"), "detail": shown.get("detail"), "rule": shown.get("rule")}
    if route in RT.DEFINITIONS:
        definition = RT.DEFINITIONS[route]
    elif route is None:
        definition = "Layer 1 did not own a route. Jev is not called from the headset."
    else:
        definition = route
    return {
        "route": route,
        "owner": owner,
        "tier": d.get("tier"),
        "rule": d.get("rule"),
        "reason": d.get("reason"),
        "plain_reason": d.get("plain_reason"),
        "route_definition": definition,
        "escalation_target": d.get("escalation_target"),
        "ticket": ticket,
        "ticket_note": ticket_note,
    }


def _library_case(rel: str, case_id: str) -> dict:
    data = json.loads((ROOT / rel).read_text())
    cases = data["cases"] if isinstance(data, dict) else data
    return next(c for c in cases if c.get("case_id") == case_id)


def vignette_from_case(case: dict, source: str) -> dict:
    facts = facts_of(case)
    return {
        "case_id": case.get("case_id"),
        "source": source,
        "library_label": case.get("expected_route"),
        "age_band": _s(case.get("age_band")),
        "sex": _s(case.get("sex")),
        "living": _s(case.get("living")) or "not recorded",
        "pmh": _join(case.get("pmh")),
        "meds": _meds(case.get("meds")),
        "devices": _join(case.get("devices")),
        "goals": _s(case.get("patient_goals")) or "not recorded",
        "function": _s(case.get("function_baseline")) or "not recorded",
        "baseline": _baseline(case.get("baseline_30d")),
        "baseline_status": _status(case.get("baseline_status")),
        "discharge": _discharge(case.get("discharge")),
        "trend": _s(case.get("trend_last_7d")),
        "note": _s(case.get("caregiver_or_nurse_note")),
        "artifact_flags": _flags(case.get("data_quality")),
        "facts": facts,
        "layer1": decision_for(facts),
    }


def build_pack() -> dict:
    cases = [vignette_from_case(_library_case(rel, cid), rel) for rel, cid in PACK]
    params = L.PARAMS.get("version")
    return {
        "synthetic": True,
        "engine": ENGINE,
        "engine_version": ENGINE_VERSION,
        "params_version": params,
        "note": (
            "SYNTHETIC review pack for the visionOS home-health domain. "
            "Narrative fields are copied from the case library. "
            "layer1 is the bundled snapshot from homehealth Layer 1 "
            f"({ENGINE_VERSION}, params {params}) with no cloud model. "
            "Regenerate with: python3 homehealth/sdr_bridge/export_vignettes.py"
        ),
        "cases": cases,
    }


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def load_pack() -> dict:
    return json.loads(PACK_PATH.read_text())


def live_cases(pack: dict | None = None) -> list[dict]:
    """Recompute Layer 1 from bundled facts. Does not echo the stored snapshot."""
    pack = pack if pack is not None else load_pack()
    out = []
    for c in pack["cases"]:
        out.append({"case_id": c["case_id"], "layer1": decision_for(c["facts"])})
    return out
