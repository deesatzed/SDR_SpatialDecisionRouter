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

## M2 — earned-autonomy dials
- **Rules** (`Core/DialEngine.swift`, pure functions, unit-tested): evidence = decisions of a context since its last dial change
  that have an **observed outcome** in the ledger; success = the **agent's** proposal matched the outcome.
  Posterior Beta(1+s, 1+f), 90% interval by normal approximation.
  - rise: n ≥ 5 and interval low ≥ 0.6 → autonomy +5, deference −5
  - lower: n ≥ 5 and interval high ≤ 0.5 → autonomy −5, deference +5
  - **demotion:** any critical miss (agent wrong where a hard trigger / escalation applied, or on a card marked
    `severity=critical`) → autonomy −15, deference +15, immediately, no minimum n
  - split ratings may nudge detail (buried me +5 / too abstract −5) or challenge (overstepped me −5) only alongside a graded
    window of n ≥ 5 and with ≥ 3 ratings of one kind; split ratings alone never move anything; rewards stay outcome-based
  - caps applied after every move (clinical: autonomy ≤ 40, deference ≥ 80); no-op moves write nothing
  - **thresholds are design placeholders**, not validated
- **Signed:** every move is a `kind=dial_change` ledger line with `dial_before/after`, `reason`, `evidence_refs`, `posterior`
  (`escalation_flags: ["demotion"]` for demotions). Current dials = seed + replay of those lines, so they persist and are auditable.
- **Reversible:** "Undo move" writes a new signed `dial_change` (REVERT) restoring the previous dials.
- **Applies to every domain** keyed by unified domain id (ED triage, tele-doc, WERIAM, symbiosis:<area>); decisions record the
  current dials. WERIAM moves on its teacher outcomes as they arrive.
- **UI:** dial gauge + autonomy/deference sparkline (history from the ledger) + "Why it moved" line with n / mean / interval.
- **Export:** `dials/dial_changes.jsonl` in `tools/unified_export.py`.
- **Demo:** the Symbiosis demo now runs finance first (5 correct graded calls → earned rise) then ED triage (SYM-ED-3 critical
  miss → demotion shown on SYM-ED-4). `tools/symbiosis_demo.sh --auto --fresh-ledger --export`.

## Case import hooks
- `-importItems <dir>` (dir = `tools/import_cases.py --out`): Symbiosis loads `items/personal_finance.json` (options mapped by
  closest fit, shown on the card; outcomes from `decisions_imported.jsonl`). `tools/symbiosis_demo.sh --import=<dir>`.
- `-importCSV <dir>/encounters.csv` loads in AI tele-doc (fixed a crash on outpatient complaints in `EncounterImporter`).
- ED triage is **not** wired: its items come from a capacity/queue simulation with several linked decisions per patient.


## M3 — Human sharpness spot-checks

When the AI absorbs a lot of detail in an area, the human's own judgment can quietly atrophy. M3 checks it.

- **Scheduling** (`RouterEngine.considerSharp`): when a card becomes Now and its area's detail dial is ≥ `-sharpDetail` (default 85),
  a spot-check fires at `-sharpRate` (default 0.3, seeded RNG) or every `-sharpEvery N` eligible cards. In the demo, cards listed in
  `SymbiosisDomain.demoSpots` are forced (FIN-4/5/6). **Never on hard-trigger cards** — escalation is never delayed, and a firing trigger preempts.
- **"Your call first"**: the AI column, proposal, confidence, why-queued reasons, split row and the Pass/accept shortcut are hidden; the
  human picks an option. That pick is the routed decision. Then a reveal strip shows *you · AI · outcome · held up/missed*.
- **Ledger**: each check is a signed `kind: "spot_check"` line referencing the decision (`spot_check: {human_call, agent_pick, outcome,
  human_correct, agent_correct, hidden, trigger}`); a later `outcome` line grades an ungraded check.
