# Symbiosis — M0 + M1 (what is built)

Spec: [SYMBIOSIS_PLAN.md](SYMBIOSIS_PLAN.md). This file documents what landed for M0 (unified decision record +
exporter) and M1 (demoable slice), and what is still placeholder.

## M0 — unified decision record
- **Model:** `SpatialDecisionRouter/Core/DecisionLedger.swift` — `UnifiedDecisionRecord` (schema `sdr.decision.v1`, every
  field in plan §4), `DecisionLedger` (append-only JSONL, SHA-256 hash chain, Ed25519 signature per line).
- **Key:** the same device approver key as WERIAM Principal v2 (`ApproverSigner`, Keychain; file fallback in the simulator).
- **Who writes:** `RouterEngine.route()` — the single path every domain's HITM decision goes through — appends one
  record per decision: ED triage, AI tele-doc (`ai_doc_review` → `ai_tele_doc`), WERIAM Principal, Symbiosis (`symbiosis:<area>`).
  `routing_log.jsonl` is still written as before (old tools keep working).
- **Later facts are new lines, never edits:** `kind=outcome` (e.g. WERIAM's teacher outcome arriving after a live pause) and
  `kind=split_rating` (a split rating given after the decision) reference the decision by `ref_id`.
- **Outcomes are nullable and carry their source:** `seeded_scenario (synthetic)`, `simulator_ground_truth (synthetic)`,
  `weriam_teacher (WERIAM observed outcome)`. ED triage and tele-doc still have **no real-world outcomes** — their grades come
  from the simulator's rule-based truth (open question §9.2).
- **File:** app `Documents/decisions/decision_ledger.jsonl`; copied into `Documents/exports/` on Export. `-freshLedger` starts a new one.
- **WERIAM bridge:** the bridge's own `labels.jsonl` / `signed_approvals.jsonl` remain as WERIAM-side mirrors; every label and
  approval made in the app is also in the unified ledger, so no HITM decision lives only in a domain-private log.

### Exporter — `tools/unified_export.py`
```bash
python3 tools/unified_export.py decision_ledger.jsonl -o out/ [--legacy routing_log.jsonl] [--replay-name NAME] [--strict]
```
Verifies chain + signatures (same canonical JSON as Swift; tested against a ledger written by the Swift unit test), folds
amendments, then writes:
1. `finetune/sft.jsonl` and `finetune/preference.jsonl` (chosen/rejected; outcome-aware `label_source`)
2. `rl/rewards.jsonl` — reward = +1/−1 vs observed outcome, `null` when unknown; split rating only in `aux_split_rating`
3. `replay/<name>/{cases,answers}.jsonl + manifest.json` — frozen (sha256 in manifest) and blinded (cases carry no human label or outcome)

`--legacy` converts pre-M0 `routing_log.jsonl` lines (marked `provenance: legacy_unsigned`; duplicates of signed records are skipped).
`tools/to_training.py` is unchanged and still works on routing logs.

## M1 — demoable slice
- **Context + dials:** `Core/SymbiosisKit.swift` — `SymbiosisContext` with deference / detail absorption / challenge / autonomy
  horizon. Values are **seeded placeholders** (`source: seed (placeholder — not learned…)`); earned movement is M2.
  Clinical caps are enforced now: autonomy ≤ 40, deference ≥ 80 (ED triage, tele-doc).
- **Card:** `Core/SymbiosisViews.swift` — three columns: *You hold* (orange), *Bridge* (checkpoint names the fixed trigger),
  *AI holds* (blue, collapsed; "Show AI depth"). Works on iPad and visionOS (shared NowCard).
- **Dual labels:** Pass / Modify / Escalate (and hard-trigger Acknowledge) + one-tap split rating
  (About right / Overstepped me / Buried me in detail / Too abstract). Both land in the unified record.
- **Areas:** ED triage (3 cards, one with a hard trigger) + personal finance (2 cards). All SYNTHETIC; no LLM. The agent's
  confidence on each card is seeded and labelled as such. `OfflineStubGenerator` is the optional local-LLM hook (returns nil).
- **Manifesto:** four lenses (philosophical, technical, teaching, executive) in our own words, editorial look (paper `#FBF9F5`,
  ink `#1C1917`, system serif + mono in place of Fraunces/Plex — no fonts bundled). Opens from the card, the Session menu (iPad),
  the launcher (visionOS, separate window) and the landing page.
- **Demo:** start screen → **Symbiosis**, or `tools/symbiosis_demo.sh [--ipad|--vision] [--auto] [--fresh-ledger] [--export]`
  (launch flags `-demo -symbiosisDemo`).

## Credit
Concepts adapted from the *Symbiont* Google AI Studio export reviewed read-only (areas + policy vector, three-column synthesis,
one-tap split presets, four audience lenses). Its file header says Apache-2.0; there is no LICENSE file. Nothing was copied:
code is a Swift rewrite, manifesto copy is our own wording (two lines are close paraphrases of Symbiont ideas: "the why and the
ought" / "the how and the exhaustive what", and "wisdom is what experience teaches that no knowledge base can hold").
No Symbiont images are used. Confirm with the author before any commercial use.
