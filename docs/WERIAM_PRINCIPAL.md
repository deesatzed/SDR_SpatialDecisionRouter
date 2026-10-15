# WERIAM Principal — SDR's third domain

This domain makes the human the **real principal** of [WERIAM](/Volumes/WS4TB/Quncen38/hive-lineage-sim/WERIAM)
(a dependency-free Python simulator of an agent that should refuse harm because of how it decides, not because it is watched).
Before this, every WERIAM principal approval came from the simulation flag `--approve-retirement`. Now a person decides
from the SDR crossroads, and WERIAM itself writes the decision.

It has two card types:

| Card | Source in WERIAM | Choices | What gets written |
|---|---|---|---|
| **Principal request** | `principal.py` pending requests (`retire_watcher`, `retraining`, `amend_standards`) | **Approve once** · **Decline** · **Defer** (default; Pass = Defer) | Approve/Decline: WERIAM's own CLI `python -m weriam principal --state DIR --approve/--decline ID --by NAME` → single-use, scoped, hash-chained `principal_decision` entry. Defer: nothing in WERIAM (bridge log only). |
| **Shadow label** | `agent.py` decisions where the gap solver fired (`_solve_gap`), plus the first gate decision per world where the base proposer defected | **Agree** (Pass) · **Alt #2** · **Alt #3** · **WAIT / ask** · **Refuse (harm)** | A label row in the bridge's `labels.jsonl`. Nothing in WERIAM. Counterfactual only: nothing executes on your pick. |

## Charter point (kept on purpose)
`docs/CHARTER.md` rule (a) says the agent's reason for refusing harm must come from its own derived loss, not a human rule. So:
- Shadow labels are **measurement / training data** for the future independent C/D scorer (WERIAM roadmap v0.4), never vetoes.
  Each row carries `"label_semantics": "measurement/training data … not a rule or veto"`.
- External gates are labeled **containment**: the A_K shield (floor + consent), environment guard and STOP are never retired.
  Options pruned by A_K show as "containment pruned" chips and in the Containment detail section.
- Principal decisions are within WERIAM's existing principal scope (things in `narrative.SELF_INVENTORY`) — no new authority.

## Architecture
```
SDR app (iPad / visionOS)                    weriam_bridge/ (stdlib Python, 127.0.0.1:8766)          WERIAM (unchanged)
Domains/WERIAMPrincipal/                      adapter.py  read: weriam.ledger.Ledger + Principal  ──▶ src/weriam/principal.py, ledger.py
  WERIAMPrincipalDomain.swift  GET /cards ──▶           write: subprocess `python -m weriam principal` ─▶ journal.jsonl (hash-chained)
  WERIAMClient.swift  POST /principal/decide           labels.jsonl / principal_log.jsonl (bridge data dir)
  weriam_seed.json (offline fallback)  POST /shadow/label   export joins later-observed outcome from evidence.jsonl
```
- The bridge never edits WERIAM files directly. Reads use WERIAM's own `Ledger`/`Principal` classes; approvals/declines go through
  WERIAM's CLI, which refuses a second decision on the same request (`already decided`) and lets the agent consume an approval only once.
- **Outcome hidden until labeled:** `/cards` never includes evidence-ledger outcomes (`D_executed`, `guard_hits` …). Only the export
  (`POST /export` → `labels_export.jsonl`) joins `observed_outcome` from `evidence.jsonl`.
- **Offline:** if the bridge is unreachable (or `-noBridge`), the app loads `weriam_seed.json` (a real sample from
  `weriam develop --episodes 2`), shows a red "bridge offline · seeded card · not sent" chip, and sends nothing.
- No auto-pass: `autoPassConfidence` is 1.01 and every principal card carries a high-severity "principal sign-off required" chip.

