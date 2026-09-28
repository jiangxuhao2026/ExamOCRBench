from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .api_client import ApiClient, ApiError
from .io import parse_json_text, read_json, read_jsonl, write_json


TASK_DEFAULTS = {
    "task1": ("prompts/task1.md", "schemas/task1_output.schema.json", 2048, 1800),
    "task2": ("prompts/task2.md", "schemas/task2_output.schema.json", 20000, 2048),
    "task3": ("prompts/task3.md", "schemas/task3_output.schema.json", 512, 2048),
    "task4": ("prompts/task4.md", "", 4096, 2048),
}


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value).strip("_") or "model"


def prompt_input(task: str, row: dict[str, Any]) -> dict[str, Any]:
    """Project public input to the V4.3 model-visible prompt payload."""
    if task == "task1":
        return {
            "questions": row.get("questions", []),
            "schema_version": "examocrbench_task1_public_input_v1",
            "student_answers_visible": bool(row.get("student_answers_visible", True)),
        }
    if task == "task2":
        return {
            "coordinate_system": row.get("coordinate_system", "normalized_1000"),
            "target_element_types": row.get("target_element_types", []),
        }
    if task == "task3":
        return {
            "query_id": row.get("query_id"),
            "coordinate_system": row.get("coordinate_system", "normalized_1000"),
            "target_type": row.get("target_type"),
            "query": row.get("query"),
        }
    return {}


def prompt_for(task: str, template_path: Path, row: dict[str, Any], schema: dict[str, Any] | None) -> str:
    template = template_path.read_text(encoding="utf-8")
    return template.replace("{{TASK_INPUT}}", json.dumps(prompt_input(task, row), ensure_ascii=False, indent=2)).replace(
        "{{OUTPUT_SCHEMA}}", json.dumps(schema or {}, ensure_ascii=False, indent=2)
    )


