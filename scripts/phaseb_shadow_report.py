"""Print an offline Phase B actual-vs-shadow evidence report as JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from praxiom.telemetry.phaseb_report import build_phaseb_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=None)
    parser.add_argument("--run-id", action="append", dest="run_ids", default=None)
    args = parser.parse_args()
    report = build_phaseb_report(state_root=args.state_root, run_ids=args.run_ids)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
