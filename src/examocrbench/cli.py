from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - requirements.txt installs jsonschema
    Draft202012Validator = None  # type: ignore[assignment,misc]

from .io import read_json, read_jsonl, write_json
from .metrics import evaluate_task1, evaluate_task2, evaluate_task3, evaluate_task4
from .runner import run_task


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description="ExamOCRBench public inference and offline evaluation CLI")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one task against a model API")
    run.add_argument("--task", required=True, choices=("task1", "task2", "task3", "task4"))
    run.add_argument("--input", required=True)
    run.add_argument("--output-dir", default="results")
    run.add_argument("--model", required=True)
    run.add_argument("--api-url", default=os.environ.get("EXAMOCRBENCH_API_URL", ""))
    run.add_argument("--api-key", default=os.environ.get("EXAMOCRBENCH_API_KEY", ""))
    run.add_argument("--protocol", choices=("chat", "responses", "anthropic", "anthropic_bearer"), default="chat")
    run.add_argument("--api-key-file", default="")
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--retries", type=int, default=3)
    run.add_argument("--timeout", type=float, default=900)
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--max-tokens", type=int, default=0)
    run.add_argument("--format-retries", type=int, default=1)
    run.add_argument("--target-long-edge", type=int, default=0)
    run.add_argument("--per-unit-output-tokens", type=int, default=120)
    run.add_argument("--max-request-tokens", type=int, default=8192)
    run.add_argument("--chat-json-mode", action="store_true")
    run.add_argument("--chat-thinking-disabled", action="store_true")
    run.add_argument("--claude-protocol", choices=("anthropic", "anthropic_bearer"), default="anthropic")
    run.add_argument("--overwrite", action="store_true")
    ev = sub.add_parser("evaluate", help="evaluate model results offline")
    ev.add_argument("--task", required=True, choices=("task1", "task2", "task3", "task4"))
    ev.add_argument("--prediction", required=True)
    ev.add_argument("--ground-truth", required=True)
    ev.add_argument("--output", required=True)
    val = sub.add_parser("validate", help="validate task input and optional GT files")
    val.add_argument("--task", required=True, choices=("task1", "task2", "task3", "task4"))
    val.add_argument("--input", required=True)
    val.add_argument("--ground-truth", default="")
    return p


def main() -> int:
    args = parser().parse_args()
    project_root = Path(__file__).resolve().parents[2]
    if args.command == "run":
        if args.api_key_file and not args.api_key:
            import re
            match = re.search(
                r"Authorization\s*:\s*Bearer\s+([^\s\"'\\]+)",
                Path(args.api_key_file).expanduser().read_text(encoding="utf-8-sig"),
                flags=re.I,
            )
            args.api_key = match.group(1) if match else ""
        if not args.api_url or not args.api_key:
            raise SystemExit("run requires --api-url and --api-key, or EXAMOCRBENCH_API_URL/EXAMOCRBENCH_API_KEY")
        run_task(
            args.task, Path(args.input).resolve(), Path(args.output_dir).resolve(), project_root,
            args.model, args.api_url, args.api_key, args.protocol, args.workers, args.retries,
            args.timeout, args.limit, args.overwrite, args.max_tokens or None,
            args.format_retries, args.target_long_edge, args.chat_json_mode,
            args.chat_thinking_disabled, args.per_unit_output_tokens, args.max_request_tokens,
        )
        return 0
    if args.command == "evaluate":
        prediction = Path(args.prediction).resolve(); gt = Path(args.ground_truth).resolve(); output = Path(args.output).resolve()
        if args.task == "task1": evaluate_task1(prediction, gt, output)
        elif args.task == "task2": evaluate_task2(prediction, gt, output)
        elif args.task == "task3": evaluate_task3(prediction, gt, output)
        else: evaluate_task4(prediction, gt, output)
        print(output)
        return 0
    input_path = Path(args.input).resolve()
    rows = read_jsonl(input_path)
    if not rows:
        raise SystemExit("input is empty")
    id_field = "query_id" if args.task == "task3" else "sample_id"
    ids = [row.get(id_field) for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate sample/query IDs")
    if args.ground_truth:
        gt_rows = read_jsonl(Path(args.ground_truth).resolve())
        gt_ids = [row.get(id_field) for row in gt_rows]
        if set(ids) != set(gt_ids):
            raise SystemExit("input and ground-truth IDs do not match")
    schema_path = project_root / "schemas" / f"{args.task}_input.schema.json"
    if schema_path.is_file() and Draft202012Validator is not None:
        schema = read_json(schema_path)
        errors = []
        for index, row in enumerate(rows):
            errors.extend(f"{index}: {error.message}" for error in Draft202012Validator(schema).iter_errors(row))
        if errors:
            raise SystemExit("input schema errors:\n" + "\n".join(errors[:20]))
    elif schema_path.is_file():
        print("warning: jsonschema is not installed; only ID/path checks were applied")
    print({"task": args.task, "count": len(rows), "valid": True})
    return 0
