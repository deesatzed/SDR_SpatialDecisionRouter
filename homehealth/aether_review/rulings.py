"""Read-only, bounded references from clinician-ruling CSV files."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClinicianReference:
    case_id: str
    ruling: str
    excerpt: str
    evidence_id: str


def load_rulings(path: Path | str) -> list[ClinicianReference]:
    references: list[ClinicianReference] = []
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            case_id = (row.get("case_id") or "").strip()
            ruling = (row.get("ruling") or "").strip()
            if not case_id or not ruling or case_id.startswith("POLICY-"):
                continue
            excerpt = (row.get("note") or "").strip()[:500]
            references.append(ClinicianReference(
                case_id=case_id,
                ruling=ruling,
                excerpt=excerpt,
                evidence_id=f"clinician_ruling:{case_id}",
            ))
    return references


def current_references(path: Path | str, case_id: str, *, include_fallback: bool = False, limit: int = 5) -> list[ClinicianReference]:
    references = load_rulings(path)
    exact = [reference for reference in references if reference.case_id == case_id]
    if exact:
        return exact[:limit]
    return references[:limit] if include_fallback else []
