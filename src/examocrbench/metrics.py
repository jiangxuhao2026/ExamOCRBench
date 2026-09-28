from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .io import read_json, read_jsonl, write_json


PUNCTUATION_TRANSLATION = str.maketrans({
    "，": ",", "。": ".", "：": ":", "；": ";", "！": "!", "？": "?",
    "（": "(", "）": ")", "【": "[", "】": "]", "“": '"', "”": '"',
    "‘": "'", "’": "'",
})
ANNOTATION_PLACEHOLDER_RE = re.compile(
    r"\{\s*(?:答题区域|配图区域|表格区域)\s*\d+\s*\}"
)


def prediction_rows(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        return [read_json(item) for item in sorted(path.glob("*.json")) if item.name != "run_summary.json"]
    return read_jsonl(path)


def strip_annotation_placeholders(value: Any) -> str:
    """Remove annotation-only region markers before text comparison."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    return ANNOTATION_PLACEHOLDER_RE.sub("", text)


def strip_math_delimiters(text: str) -> str:
    return (
        text.replace("$$", "")
        .replace("$", "")
        .replace("\\(", "")
        .replace("\\)", "")
        .replace("\\[", "")
        .replace("\\]", "")
    )


def normalize_formula(text: str) -> str:
    """Normalize common LaTeX/Unicode spellings without solving formulas."""
    value = strip_math_delimiters(
        strip_annotation_placeholders(text).translate(PUNCTUATION_TRANSLATION)
    )
    value = value.replace("\\left", "").replace("\\right", "")
    value = value.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    value = value.replace("×", "\\times").replace("✕", "\\times")
    value = value.replace("÷", "\\div")
    value = value.replace("⋅", "\\cdot").replace("·", "\\cdot")
    value = value.replace("……", "\\cdots").replace("…", "\\cdots")
    value = value.replace("−", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"\\(?:text|mathrm|operatorname)\{([^{}]*)\}", r"\1", value)
    value = re.sub(
        r"\{(\\(?:times|div|cdot|cdots|ldots|pm|leq|geq|neq))\}",
        r"\1",
        value,
    )
    return re.sub(r"\s+", "", value).casefold()


def normalize_boolean(text: str) -> str:
    value = re.sub(r"\s+", "", strip_math_delimiters(strip_annotation_placeholders(text))).casefold()
    if value in {"√", "✓", "✔", "\\checkmark", "\\surd", "true", "对", "正确"}:
        return "√"
    if value in {"×", "x", "✕", "✗", "✘", "\\times", "false", "错", "错误"}:
        return "×"
    return value


def norm_text(value: Any, content_type: str = "plain_text") -> str:
    # Task 2 follows its historical TEDS text policy: do not rewrite
    # full-width punctuation, but remove annotation-only region markers.
    text = strip_annotation_placeholders(value)
    text = text.replace("\\left", "").replace("\\right", "")
    if content_type == "formula":
        return normalize_formula(text)
    if content_type == "boolean":
        return normalize_boolean(text)
    return re.sub(r"\s+", "", text).casefold()


def normalize_task4_text(value: Any, content_type: str = "plain_text") -> str:
    """Use the full V4.1 Task 4 comparison normalization policy."""
    text = strip_annotation_placeholders(value).translate(PUNCTUATION_TRANSLATION)
    if content_type == "formula":
        return normalize_formula(text)
    if content_type == "boolean":
        return normalize_boolean(text)
    text = strip_math_delimiters(text)
    return re.sub(r"\s+", "", text).casefold()


def edit_distance(left: str, right: str) -> int:
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for i, char in enumerate(right, 1):
        current = [i]
        for j, other in enumerate(left, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (char != other)))
        previous = current
    return previous[-1]


def bbox_iou(left: Any, right: Any) -> float:
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != 4 or len(right) != 4:
        return 0.0
    try:
        ax1, ay1, ax2, ay2 = map(float, left)
        bx1, by1, bx2, by2 = map(float, right)
    except (TypeError, ValueError):
        return 0.0
    if ax2 <= ax1 or ay2 <= ay1 or bx2 <= bx1 or by2 <= by1:
        return 0.0
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union else 0.0


@dataclass
class Node:
    element: dict[str, Any]
    children: list["Node"] = field(default_factory=list)


def build_tree(elements: list[dict[str, Any]]) -> tuple[Node, str | None]:
    nodes: dict[str, Node] = {}
    for element in elements:
        identifier = str(element.get("element_id") or "")
        if not identifier or identifier in nodes:
            return Node({"element_type": "Root"}), "duplicate_or_missing_element_id"
        nodes[identifier] = Node(element)
    pages = [node for node in nodes.values() if node.element.get("element_type") == "Page"]
    if len(pages) != 1:
        return Node({"element_type": "Root"}), f"page_count_{len(pages)}"
    root = Node({"element_type": "Root"})
    for identifier, node in nodes.items():
        parent_id = node.element.get("parent_id")
        if parent_id is None:
            if node.element.get("element_type") != "Page":
                return root, "non_page_parent_null"
            root.children.append(node)
        elif str(parent_id) not in nodes:
            return root, "missing_parent"
        else:
            nodes[str(parent_id)].children.append(node)
    for node in nodes.values():
        node.children.sort(key=lambda child: (
            int(child.element.get("reading_order", 0)),
            float((child.element.get("bbox") or [0, 0, 0, 0])[1]),
            float((child.element.get("bbox") or [0, 0, 0, 0])[0]),
            str(child.element.get("element_id")),
        ))
    return root, None


def tree_size(node: Node) -> int:
    return 1 + sum(tree_size(child) for child in node.children)


def _postorder(root: Node) -> tuple[list[Node | None], list[int], list[int]]:
    nodes: list[Node | None] = [None]
    leftmost: list[int] = [0]

    def visit(node: Node) -> int:
        child_leftmost = [visit(child) for child in node.children]
        nodes.append(node)
        index = len(nodes) - 1
        leftmost.append(child_leftmost[0] if child_leftmost else index)
        return leftmost[index]

    visit(root)
    latest: dict[int, int] = {}
    for index in range(1, len(nodes)):
        latest[leftmost[index]] = index
    return nodes, leftmost, sorted(latest.values())


def _tree_edit_distance(left_root: Node, right_root: Node) -> float:
    left_nodes, left_lmd, left_keyroots = _postorder(left_root)
    right_nodes, right_lmd, right_keyroots = _postorder(right_root)
    distances = [[0.0] * len(right_nodes) for _ in range(len(left_nodes))]
    for left_keyroot in left_keyroots:
        for right_keyroot in right_keyroots:
            left_start, right_start = left_lmd[left_keyroot], right_lmd[right_keyroot]
            forest = [[0.0] * (right_keyroot - right_start + 2) for _ in range(left_keyroot - left_start + 2)]
            for row in range(1, len(forest)):
                forest[row][0] = forest[row - 1][0] + 1
            for col in range(1, len(forest[0])):
                forest[0][col] = forest[0][col - 1] + 1
            for row in range(1, len(forest)):
                left_index = left_start + row - 1
                for col in range(1, len(forest[0])):
                    right_index = right_start + col - 1
                    delete = forest[row - 1][col] + 1
                    insert = forest[row][col - 1] + 1
                    if left_lmd[left_index] == left_start and right_lmd[right_index] == right_start:
                        substitute = forest[row - 1][col - 1] + _rename_cost(left_nodes[left_index], right_nodes[right_index])
                        forest[row][col] = min(delete, insert, substitute)
                        distances[left_index][right_index] = forest[row][col]
                    else:
                        prefix_row = left_lmd[left_index] - left_start
                        prefix_col = right_lmd[right_index] - right_start
                        forest[row][col] = min(delete, insert, forest[prefix_row][prefix_col] + distances[left_index][right_index])
    return distances[-1][-1]


def _rename_cost(left: Node | None, right: Node | None) -> float:
    if left is None or right is None:
        return 1.0
    left_type = str(left.element.get("element_type") or "")
    right_type = str(right.element.get("element_type") or "")
    if left_type != right_type:
        return 1.0
    if (left.element.get("attributes") or {}).get("text_evaluation_eligible") is False:
        return 0.0
    if left_type not in {"Instruction", "Question"}:
        return 0.0
    target = norm_text(left.element.get("text"))
    predicted = norm_text(right.element.get("text"))
    return min(1.0, edit_distance(target, predicted) / max(1, len(target)))


def filter_excluded_predictions(
    gt_elements: list[dict[str, Any]],
    pred_elements: list[dict[str, Any]],
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    excluded = [
        element for element in gt_elements
        if (element.get("attributes") or {}).get("teds_evaluation_eligible") is False
    ]
    return [
        pred for pred in pred_elements
        if not any(
            pred.get("element_type") == gt.get("element_type")
            and bbox_iou(pred.get("bbox"), gt.get("bbox")) >= threshold
            for gt in excluded
        )
    ]


def teds_score(gt_elements: list[dict[str, Any]], pred_elements: list[dict[str, Any]]) -> tuple[float, str | None]:
    gt_eligible = [
        element for element in gt_elements
        if (element.get("attributes") or {}).get("teds_evaluation_eligible") is not False
    ]
    pred_elements = filter_excluded_predictions(gt_elements, pred_elements)
    gt_tree, gt_error = build_tree(gt_eligible)
    pred_tree, pred_error = build_tree(pred_elements)
    if pred_error:
        return 0.0, pred_error
    distance = _tree_edit_distance(gt_tree, pred_tree)
    denominator = max(1, len(gt_eligible) + 1, len(pred_elements) + 1)
    return max(0.0, 1.0 - distance / denominator), gt_error


def layout_f1(gt: list[dict[str, Any]], pred: list[dict[str, Any]]) -> dict[str, Any]:
    gt_rows = [
        item for item in gt
        if item.get("element_type") != "Page"
        and (item.get("attributes") or {}).get("layout_evaluation_eligible") is not False
    ]
    pred_rows = [
        item for item in filter_excluded_predictions(gt, pred)
        if item.get("element_type") != "Page"
    ]
    pred_rows.sort(key=lambda item: float(item.get("confidence", 1.0)), reverse=True)
    matched: set[int] = set()
    tp = 0
    for item in pred_rows:
        choices = [
            (bbox_iou(item.get("bbox"), target.get("bbox")), index)
            for index, target in enumerate(gt_rows)
            if index not in matched and item.get("element_type") == target.get("element_type")
        ]
        best, index = max(choices, default=(0.0, -1))
        if best >= 0.5:
            matched.add(index)
            tp += 1
    fp, fn = len(pred_rows) - tp, len(gt_rows) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"gt_count": len(gt_rows), "pred_count": len(pred_rows), "tp": tp, "fp": fp, "fn": fn, "precision_at_0_5": precision, "recall_at_0_5": recall, "f1_at_0_5": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def evaluate_task1(prediction_path: Path, gt_path: Path, output_path: Path) -> dict[str, Any]:
    predictions = {str(row.get("sample_id")): row for row in prediction_rows(prediction_path)}
    gt_rows = read_jsonl(gt_path)
    pages = []
    for gt in gt_rows:
        pred = predictions.get(str(gt["sample_id"]), {})
        pred = pred.get("prediction_json") if isinstance(pred.get("prediction_json"), dict) else pred
        pred_units = {(str(item.get("question_key")), str(item.get("unit_key"))): item for item in pred.get("grading_units", [])}
        normal_ok = []
        safety_ok = []
        normal_count = 0
        for unit in gt.get("grading_units", []):
            key = (str(unit["question_key"]), str(unit["unit_key"]))
            value = pred_units.get(key, {})
            if unit.get("gt_route") == "not_answerable_safety":
                safe = value.get("evaluable") is False and value.get("grading_status") == "not_evaluable" and value.get("awarded_score") is None and not str(value.get("reference_answer") or "").strip()
                safety_ok.append(safe)
            else:
                normal_count += 1
                expected_score = float(unit.get("gt_awarded_score", -1))
                score = value.get("awarded_score")
                normal_ok.append(value.get("evaluable") is True and value.get("grading_status") == "graded" and score is not None and float(score) == expected_score)
        pages.append({"sample_id": gt["sample_id"], "correct": bool(normal_ok) and all(normal_ok), "correct_units": sum(normal_ok), "unit_count": len(normal_ok), "normal_unit_count": normal_count, "safety_unit_count": len(safety_ok), "safety_compliant_count": sum(safety_ok)})
    scored_pages = [row for row in pages if row["normal_unit_count"]]
    safety_units = sum(row["safety_unit_count"] for row in pages)
    missing_count = sum(1 for gt in gt_rows if str(gt["sample_id"]) not in predictions)
    run_failure_count = sum(1 for value in predictions.values() if value.get("status") in {"failed", "api_failed", "run_failure"})
    page_accuracy = sum(row["correct"] for row in scored_pages) / max(1, len(scored_pages)) if scored_pages else None
    safety_recall = sum(row["safety_compliant_count"] for row in pages) / max(1, safety_units) if safety_units else None
    summary = {"task": "task1", "page_count": len(pages), "PageScoreAccuracy": page_accuracy, "SafetyUnitRecall": safety_recall, "page_accuracy": page_accuracy, "safety_unit_compliance_rate": safety_recall, "normal_page_count": len(scored_pages), "safety_unit_count": safety_units, "prediction_missing_count": missing_count, "run_failure_count": run_failure_count, "pages": pages}
    write_json(output_path, summary)
    return summary


def evaluate_task2(prediction_dir: Path, gt_path: Path, output_path: Path) -> dict[str, Any]:
    gt_by = {str(row["sample_id"]): row for row in read_jsonl(gt_path)}
    rows = []
    ap_entries: dict[str, list[tuple[float, int]]] = {}
    ap_gt_counts: dict[str, int] = {}
    for path in sorted(prediction_dir.glob("*.json")):
        if path.name == "run_summary.json":
            continue
        result = read_json(path)
        sample_id = str(result.get("sample_id"))
        payload = result.get("prediction_json") if isinstance(result.get("prediction_json"), dict) else result
        pred = (payload or {}).get("elements") or []
        gt = gt_by.get(sample_id, {}).get("elements", [])
        teds, tree_error = teds_score(gt, pred)
        rows.append({"sample_id": sample_id, "teds": teds, "tree_error": tree_error})
        eligible_gt = [e for e in gt if e.get("element_type") != "Page" and (e.get("attributes") or {}).get("layout_evaluation_eligible") is not False]
        pred_for_ap = filter_excluded_predictions(gt, pred)
        for element_type in {e.get("element_type") for e in eligible_gt}:
            gt_items = [e for e in eligible_gt if e.get("element_type") == element_type]
            pred_items = [e for e in pred_for_ap if e.get("element_type") == element_type]
            matched: set[int] = set()
            for item in sorted(pred_items, key=lambda x: float(x.get("confidence", 1.0)), reverse=True):
                choices = [(bbox_iou(item.get("bbox"), target.get("bbox")), i) for i, target in enumerate(gt_items) if i not in matched]
                best, index = max(choices, default=(0.0, -1))
                ap_entries.setdefault(str(element_type), []).append((float(item.get("confidence", 1.0)), int(best >= 0.5)))
                if best >= 0.5: matched.add(index)
            ap_gt_counts[str(element_type)] = ap_gt_counts.get(str(element_type), 0) + len(gt_items)
    def average_precision(entries: list[tuple[float, int]], gt_count: int) -> float:
        if not gt_count: return 0.0
        entries=sorted(entries,key=lambda x:x[0],reverse=True); tp=fp=0; area=0.0; prev_recall=0.0
        for _,hit in entries:
            tp += hit; fp += 1-hit; recall=tp/gt_count; precision=tp/(tp+fp)
            area += max(0.0, recall-prev_recall)*precision; prev_recall=recall
        return area
    ap_by_type={k:average_precision(v,ap_gt_counts.get(k,0)) for k,v in ap_entries.items()}
    teds_value = sum(row["teds"] for row in rows) / max(1, len(rows))
    map_value = sum(ap_by_type.values()) / max(1, len(ap_by_type))
    summary = {"task": "task2", "page_count": len(rows), "TEDS": teds_value, "mAP@0.5": map_value, "mean_teds": teds_value, "map_at_0_5": map_value, "ap_at_0_5_by_element_type": ap_by_type, "pages": rows}
    write_json(output_path, summary)
    return summary


def evaluate_task3(prediction_dir: Path, gt_path: Path, output_path: Path) -> dict[str, Any]:
    gt_by = {str(row["query_id"]): row for row in read_jsonl(gt_path)}
    rows = []
    for path in sorted(prediction_dir.glob("*.json")):
        if path.name == "run_summary.json":
            continue
        result = read_json(path); payload = result.get("prediction_json") if isinstance(result.get("prediction_json"), dict) else result; query_id = str(result.get("query_id") or payload.get("query_id")); pred = payload or {}; gt = gt_by.get(query_id, {})
        iou = bbox_iou(pred.get("bbox"), gt.get("bbox")) if pred.get("found") else 0.0
        rows.append({"query_id": query_id, "target_type": gt.get("target_type"), "iou": iou, "correct_at_0_5": iou >= 0.5})
    by_type = {}
    for target_type in ("HandwrittenAnswer", "Question", "Instruction", "StudentCorrection"):
        values = [row for row in rows if row.get("target_type") == target_type]
        by_type[target_type] = {"query_count": len(values), "hit_at_0_5": sum(row["correct_at_0_5"] for row in values) / len(values) if values else None}
    available = [v["hit_at_0_5"] for v in by_type.values() if v["hit_at_0_5"] is not None]
    four_type = sum(available) / 4 if len(available) == 4 else None
    summary = {"task": "task3", "query_count": len(rows), "Macro Accuracy": four_type, "four_type_macro_hit_at_0_5": four_type, "accuracy_at_0_5_macro": four_type if four_type is not None else (sum(available) / len(available) if available else None), "by_target_type": by_type, "queries": rows}
    write_json(output_path, summary)
    return summary


def evaluate_task4(prediction_dir: Path, gt_path: Path, output_path: Path) -> dict[str, Any]:
    gt_by = {str(row["sample_id"]): row for row in read_jsonl(gt_path)}
    rows = []
    for path in sorted(prediction_dir.glob("*.json")):
        if path.name == "run_summary.json":
            continue
        result = read_json(path); sample_id = str(result.get("sample_id")); gt = gt_by.get(sample_id, {})
        content_type = str(gt.get("content_type") or "plain_text")
        target = normalize_task4_text(gt.get("gt_text"), content_type)
        predicted = normalize_task4_text(result.get("prediction_text"), content_type)
        distance = edit_distance(target, predicted)
        rows.append({"sample_id": sample_id, "cer": distance / max(1, len(target)), "exact_match": target == predicted, "gt": gt.get("gt_text"), "prediction": result.get("prediction_text"), "normalized_gt": target, "normalized_prediction": predicted, "edit_distance": distance})
    edit_total = sum(edit_distance(normalize_task4_text(row["gt"], gt_by[row["sample_id"]].get("content_type", "plain_text")), normalize_task4_text(row["prediction"], gt_by[row["sample_id"]].get("content_type", "plain_text"))) for row in rows)
    gt_char_total = sum(len(normalize_task4_text(row["gt"], gt_by[row["sample_id"]].get("content_type", "plain_text"))) for row in rows)
    summary = {
        "task": "task4",
        "crop_count": len(rows),
        "edit_distance_total": edit_total,
        "gt_char_total": gt_char_total,
        "CER": edit_total / max(1, gt_char_total),
        "cer": edit_total / max(1, gt_char_total),
        "mean_cer": edit_total / max(1, gt_char_total),
        "ExactMatch": sum(row["exact_match"] for row in rows) / max(1, len(rows)),
        "exact_match": sum(row["exact_match"] for row in rows) / max(1, len(rows)),
        "crops": rows,
    }
    write_json(output_path, summary)
    return summary
