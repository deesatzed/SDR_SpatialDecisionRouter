# holdout_v4 (SYNTHETIC) — SMART_TRIGGERS v1.11.2, params 0.11.2-placeholder, seed 20261023
Pipeline = holdout_v3 (GEN_LLM2_v2.3 + hard slice, GRADER_LLM3_v1.3 / gemini-4-argon, grade_merge) + ADDENDUM_v1112.md; batches HX1..HX8 (specs_v4.py; new author prompts varying wording, settings, patient types). Generated on the box (/workspace/jevfly_smoke/holdout_v4), Jev + scoring on the Mac.
Resume generation: `nohup python3 run_holdout_v4.py --seq >> run.out 2>&1 &` (state.json checkpoints; done gen/grade files skipped).
## Status
1. [x] Generation: 82 cases (HX1-HX7 11 each; HX8 5 — deepseek-v4-pro via provider Baidu returned corrupted JSON (typos like `fals`, `Q.:0`) on 3 tries for part 1, part 2 ok). First parallel run stalled on 13 read timeouts ($0 reported); rerun with --seq.
2. [x] Grading: 4 grader calls, all 82 graded.
3. [x] Finalize: 68 accepted by merge, 9 merge disputes, 5 on fix list. Script fix: HX4 router_input boilerplate "no artifact flags" tripped the grade_merge banned word (all 11 HX4 cases) -> reworded to "device-quality flags" (orig kept as gen/HX4.batch.orig.json; no label/clinical fact changed). Story-level dedupe fixed to exempt designed near-miss pair partners (same pair_id). Dedupe removed 1 (HX4-008: story match to HX4-004 on 'in full sentences at rest'). 67 accepted final. Converter: Mac casegen/convert_casegen.py (v1.9 route ids).
   Spend after generation+grading: $1.635.
4. [x] FREEZE: accepted cases + generation metadata committed before any scoring (md5 in FREEZE_md5.txt).
5. [x] Jev (run_jev_v4.py, Mac): prompt v1.10, base variant, 67 x 3 models, all rows picked.
6. [x] Scored (score_holdout_v4.py -> results/summary.json), author labels, zero tuning:

| System | Decided | Accuracy | Critical misses | False pages/100 | HITM/100 |
|---|---|---|---|---|---|
| Layer 1 alone | 31/67 | 80.65% | 0 | 4.48 | 56.72 |
| L1 + d1-ultra | 67/67 | 79.1% | 0 | 5.97 | 2.99 |
| L1 + pplx | 67/67 | 80.6% | 0 | 4.48 | 2.99 |
| L1 + dual (cautious_max_hitm), default | 67/67 | 80.6% | 0 | 5.97 | 11.94 |
| L1 + dual(d1-ultra, drex-max), challenger | 67/67 | 80.6% | 0 | 5.97 | 7.46 |

Jev-decided only (36 cases Layer 1 leaves to Jev): default 31/36, d1 30/36, pplx 31/36, d1+drex 31/36.
Device tickets: 0 of 9 expected (Layer 1 device-disagreement detector did not fire on the new wording). Plain reason: 31/31 Layer 1 decisions.
7. [x] review_queue.csv: 34 rows (4 false pages, 5 over-routes, 5 under-triage, 11 Layer 1 trigger misses caught by Jev, 9 merge disputes). 0 critical misses.
