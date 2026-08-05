"""Runs the full pipeline across all (or a subset of) input/EC_0NN.json
cases. Each case is isolated in its own try/except: one bad case never
blocks the other 49, and the runner always writes exactly one output file
per input file it attempts.
"""
from __future__ import annotations

import json
import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from src.agents.coordinator import Coordinator, build_minimal_fallback_output
from src.config import (
    DATA_DIR,
    GROQ_BASE_URL,
    GROQ_MODEL,
    GROQ_MODEL_PARAM_SIZE,
    INPUT_DIR,
    METADATA_PATH,
    OUTPUT_DIR,
    POLICY_VERSION,
    TRACE_PATH,
)
from src.data.loader import load_data_store
from src.llm.groq_client import GroqClient
from src.schemas.input_models import InputCase
from src.tracing.trace_logger import TraceLogger

AGENTS_METADATA = [
    {"name": "order_product_agent", "uses_llm": True},
    {"name": "customer_agent", "uses_llm": True},
    {"name": "payment_agent", "uses_llm": True},
    {"name": "delivery_agent", "uses_llm": True},
    {"name": "policy_agent", "uses_llm": True},
    {"name": "verifier_agent", "uses_llm": True},
    {"name": "coordinator", "uses_llm": False},
]


def run_all(
    input_dir: Path = INPUT_DIR,
    output_dir: Path = OUTPUT_DIR,
    data_dir: Path = DATA_DIR,
    trace_path: Path = TRACE_PATH,
    metadata_path: Path = METADATA_PATH,
    case_ids: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    print(f"Loading data store from {data_dir} ...")
    ds = load_data_store(data_dir)
    print(f"Loaded {len(ds.orders)} orders in {time.monotonic() - t0:.2f}s")

    llm = GroqClient(force_unavailable=dry_run)
    if not dry_run and not llm.available:
        print("ERROR: GROQ_API_KEY not set and --dry-run not requested. Aborting before any case runs.")
        return 1

    coordinator = Coordinator(ds, llm)
    trace = TraceLogger(trace_path)
    trace.run_start(
        run_started_at=run_started_at, dry_run=dry_run, model=GROQ_MODEL, policy_version=POLICY_VERSION
    )

    input_files = sorted(input_dir.glob("EC_*.json"))
    if case_ids:
        wanted = set(case_ids)
        input_files = [f for f in input_files if f.stem in wanted]

    succeeded = 0
    failed: list[str] = []
    confidences: list[float] = []

    for input_file in input_files:
        case_id = input_file.stem
        try:
            raw = json.loads(input_file.read_text(encoding="utf-8"))
            case = InputCase.model_validate(raw)
            output = coordinator.run_case(case, trace)
        except Exception as exc:  # noqa: BLE001 - a single bad case must not stop the run
            tb = traceback.format_exc(limit=6)
            trace.case_failed(case_id, error=str(exc), traceback=tb)
            claimed_order_id = None
            try:
                claimed_order_id = raw.get("customer_request", {}).get("claimed_order_id")  # type: ignore[possibly-undefined]
            except Exception:  # noqa: BLE001
                pass
            output = build_minimal_fallback_output(case_id, claimed_order_id)
            failed.append(case_id)

        output_path = output_dir / f"{case_id}.json"
        output_path.write_text(
            json.dumps(output.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        confidences.append(output.case_assessment.confidence)
        succeeded += 1

    duration_s = round(time.monotonic() - t0, 2)
    mean_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

    trace.run_end(
        total_cases=len(input_files),
        succeeded=len(input_files) - len(failed),
        failed=len(failed),
        failed_case_ids=failed,
        duration_s=duration_s,
        mean_confidence=mean_confidence,
    )
    trace.close()

    _write_metadata(
        metadata_path,
        run_started_at=run_started_at,
        total_cases=len(input_files),
        succeeded=len(input_files) - len(failed),
        failed=len(failed),
        duration_s=duration_s,
        mean_confidence=mean_confidence,
        dry_run=dry_run,
    )

    print(f"\nDone in {duration_s}s. {len(input_files) - len(failed)}/{len(input_files)} succeeded.")
    if failed:
        print(f"Failed cases (fallback output written): {failed}")
    print(f"Mean confidence: {mean_confidence}")
    print("Policy edge cases (if any) are logged per-case in trace.jsonl as policy_edge_case=true.")

    output_files = sorted(output_dir.glob("EC_*.json"))
    if len(output_files) != 50:
        print(f"WARNING: expected 50 output files, found {len(output_files)}.")
        return 1
    return 0


def _write_metadata(
    metadata_path: Path,
    run_started_at: str,
    total_cases: int,
    succeeded: int,
    failed: int,
    duration_s: float,
    mean_confidence: float,
    dry_run: bool,
) -> None:
    metadata = {
        "run": {
            "run_id": run_started_at,
            "started_at": run_started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": duration_s,
            "total_cases": total_cases,
            "succeeded": succeeded,
            "failed": failed,
            "mean_confidence": mean_confidence,
            "dry_run": dry_run,
            "os": platform.platform(),
            "python_version": sys.version.split()[0],
        },
        "agents": [
            {
                **agent,
                "model_name": GROQ_MODEL if agent["uses_llm"] else None,
                "provider": "groq" if agent["uses_llm"] else None,
                "parameter_size": GROQ_MODEL_PARAM_SIZE if agent["uses_llm"] else None,
                "endpoint": f"{GROQ_BASE_URL}/chat/completions" if agent["uses_llm"] else None,
            }
            for agent in AGENTS_METADATA
        ],
        "frameworks": {
            "language": f"Python {sys.version.split()[0]}",
            "llm_sdk": "openai (SDK) -> Groq OpenAI-compatible endpoint",
            "data": "pandas",
            "validation": "pydantic v2",
            "orchestration": "custom lightweight orchestrator (no LangGraph/CrewAI)",
        },
        "policy_version": POLICY_VERSION,
        "dataset": "Olist Brazilian E-Commerce Public Dataset (Kaggle olistbr/brazilian-ecommerce)",
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
