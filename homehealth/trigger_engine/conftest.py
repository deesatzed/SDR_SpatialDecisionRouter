"""Make the homehealth trigger-engine tests runnable from the repo root: `python -m pytest -q homehealth/trigger_engine`."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "casegen"))   # grade_merge.py
os.chdir(HERE)   # the tests load trigger_params.json relative to this folder
