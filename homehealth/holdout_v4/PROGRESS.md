# holdout_v4 (SYNTHETIC) — SMART_TRIGGERS v1.11.2, params 0.11.2-placeholder, seed 20261023
Pipeline = holdout_v3 (GEN_LLM2_v2.3 + hard slice, GRADER_LLM3_v1.3 / gemini-4-argon, grade_merge) + ADDENDUM_v1112.md; batches HX1..HX8 (specs_v4.py; new author prompts varying wording, settings, patient types). Generated on the box (/workspace/jevfly_smoke/holdout_v4), Jev + scoring on the Mac.
Resume generation: `nohup python3 run_holdout_v4.py --seq >> run.out 2>&1 &` (state.json checkpoints; done gen/grade files skipped).
## Status
1. [x] Generation: 82 cases (HX1-HX7 11 each; HX8 5 — deepseek-v4-pro via provider Baidu returned corrupted JSON (typos like `fals`, `Q.:0`) on 3 tries for part 1, part 2 ok). First parallel run stalled on 13 read timeouts ($0 reported); rerun with --seq.
2. [x] Grading: 4 grader calls, all 82 graded.
3. [x] Finalize: 68 accepted by merge, 9 merge disputes, 5 on fix list. Script fix: HX4 router_input boilerplate "no artifact flags" tripped the grade_merge banned word (all 11 HX4 cases) -> reworded to "device-quality flags" (orig kept as gen/HX4.batch.orig.json; no label/clinical fact changed). Story-level dedupe fixed to exempt designed near-miss pair partners (same pair_id). Dedupe removed 1 (HX4-008: story match to HX4-004 on 'in full sentences at rest'). 67 accepted final. Converter: Mac casegen/convert_casegen.py (v1.9 route ids).
   Spend after generation+grading: $1.635.
4. [x] FREEZE: accepted cases + generation metadata committed before any scoring (md5 in FREEZE_md5.txt).
