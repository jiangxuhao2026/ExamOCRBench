from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from examocrbench.io import read_jsonl, write_json
from examocrbench.api_client import ApiClient, image_data_uri
from examocrbench.runner import prompt_for
from examocrbench.metrics import (
    evaluate_task1,
    evaluate_task2,
    evaluate_task3,
    evaluate_task4,
    norm_text,
    normalize_task4_text,
)


def test_text_normalization_policies() -> None:
    assert norm_text("题干{答题区域1}{配图区域2}{表格区域3}") == "题干"
    assert norm_text(r"$\left\{ x \right.$") == r"$\{x.$"
    assert normalize_task4_text(r"$$\dfrac{1}{2} × x$$", "formula") == r"\frac{1}{2}\timesx"
    assert normalize_task4_text(r"\(A ÷ B\)", "formula") == r"a\divb"


def test_transport_compatibility() -> None:
    image = ROOT / "examples/demo/task1/images/demo_task1_001.jpg"
    image_uri = image_data_uri(image, target_long_edge=1800)
    assert image_uri.startswith("data:image/jpeg;base64,")

    chat_payload, chat_headers = ApiClient(
        "https://example.invalid", "key", protocol="chat",
        chat_json_mode=True, chat_thinking_disabled=True,
    )._payload("qwen3.8-max", "prompt", image_uri, 10)
    assert chat_headers["Authorization"] == "Bearer key"
    assert chat_payload["response_format"] == {"type": "json_object"}
    assert chat_payload["thinking"] == {"type": "disabled"}

    responses_payload, _ = ApiClient(
        "https://example.invalid", "key", protocol="responses",
    )._payload("gpt-5.6-sol", "prompt", image_uri, 10)
    assert responses_payload["input"][0]["content"][1]["detail"] == "high"

    anthropic_payload, anthropic_headers = ApiClient(
        "https://example.invalid", "key", protocol="anthropic",
    )._payload("claude-opus-5", "prompt", image_uri, 10)
    assert anthropic_headers["x-api-key"] == "key"
    assert anthropic_payload["messages"][0]["content"][0]["type"] == "image"

    bearer_payload, bearer_headers = ApiClient(
        "https://example.invalid", "key", protocol="anthropic_bearer",
    )._payload("doubao-seed-2-1-pro-260628", "prompt", image_uri, 10)
    assert bearer_headers["Authorization"] == "Bearer key"
    assert "x-api-key" not in bearer_headers


def test_public_prompt_projection_hides_internal_metadata() -> None:
    row = {
        "schema_version": "examocrbench_task1_public_input_v1",
        "sample_id": "demo_task1_001",
        "record_id": "internal-record-id",
        "image": "images/demo_task1_001.jpg",
        "subject": "语文",
        "student_answers_visible": True,
        "questions": [{"question_key": "Q001", "answer_units": [{"unit_key": "U001", "answer_type": "objective", "max_points": 1}]}],
    }
    schema = {"type": "object"}
    prompt = prompt_for("task1", ROOT / "prompts/task1.md", row, schema)
    assert "internal-record-id" not in prompt
    assert '"questions"' in prompt
    assert "Q001" in prompt


def test_demo_inputs_and_images() -> None:
    demo = ROOT / "examples/demo"
    for task, name in (("task1", "input.jsonl"), ("task2", "input.jsonl"), ("task3", "queries.jsonl"), ("task4", "input.jsonl")):
        rows = read_jsonl(demo / task / name)
        assert rows
        for row in rows:
            image = demo / task / row["image"]
            assert image.is_file(), image


def test_perfect_predictions_score_one() -> None:
    demo = ROOT / "examples/demo"
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for task in ("task1", "task2", "task3", "task4"):
            target = root / task / "model"
            target.mkdir(parents=True)
            for gt in read_jsonl(demo / task / "ground_truth.jsonl"):
                if task == "task1":
                    prediction = {
                        "schema_version": "examocrbench_task1_public_output_v1",
                        "sample_id": gt["sample_id"],
                        "grading_units": [],
                    }
                    for unit in gt["grading_units"]:
                        if unit.get("gt_route") == "not_answerable_safety":
                            prediction["grading_units"].append({
                                "question_key": unit["question_key"], "unit_key": unit["unit_key"],
                                "evaluable": False, "grading_status": "not_evaluable",
                                "awarded_score": None, "reference_answer": None,
                                "judgement_reason": "test",
                            })
                        else:
                            answer = (unit.get("reference_answers") or [""])[0]
                            prediction["grading_units"].append({
                                "question_key": unit["question_key"], "unit_key": unit["unit_key"],
                                "observed_answer": answer, "evaluable": True,
                                "grading_status": "graded", "awarded_score": unit["gt_awarded_score"],
                                "reference_answer": answer, "judgement_reason": "test",
                            })
                    key = gt["sample_id"]
                elif task == "task2":
                    prediction = {"schema_version": "examocrbench_task2_public_output_v1", "sample_id": gt["sample_id"], "coordinate_system": "normalized_1000", "elements": gt["elements"]}
                    key = gt["sample_id"]
                elif task == "task3":
                    prediction = {"schema_version": "examocrbench_task3_public_output_v1", "sample_id": gt["sample_id"], "query_id": gt["query_id"], "found": True, "bbox": gt["bbox"], "confidence": 1.0}
                    key = gt["query_id"]
                else:
                    prediction = {"sample_id": gt["sample_id"], "prediction_text": gt["gt_text"]}
                    key = gt["sample_id"]
                write_json(target / f"{key}.json", {"sample_id": gt["sample_id"], "query_id": gt.get("query_id"), "status": "success", "prediction_json": prediction, "prediction_text": prediction.get("prediction_text", "")})
        task1 = evaluate_task1(root / "task1/model", demo / "task1/ground_truth.jsonl", root / "task1.json")
        assert task1["page_accuracy"] == 1.0
        assert task1["PageScoreAccuracy"] == 1.0
        assert "SafetyUnitRecall" in task1
        assert task1["safety_unit_compliance_rate"] in (None, 1.0)
        task2_metrics = evaluate_task2(root / "task2/model", demo / "task2/ground_truth.jsonl", root / "task2.json")
        assert task2_metrics["mean_teds"] == 1.0
        assert "map_at_0_5" in task2_metrics
        assert "TEDS" in task2_metrics and "mAP@0.5" in task2_metrics
        task3_metrics = evaluate_task3(root / "task3/model", demo / "task3/ground_truth.jsonl", root / "task3.json")
        assert task3_metrics["accuracy_at_0_5_macro"] == 1.0
        assert task3_metrics["four_type_macro_hit_at_0_5"] is None
        assert "Macro Accuracy" in task3_metrics
        assert task3_metrics["by_target_type"]["HandwrittenAnswer"]["hit_at_0_5"] == 1.0
        task4 = evaluate_task4(root / "task4/model", demo / "task4/ground_truth.jsonl", root / "task4.json")
        assert task4["mean_cer"] == 0.0 and task4["exact_match"] == 1.0
        assert task4["CER"] == 0.0 and task4["ExactMatch"] == 1.0
