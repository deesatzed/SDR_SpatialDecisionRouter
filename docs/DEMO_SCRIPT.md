# Demo script — AI Doc Review, physician in the middle (3–5 min)

All encounters are **SYNTHETIC**. Risk-engine parameters are **placeholders** pending expert review. Treat the categorical labels as the output; the exact digits are not calibrated.

## One-command start

```bash
cd ~/Projects/SpatialDecisionRouter
tools/demo.sh            # sidecar + simulator + app in DEMO mode (you click through)
tools/demo.sh --auto     # same, auto-plays the 6 steps
```

- `demo.sh` starts `risk_engine` on 127.0.0.1:8765 if it isn't already healthy, boots the `SDR-VisionPro` simulator, installs the app and launches it with `-demo`.
- On the start window there are **Demo** and **Demo (auto-play)** buttons. On the board there are **Reset demo** and **Auto-play** buttons.
- Every card shows a badge. **BN · params: placeholder** means the Bayesian sidecar answered. **fallback · sidecar offline** means the Swift heuristics are running, and the demo still works.

**Fallback (a pre-recorded video):** `tools/demo.sh --auto --record 185` writes `screens/demo.mp4`, recorded with `xcrun simctl io <udid> recordVideo`. A copy is at `/workspace/vosim/demo.mp4`.

## Talk track

| t | On screen | Say |
|---|---|---|
| 0:00 | Crossroads, board, Now card | **Problem.** AI "doctors" now take histories and draft plans at scale. The failure mode isn't the model's medicine; it's the *information*: what the patient didn't say, said wrong, or said differently on purpose. |
| 0:25 | Now card, why-queued chips | **HITM.** One physician supervises many AI encounters. Each AI decision arrives as a card with a proposal, confidence, what happens next, and *why it was queued*. Confident, clean items auto-pass, and a sample goes to spot-check. |
| 0:45 | **Step 1/6** PDE5 request, Reliability panel | **4 reliability states** per field: Reliable / Not said / Said wrong / Said differently on purpose. Here he denied nitrates, but the pharmacy record shows isosorbide, and his partner is present → *Said differently on purpose*. **If-wrong**: PDE5 + nitrate → profound hypotension, a hard stop. |
| 1:15 | Ask-next → answer | **VOI.** The engine ranks questions by expected-loss reduction (true value of information), not curiosity. We send the top question privately; he discloses isosorbide + poppers. The card flips to **HARD STOP → decline**. |
| 1:45 | **Step 2/6** sore throat wants azithro | Centor is low, and the hidden problem is a med: methadone from a clinic (record mismatch). Macrolide + methadone → QT/torsades. Decision: **with conditions** (no macrolide/FQ; amoxicillin or none). |
| 2:10 | **Step 3/6** GLP-1 | "My mom had some thyroid thing." A hedge is a signal in the Bayesian network. Asking reveals medullary thyroid cancer → **decline** GLP-1. Counselling card: cost/coverage, compounded products, GI effects, lean-mass loss, regain on stopping. |
| 2:35 | **Step 4/6** testosterone | Fertility was **never asked** (Not said). Asking reveals he's trying to conceive; TRT suppresses spermatogenesis → **decline/refer**. |
| 2:55 | **Step 5/6** red banner | **Escalation.** Exertional chest pain is a *hard trigger*: it bypasses reliability analysis, pages the Alert Team, and the physician only acknowledges. Separately, the BN recommends escalation when P(critical miss) exceeds a threshold and no single question can rule it out. |
| 3:15 | **Step 6/6** auto-pass, spot-check | A clean refill with all key fields reliable auto-passes; a sample is queued for spot-check. Supervision effort goes where the risk is. |
| 3:30 | Board / export | **Data flywheel.** Every decision, re-rating (R/N/W/D), question asked, answer, and dwell time is logged → `tools/to_training.py` turns it into training/eval data, so the AI learns which questions it should have asked. |
| 3:50 | Domain config | **Domain-agnostic.** The same router runs ED triage and AI-doc review from JSON configs plus a domain module; the risk engine is a sidecar with editable YAML parameters (each with a source label: placeholder / expert / literature). |
| 4:10 | — | Close: *"The AI does the volume; the physician supervises the uncertainty."* |

## What each step demonstrates

1. **Hidden nitrate (PDE5)**: Said differently on purpose → if-wrong hard stop → ask-next reveals → decline.
2. **Azithro + hidden methadone**: record-mismatch signal → QT flag → with conditions.
3. **GLP-1 + family MTC omission**: hedge signal → ask → decline + limitations card.
4. **Testosterone + fertility wish**: Not said → ask → decline/refer.
5. **Exertional chest pain**: hard trigger, analysis bypassed, acknowledge.
6. **Clean refill**: auto-pass and spot-check sample.

In demo mode, asked questions always reveal the hidden truth, so the run is deterministic. In normal mode, reveal is probabilistic.

## If something goes wrong
- No BN badge: run `curl localhost:8765/health`, then restart with `risk_engine/run_sidecar.sh`. The fallback is still a coherent demo.
- Wrong state: press **Reset demo** on the board.
- Live demo impossible: play `screens/demo.mp4`.
