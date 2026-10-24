# library_expansion_v2 (SYNTHETIC device-fault library batch) — SMART_TRIGGERS v1.13 + ADDENDUM_v113 device tickets, params 0.13.0-placeholder, seed 20261025
Pipeline = library_expansion_v1 (GEN_LLM2_v2.3 + hard slice, GRADER_LLM3_v1.3 / gemini-4-argon, grade_merge, story dedupe) + ADDENDUM_v113 (device-ticket rules). Run on the box (jevfly_smoke), outputs copied here.
- DO_NOT_REPEAT = library_v2 + holdout_v1/v2 + library_expansion_v1. holdout_v3/v4 never entered any prompt and were NOT used in the dedupe either.
- Batches (specs_lx2.py): LX9 data pipeline (sync, battery, firmware, duplicate/time shift), LX10 fit/placement/cuff/SpO2 disagreement, LX11 scale + CGM, LX12 near-miss pairs (fault vs confirmed real; ticket-only vs ticket on clinical).
## Round log
1. run_lx2.py: LX9, LX10 generated (haiku-5.5; LX10 try1 timed out); 22-case grade call timed out twice; deepseek LX11 gen timed out. Run interrupted twice.
2. run_lx2b.py (resume, nothing regenerated): grader in chunks of <= 6 cases; LX11, LX12 generated with haiku-5.5 instead of deepseek-v4-pro. All graded.
3. ticket_grade.py: the v1.3 grader has no ticket field, so a blind ticket pass with the same grader model (case facts only, ADDENDUM_v113 rules).
4. finalize_lx2.py: auto-accept only where author and grader agree on route AND ticket. 43 generated, 31 accepted, 12 in merge_disputes.csv for Wayne (3 route/novelty, 9 ticket), 0 dedupe removed.
Spend: spend.json ($1.157 reported by OpenRouter; 3 timed-out calls reported no cost).
