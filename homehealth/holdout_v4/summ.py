"""Render a SUMMARY table from a score_ruled.py output. Usage: python3 summ.py <summary.json>  -> markdown on stdout."""
import json, sys
o = json.load(open(sys.argv[1])); t = o["device_tickets"]
print("| System | Accuracy (decided/n) | Critical misses | False pages /100 | HITM /100 | Errors |\n|---|---|---|---|---|---|")
for s, m in o["systems"].items():
    print(f'| {s} | {100*m["accuracy"]:.1f}% ({m["decided"]}/{m["n"]}) | {m["critical_misses"]} {" ".join(m["critical_ids"])} | {m["false_pages_per_100"]:.2f} ({", ".join(m["false_page_ids"]) or "-"}) | {m["hitm_per_100"]:.2f} | {m["n_errors"]} |')
print(f'\nDevice tickets (Layer 1): {t["hit"]}/{t["expected"]} expected hit, {t["any_ticket"]} with any ticket; missed {", ".join(t["missed_ids"]) or "-"}; unexpected {", ".join(t["unexpected_ids"]) or "-"}.')
d = o["systems"]["L1 + dual(d1-ultra, pplx) [default]"]["errors"]
print("\nDefault-stack errors: " + "; ".join(f'{e["case"]} {e["label"]}->{e["picked"]} (L1 {e["l1"]}/{e["l1_reason"]})' for e in d))