def prediction_errors(task: str, row: dict[str, Any], value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["JSON 根节点必须是对象"]
    errors: list[str] = []
    if task == "task1":
        units = value.get("grading_units")
        if not isinstance(units, list):
            return ["grading_units 必须是数组"]
        expected = {
            (str(question.get("question_key")), str(unit.get("unit_key")))
            for question in row.get("questions", [])
            for unit in question.get("answer_units", [])
        }
        actual = {(str(unit.get("question_key")), str(unit.get("unit_key"))) for unit in units}
        if len(actual) != len(units):
            errors.append("grading_units 存在重复 question_key/unit_key")
        if actual != expected:
            errors.append(f"grading_units 必须完整覆盖输入单元，缺失={sorted(expected - actual)}，多出={sorted(actual - expected)}")
        max_points = {
            (str(question.get("question_key")), str(unit.get("unit_key"))): float(unit.get("max_points", 0))
            for question in row.get("questions", [])
            for unit in question.get("answer_units", [])
        }
        for unit in units:
            key = (str(unit.get("question_key")), str(unit.get("unit_key")))
            if unit.get("grading_status") not in {"graded", "not_evaluable"}:
                errors.append(f"{unit.get('question_key')}/{unit.get('unit_key')} grading_status 不合法")
            if unit.get("evaluable") is True and not isinstance(unit.get("awarded_score"), (int, float)):
                errors.append(f"{unit.get('question_key')}/{unit.get('unit_key')} evaluable 与 awarded_score 不一致")
            if unit.get("evaluable") is False and unit.get("awarded_score") is not None:
                errors.append(f"{unit.get('question_key')}/{unit.get('unit_key')} 不可评估单元的 awarded_score 必须为 null")
            score = unit.get("awarded_score")
            if isinstance(score, (int, float)) and not 0 <= float(score) <= max_points.get(key, 0):
                errors.append(f"{unit.get('question_key')}/{unit.get('unit_key')} awarded_score 超出范围")
            if not isinstance(unit.get("judgement_reason"), str) or not unit.get("judgement_reason").strip():
                errors.append(f"{unit.get('question_key')}/{unit.get('unit_key')} judgement_reason 不能为空")
    elif task == "task2":
        elements = value.get("elements")
        if not isinstance(elements, list) or not elements:
            errors.append("elements 必须是非空数组")
        else:
            ids = [str(item.get("element_id") or "") for item in elements if isinstance(item, dict)]
            if len(ids) != len(elements) or not all(ids) or len(set(ids)) != len(ids):
                errors.append("elements 的 element_id 必须存在且唯一")
            if sum(item.get("element_type") == "Page" for item in elements if isinstance(item, dict)) != 1:
                errors.append("elements 必须恰好包含一个 Page")
            for index, item in enumerate(elements):
                if not isinstance(item, dict):
                    errors.append(f"elements[{index}] 必须是对象")
                    continue
                if "type" in item and "element_type" not in item:
                    errors.append(f"elements[{index}] 必须使用 element_type，不能使用 type")
                required = {"element_id", "element_type", "parent_id", "reading_order", "bbox", "text", "content_format", "visible_marker", "explicit_score", "confidence"}
                missing = sorted(required - set(item))
                if missing:
                    errors.append(f"elements[{index}] 缺少字段: {missing}")
    elif task == "task3":
        if not isinstance(value.get("found"), bool):
            errors.append("found 必须是布尔值")
        bbox = value.get("bbox")
        if value.get("found") and not (isinstance(bbox, list) and len(bbox) == 4 and bbox[2] > bbox[0] and bbox[3] > bbox[1]):
            errors.append("found=true 时 bbox 必须是 [x1,y1,x2,y2]")
        if value.get("found") is False and bbox is not None:
            errors.append("found=false 时 bbox 必须为 null")
    return errors


def canonicalize_prediction(task: str, row: dict[str, Any], value: Any) -> Any:
    """Normalize common model aliases while keeping the public output shape."""
    if task != "task2" or not isinstance(value, dict):
        return value
    result = deepcopy(value)
    result["schema_version"] = "examocrbench_task2_public_output_v1"
    result["sample_id"] = str(row.get("sample_id") or "")
    elements = result.get("elements")
    if not isinstance(elements, list):
        return result
    normalized = []
    for element in elements:
        if not isinstance(element, dict):
            normalized.append(element)
            continue
        item = dict(element)
        if "element_type" not in item and "type" in item:
            item["element_type"] = item.pop("type")
        element_type = item.get("element_type")
        text = item.get("text")
        if "parent_id" not in item:
            item["parent_id"] = None
        if "reading_order" not in item:
            item["reading_order"] = 0
        if "text" not in item:
            item["text"] = None
        if "content_format" not in item:
            if element_type in {"Question", "Instruction"} and isinstance(text, str) and text.strip():
                item["content_format"] = "mixed_latex" if "$" in text or "\\" in text else "plain_text"
            else:
                item["content_format"] = "none"
        item.setdefault("visible_marker", None)
        item.setdefault("explicit_score", None)
        item.setdefault("confidence", 1.0)
        allowed = {
            "element_id", "element_type", "parent_id", "reading_order", "bbox",
            "text", "content_format", "visible_marker", "explicit_score", "confidence",
        }
        normalized.append({key: item[key] for key in allowed if key in item})
    result["elements"] = normalized
    return result


def row_id(task: str, row: dict[str, Any]) -> str:
    if task == "task1":
        return str(row["sample_id"])
    if task == "task2":
        return str(row["sample_id"])
    if task == "task3":
        return str(row["query_id"])
    return str(row["sample_id"])


def task1_unit_count(row: dict[str, Any]) -> int:
    return sum(
        len(question.get("answer_units", []))
        for question in row.get("questions", [])
        if isinstance(question, dict)
    )


def run_one(
    task: str,
    row: dict[str, Any],
    input_root: Path,
    prompt_path: Path,
    schema: dict[str, Any] | None,
    client: ApiClient,
    model: str,
    output_path: Path,
    max_tokens: int,
    overwrite: bool,
    format_retries: int,
) -> dict[str, Any]:
    identifier = row_id(task, row)
    if output_path.exists() and not overwrite:
        try:
            old = read_json(output_path)
            if old.get("status") == "success":
                return {"id": identifier, "status": "skipped_existing", "path": str(output_path)}
        except Exception:
            pass
    image_value = row.get("image")
    image_path = (input_root / str(image_value)).resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")
    prompt = prompt_for(task, prompt_path, row, schema)
    started = time.monotonic()
    result: dict[str, Any] = {
        "schema_version": "examocrbench_public_model_run_v1",
        "task": task,
        "sample_id": str(row.get("sample_id") or row.get("record_id") or ""),
        "query_id": row.get("query_id"),
        "model": model,
        "image": str(image_value),
        "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "prompt_file": str(prompt_path),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "status": "failed",
        "prediction_text": "",
        "prediction_json": None,
        "api_response": None,
        "attempts": [],
        "error": None,
    }
    format_errors: list[str] = []
    for format_attempt in range(1, max(0, format_retries) + 2):
        current_prompt = prompt
        if format_errors:
            current_prompt += (
                "\n上一次输出未通过机器校验，请只修正以下问题并重新输出完整结果，"
                "不要添加解释：" + "；".join(format_errors[:12])
            )
            if task == "task2":
                current_prompt += (
                    "\nTask2 字段修正：节点类型字段必须命名为 element_type，不能写 type；"
                    "每个节点必须包含 element_id、element_type、parent_id、reading_order、bbox、"
                    "text、content_format、visible_marker、explicit_score、confidence；"
                    "必须保留且只保留一个 element_type=Page 的节点。"
                )
            elif task == "task1":
                current_prompt += (
                    "\nTask1 输出修正：必须输出完整闭合 JSON；为避免长页截断，"
                    "observed_answer 是可选字段，可以省略，但每个评分单元的必填字段必须完整。"
                )
        try:
            raw, response, attempts = client.call(model, current_prompt, image_path, max_tokens)
            result["prediction_text"] = raw
            result["api_response"] = {"usage": response.get("usage", {}), "id": response.get("id")}
            result["attempts"].extend([{"format_attempt": format_attempt, **item} for item in attempts])
            if task == "task4":
                result["status"] = "success"
                break
            parsed = canonicalize_prediction(task, row, parse_json_text(raw))
            errors = prediction_errors(task, row, parsed)
            if errors:
                format_errors = errors
                result["prediction_json"] = parsed
                result["error"] = "格式校验失败: " + "；".join(errors[:12])
                continue
            result["prediction_json"] = parsed
            result["status"] = "success"
            result["error"] = None
            break
        except Exception as exc:  # noqa: BLE001
            format_errors = [str(exc)]
            result["error"] = str(exc)
            # Transport failures are retried by ApiClient. A format retry would
            # resubmit the same expensive image request without new information.
            if isinstance(exc, ApiError) or format_attempt >= max(0, format_retries) + 1:
                break
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    write_json(output_path, result)
    return {"id": identifier, "status": result["status"], "path": str(output_path)}


def run_task(
    task: str,
    input_path: Path,
    output_root: Path,
    project_root: Path,
    model: str,
    api_url: str,
    api_key: str,
    protocol: str,
    workers: int,
    retries: int,
    timeout: float,
    limit: int,
    overwrite: bool,
    max_tokens: int | None,
    format_retries: int = 1,
    target_long_edge: int | None = None,
    chat_json_mode: bool = False,
    chat_thinking_disabled: bool = False,
    per_unit_output_tokens: int = 120,
    max_request_tokens: int = 8192,
) -> dict[str, Any]:
    if task not in TASK_DEFAULTS:
        raise ValueError(f"unsupported task: {task}")
    prompt_name, schema_name, default_tokens, default_long_edge = TASK_DEFAULTS[task]
    prompt_path = project_root / prompt_name
    schema = read_json(project_root / schema_name) if schema_name else None
    rows = read_jsonl(input_path)
    if limit > 0:
        rows = rows[:limit]
    client = ApiClient(
        api_url,
        api_key,
        protocol=protocol,
        timeout=timeout,
        retries=retries,
        target_long_edge=target_long_edge or default_long_edge,
        chat_json_mode=chat_json_mode,
        chat_thinking_disabled=chat_thinking_disabled,
    )
    model_dir = output_root / task / safe_name(model)
    jobs = []
    for row in rows:
        output_path = model_dir / f"{safe_name(row_id(task, row))}.json"
        jobs.append((row, output_path))
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(
                run_one, task, row, input_path.parent, prompt_path, schema, client, model,
                output_path,
                max_tokens or (
                    min(max_request_tokens, max(default_tokens, task1_unit_count(row) * per_unit_output_tokens))
                    if task == "task1" else default_tokens
                ),
                overwrite,
                format_retries,
            ): row_id(task, row)
            for row, output_path in jobs
        }
        for index, future in enumerate(as_completed(futures), start=1):
            value = future.result()
            results.append(value)
            print(f"[{index}/{len(futures)}] {task}/{model}/{value['id']} -> {value['status']}", flush=True)
    summary = {
        "schema_version": "examocrbench_public_run_summary_v1",
        "task": task,
        "model": model,
        "input": str(input_path),
        "output_root": str(model_dir),
        "total": len(rows),
        "success": sum(item["status"] == "success" for item in results),
        "skipped_existing": sum(item["status"] == "skipped_existing" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "results": sorted(results, key=lambda item: item["id"]),
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_json(model_dir / "run_summary.json", summary)
    return summary
