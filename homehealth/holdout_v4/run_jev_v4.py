"""holdout_v4 Jev run (SYNTHETIC): prompt v1.10, base variant, zero tuning. Models: liquid/d1-ultra, perplexity/pplx-decider-v1.2 (default dual) and
challenger nace-ai/drex-max (called as in sidebar_models/run_sidebar.py). Resumes from jev/parsed checkpoints; HTTP 402 stops everything.
Key loaded from .env in code, never printed. SPEND_CAP $0.30 (holdout_v4 total cap $2.50; generation+grading $1.635)."""
import os, sys, urllib.error
HH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for l in open(os.path.join(HH, "..", "SpatialDecisionRouter", ".env")):
    if l.startswith("OPENROUTER_API_KEY="): os.environ["OPENROUTER_API_KEY"] = l.split("=", 1)[1].strip().strip("\"'")
os.environ.update(JEV_OUT=os.path.join(HH, "holdout_v4", "jev"), JEV_PROMPT="v1.10", VARIANTS="base", SPEND_CAP="0.30", WORKERS="3",
                  RUNNER_JSON=os.path.join(HH, "holdout_v4", "holdout_v4_runner.json"), CASES_JSON=os.path.join(HH, "holdout_v4", "holdout_v4_accepted.json"))
sys.path.insert(0, os.path.join(HH, "jev_baseline")); import jev_run as J
_post = J.post
def post(b, key):
    if J.STOP.is_set(): raise RuntimeError("stopped")
    try: return _post(b, key)
    except urllib.error.HTTPError as e:
        if e.code == 402: J.STOP.set(); J.log(f"HTTP 402 on {b['model']}: STOP")
        raise
J.post = post
sys.argv = [sys.argv[0]] + (sys.argv[1:] or ["liquid/d1-ultra", "perplexity/pplx-decider-v1.2", "nace-ai/drex-max"])
J.main()