- **Calibration** (`DialEngine.sharpness`): Beta(1+k, 1+n−k) per area, shown on the calibration card with n and 90% interval, beside
  **overrides held up** (`DialEngine.overrides`: decisions where the human changed the agent's pick, graded by outcome).
- **Dial effect** (inside the M2 window, signed `dial_change`): n ≥ 3 and 90% high ≤ 0.5 → detail −5, challenge +5 ("AI hands detail back");
  at detail ≥ 85, a "buried me" split can raise absorption only with 90% low ≥ 0.5. Sharpness never moves autonomy.
- **Demotion softened**: a critical miss still cuts autonomy −15, but deference rises at most +10 and stops at 95 (floor 80 still enforced).
- **Export**: `sharpness/spot_checks.jsonl` (outcomes folded in), count in `summary.json`.
- Demo: `tools/symbiosis_demo.sh --auto` — three missed checks in finance, then at FIN-6 the earned rise and the sharpness hand-back land in one move.


## M4 — Frozen-replay promotion + Principal card

Pipeline (Swift `Core/PromotionEngine.swift` + `Core/PromotionFlow.swift`; Python mirror `tools/promotion.py`, same numbers):

1. **Critic proposes** (`deterministic-v1`): per area, tries predicates (agent confidence < 0.6/0.65/0.7, severity = critical) on
   held-in evidence (bundled synthetic history + this device's graded Symbiosis decisions, minus every held-out replay id) and proposes
   the rule with the best in-sample gain (≥ 3 supporting cases). `llmCritic()` / `critic_llm()` is a stub: no external calls; anything it
   returned would still only be a proposal. Signed `policy_proposal` line with evidence refs.
2. **Frozen, blinded replay** (`replay_*` resources = `data/replay_seed/replay/seed`, written by the exporter): manifest sha256 of
   cases and answers re-checked on every load (tamper → refused); cases carrying `outcome`/`human_answer`/… are refused (leakage);
   candidate evidence overlapping held-out ids is refused; policies only receive `ReplayCase` (inputs), answers are joined only inside
   the evaluator. Evaluator `replay-eval-v1` and the pre-registered margin are hashed and pinned (`tools/evaluator.lock`, Swift
   `evaluatorLock`): changing either without a new version is refused.
3. **Rules** (pre-registered): Δaccuracy ≥ 0.05 with 90% interval reported, n ≥ 20, wins/losses Beta 90% low > 0.5, candidate critical
   misses ≤ champion's, clinical areas may not remove any escalation. Signed `policy_evaluation` line: verdict, reasons, metrics, replay
   hashes, evaluator version + hash. Failing candidates are **discarded and logged**.
4. **Principal card** (passing only): before/after diff of every replay case whose behaviour changes (worse first) with outcomes;
   **Approve once / Decline / Defer (Pass)**. Signed `principal_decision`. Approve on a stale (other champion generation), failing or
   re-hashed evaluation writes the decision but does not promote.
5. **Promotion**: signed `promotion` line (rules before/after, champion generation +1). The champion changes the AI's pick on live
   Symbiosis cards (never on hard-trigger cards, never rewriting a clinical escalation). **Rollback**: signed `rollback` line, generation +1.
6. **Export**: `promotion/promotion_records.jsonl`.

Demo (seed is SYNTHETIC with a planted real pattern and a planted spurious one): finance rule "confidence < 0.65 → Hold" wins on replay
(35/60 → 53/60, Δ +0.30 [+0.19, +0.41], wins/losses 20/2); ED rule "critical → Alternative plan" looks good in-sample but on replay
loses (Δ −0.20, critical misses 0 → 8, removes 8 escalations) and is discarded. Open **Promotion** on any Symbiosis card (iPad sheet,
visionOS window) → Run critic + replay → Approve once → gen 1 → Roll back → gen 2. Offline: `python3 tools/promotion.py --train
data/replay_seed/train.jsonl --replay data/replay_seed/replay/seed`. Regenerate the seed: `python3 tools/make_replay_seed.py`.
