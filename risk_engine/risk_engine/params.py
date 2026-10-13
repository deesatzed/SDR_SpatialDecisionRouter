"""Load + validate the human-editable parameter file. Every number is an entry {value, source, citation[, note]}."""
from itertools import product
from pathlib import Path
import yaml

SOURCES = {"placeholder", "expert_estimate", "literature"}
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "params.yaml"


class ParamError(ValueError):
    pass


def is_entry(x):
    return isinstance(x, dict) and "value" in x and "source" in x


def check_entry(path, e, kind="prob"):
    if not is_entry(e):
        raise ParamError(f"{path}: expected {{value, source, citation}} entry")
    if e["source"] not in SOURCES:
        raise ParamError(f"{path}: source must be one of {sorted(SOURCES)}, got {e['source']!r}")
    cit = e.get("citation", "")
    if e["source"] == "literature" and not str(cit).strip():
        raise ParamError(f"{path}: literature source requires a citation")
    if e["source"] != "literature" and str(cit).strip():
        raise ParamError(f"{path}: citation must be empty unless source is literature")
    v = e["value"]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ParamError(f"{path}: value must be numeric")
    if kind == "prob" and not (0.0 <= v <= 1.0):
        raise ParamError(f"{path}: probability {v} outside [0,1]")
    if kind == "cost" and v < 0:
        raise ParamError(f"{path}: cost {v} must be >= 0")
    if kind == "severity" and (int(v) != v or not 1 <= v <= 5):
        raise ParamError(f"{path}: severity must be integer 1-5")
    return float(v)


def iter_entries(node, path=""):
    if is_entry(node):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from iter_entries(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_entries(v, f"{path}[{i}]")


def validate(p):
    for key in ["thresholds", "labels", "context_priors", "truths", "complaints", "loss"]:
        if key not in p:
            raise ParamError(f"missing section {key}")
    for path, e in iter_entries(p):
        kind = "prob"
        if path.startswith("loss.miss_cost_by_severity") or path in ("loss.modify_cost", "loss.escalate_cost") or (path.startswith("complaints.") and path.endswith(".modify_cost")):
            kind = "cost"
        if path == "thresholds.critical_severity":
            kind = "severity"
        check_entry(path, e, kind)
    for name, t in p["truths"].items():
        st = t.get("states")
        if not st or len(st) < 2 or len(set(st)) != len(st):
            raise ParamError(f"truths.{name}.states must be >=2 unique labels")
        for comp, pr in t["prior"].items():
            if len(st) == 2:
                check_entry(f"truths.{name}.prior.{comp}", pr)
            else:
                if set(pr) != set(st[1:]):
                    raise ParamError(f"truths.{name}.prior.{comp}: needs entries for {st[1:]}")
                if sum(e["value"] for e in pr.values()) > 1.0 + 1e-9:
                    raise ParamError(f"truths.{name}.prior.{comp}: risky-state probabilities sum > 1")
        for k in ["false_positive", "recall_miss", "conceal_base"]:
            if k not in t["report"]:
                raise ParamError(f"truths.{name}.report.{k} missing")
        for c in list(t["report"].get("conceal_context", {})) + list(t["report"].get("recall_context", {})):
            if c not in p["context_priors"]:
                raise ParamError(f"truths.{name}: unknown context {c}")
    for cname, c in p["complaints"].items():
        for t in c["truths"]:
            if t not in p["truths"]:
                raise ParamError(f"complaints.{cname}: unknown truth {t}")
            if cname not in p["truths"][t]["prior"]:
                raise ParamError(f"complaints.{cname}: truth {t} has no prior for this complaint")
        for f in c.get("plan_flags", []) + c.get("context", []):
            if f not in p["context_priors"]:
                raise ParamError(f"complaints.{cname}: unknown context/plan flag {f}")
        allowed = set(c["truths"]) | set(c.get("plan_flags", []))
        for dname, d in c["dx"].items():
            for par in d["parents"]:
                if par not in allowed:
                    raise ParamError(f"complaints.{cname}.dx.{dname}: parent {par} not a truth/plan flag of this complaint")
            states = [p["truths"][x]["states"] if x in p["truths"] else ["no", "yes"] for x in d["parents"]]
            want = set(product(*states))
            got = [tuple(r["when"][x] for x in d["parents"]) for r in d["cpt"]]
            if len(got) != len(set(got)) or set(got) != want:
                raise ParamError(f"complaints.{cname}.dx.{dname}: cpt rows must cover each parent combination exactly once")
            for a in d.get("mitigated_by", []):
                if a not in ("modify", "escalate"):
                    raise ParamError(f"complaints.{cname}.dx.{dname}: bad mitigated_by {a}")
    if not p["labels"] or p["labels"][-1]["max"] < 1.0:
        raise ParamError("labels must end with max: 1.0")
    return p


def load_params(path=None):
    path = Path(path or DEFAULT_PATH)
    with open(path) as f:
        p = yaml.safe_load(f)
    return validate(p)


def v(e):
    return float(e["value"])


def source_summary(p):
    s = sorted({e["source"] for _, e in iter_entries(p)})
    return s[0] if len(s) == 1 else "mixed(" + ",".join(s) + ")"


def markdown_table(p):
    rows = ["| parameter | value | source | citation | note |", "|---|---|---|---|---|"]
    for path, e in iter_entries(p):
        rows.append(f"| `{path}` | {e['value']} | {e['source']} | {e.get('citation', '')} | {e.get('note', '')} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(markdown_table(load_params()))
