#!/usr/bin/env python3
"""Rewrite the bundled home-health vignette pack from the synthetic library + Layer 1.

From the repo root:
  python3 homehealth/sdr_bridge/export_vignettes.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decide import PACK_PATH, build_pack, dumps  # noqa: E402


def main() -> None:
    PACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    PACK_PATH.write_text(dumps(build_pack()))
    print(f"wrote {PACK_PATH}")


if __name__ == "__main__":
    main()
