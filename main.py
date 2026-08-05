"""CLI entrypoint. Usage:

    python main.py --dry-run          # deterministic engine + schema only, no Groq calls
    python main.py                    # full run against Groq for all 50 cases
    python main.py --case-ids EC_001,EC_012   # run a subset
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DATA_DIR, INPUT_DIR, METADATA_PATH, OUTPUT_DIR, TRACE_PATH
from src.runner import run_all


def main() -> int:
    parser = argparse.ArgumentParser(description="EC_POLICY_V2 multi-agent case runner")
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--trace-path", type=Path, default=TRACE_PATH)
    parser.add_argument("--metadata-path", type=Path, default=METADATA_PATH)
    parser.add_argument("--case-ids", type=str, default=None, help="Comma-separated case IDs, e.g. EC_001,EC_012")
    parser.add_argument("--dry-run", action="store_true", help="Skip Groq calls; deterministic engine + schema only")
    args = parser.parse_args()

    case_ids = args.case_ids.split(",") if args.case_ids else None

    return run_all(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        data_dir=args.data_dir,
        trace_path=args.trace_path,
        metadata_path=args.metadata_path,
        case_ids=case_ids,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