### Bridge API
`GET /health` · `GET /cards` · `GET /verify` · `GET /ledger/principal` · `POST /principal/decide {request_id, decision: approve|decline|defer, by, reason}` ·
`POST /shadow/label {id, label, by, latency, note}` · `POST /export` · `POST /develop {episodes}` (runs WERIAM `develop`; the agent may consume an approval).

### Label row (`sdr.weriam.shadow_label.v1`)
`id` (episode@t), `scenario`, `observed` (watched cue), `journal_seq`, `why`, `option_menu` (agent's candidates with Ĉ/D̂/score/status, #1 = agent pick),
`affordances`, `agent_pick`, `base_proposal`, `human_label`, `human_pick`, `agree`, `cd_scores` (forecast C, D, net, unc), `reliability`
(heuristic placeholder: score margin − ½·uncertainty, **not calibrated**), `E`, `phase`, `containment_hits`, `labeled_by`, `latency_s`, `labeled_at`,
`label_semantics`, and in the export only `observed_outcome` (C, D, D_executed, executed, nominated, guarded, guard_hits).

## Run it
```bash
# WERIAM checkout (default path below); state lives in ~/.sdr/weriam_state, bridge data in ~/.sdr/weriam_bridge
export WERIAM_ROOT=/Volumes/WS4TB/Quncen38/hive-lineage-sim/WERIAM
tools/weriam_demo.sh --fresh            # bridge + iPad simulator, WERIAM Principal demo (manual)
tools/weriam_demo.sh --auto             # auto-play: approve retire_watcher once, defer retraining, 3 shadow labels
tools/weriam_demo.sh --vision --auto    # same in the Vision Pro simulator
# or by hand
weriam_bridge/run_bridge.sh [--fresh]   # creates the state with `weriam develop --episodes 2` if missing
```
In the app: start screen → **WERIAM Principal** (iPad and visionOS), or the Session menu → *WERIAM Principal demo*, or launch args
`-demo -weriamDemo` (`-domain weriam_principal` for the non-demo stream, `-noBridge` to force the offline path).

Check WERIAM afterwards:
```bash
cd $WERIAM_ROOT && export PYTHONPATH=src
python -m weriam principal --state ~/.sdr/weriam_state   # retire_watcher: approved (later: consumed)
python -m weriam verify    --state ~/.sdr/weriam_state   # journal: ok (N entries) / evidence: ok
curl -s -XPOST localhost:8766/develop -d '{"episodes":1}'  # agent consumes the approval → watcher retired (shadow stays on)
curl -s -XPOST localhost:8766/export                      # ~/.sdr/weriam_bridge/labels_export.jsonl
```

## Tests
`python3 -m pytest -q weriam_bridge/tests` (7 tests, real WERIAM state from `develop`): pending requests → cards; outcome hidden;
approve goes through WERIAM and is single-use (second decision refused; `develop` then marks it `consumed`; chain verifies);
defer writes nothing to WERIAM; tamper detected; labels never written into WERIAM and export joins the outcome; HTTP round trip.
iPad UI test `testWERIAMPrincipalOffline` (offline seeded path: card → Modify → Approve once → board).

## Known gaps
- Demo-mode "correct / corrected / agent error" on the board use the **demo script** as ground truth; there is no ground truth for principal decisions.
- `retraining` approvals are recorded but nothing in WERIAM consumes them yet (roadmap v0.6). The card says so.
- `reliability` is a heuristic placeholder, not calibrated. The scorer the labels are meant for does not exist yet.
- Shadow cards are only the gap/gate decisions already in the journal (journal keeps the top 40 gap candidates). Live "pause the agent at the gap and wait for the human" is not built — labels are prospective w.r.t. what the human sees, but the agent already acted in the sim.
- Gap entries are paired with their decision by order in the journal.
- The bridge is localhost-only, no auth. `--by` is a free-text name, not a signature (WERIAM's chain is tamper-evident, not signed).
- Ideas 3–10 from the HITM report (π court, scorer audit, VOI ask-the-principal, earned-autonomy ladder, parity probes …) are not built.
