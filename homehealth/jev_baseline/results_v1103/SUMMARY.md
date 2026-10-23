# SMART_TRIGGERS v1.10.3 (params 0.10.3-placeholder): HT_FOCAL_NEURO lay wording. Stored picks, 0 model calls (SYNTHETIC)
Synonyms added (practice cases in test_layer1_v1103.py, 14 tests incl. 4 must-stay-quiet: tremor, arthritis, sleepy mumbling, negated).
Before (v1.10.2) -> after (v1.10.3): library 270 and holdout_v1 ruled 91 identical on all systems (0 Layer 1 decision changes; default crit 0, FP/100 2.96 / 2.20).
holdout_v2 ruled: 65-case metrics identical (default 96.9%, crit 0, FP/100 3.08, HITM/100 9.23). Layer 1 alone all 81: 40 -> 41 decided, 97.5% -> 97.6%, crit 0, FP 0.
Only change: HV2-002 (disputed, no picks) no trigger -> HT_FOCAL_NEURO SUPPRESSED goals_of_care -> nurse_task (matches ruling). Caveat: holdout_v2 is partly tuning data.
