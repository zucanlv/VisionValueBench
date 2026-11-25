#!/usr/bin/env python3
"""Reference SAE/IAE evaluation runner.

Prepare only:      python evaluation/run_eval.py --manifest ... --out runs/demo
Offline smoke test: python evaluation/run_eval.py --manifest ... --out runs/demo --mock
Real model calls:   python evaluation/run_eval.py --manifest ... --out runs/demo --config ... --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vvb_eval.runner import MOCK_CONFIG, Runner, StageError, load_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, required=True, help="JSONL rows: sample_id, scenario, image")
    parser.add_argument("--out", type=Path, required=True, help="Run directory")
    parser.add_argument("--config", type=Path, help="Model configuration JSON (required with --execute)")
    parser.add_argument("--mock", action="store_true", help="Run the full pipeline with deterministic mock responses")
    parser.add_argument("--execute", action="store_true", help="Call the configured OpenAI-compatible endpoints")
    parser.add_argument("--workers", type=int, help="Concurrent calls (default: config.workers or 8)")
    parser.add_argument(
        "--max-calls",
        type=int,
        default=200,
        help="Safety cap on attempted model calls (default: 200; raise deliberately for full runs)",
    )
    parser.add_argument("--limit", type=int, help="Use only the first N manifest rows")
    parser.add_argument("--retry-failed", action="store_true", help="Re-run cached invalid calls")
    parser.add_argument("--no-resume", action="store_true", help="Ignore cached valid records")
    args = parser.parse_args()

    if args.mock and args.execute:
        parser.error("--mock and --execute are mutually exclusive")
    if args.execute and args.config is None:
        parser.error("--execute requires --config")

    if args.mock:
        mode = "mock"
        config = load_config(args.config) if args.config else json.loads(json.dumps(MOCK_CONFIG))
    elif args.execute:
        mode = "execute"
        config = load_config(args.config)
    else:
        mode = "prepare"
        config = load_config(args.config) if args.config else json.loads(json.dumps(MOCK_CONFIG))

    try:
        runner = Runner(
            manifest=args.manifest,
            out=args.out,
            config=config,
            mock=args.mock,
            workers=args.workers,
            max_calls=args.max_calls,
            retry_failed=args.retry_failed,
            resume=not args.no_resume,
            limit=args.limit,
        )
        status = runner.run(mode)
    except (StageError, ValueError, FileNotFoundError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print(json.dumps(status, ensure_ascii=False, indent=2))
    if mode == "prepare":
        return 0
    return 0 if status.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())