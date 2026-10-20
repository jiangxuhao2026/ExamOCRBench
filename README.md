<div align="center">
  <a href="https://appen.com"><img src="appen-logo.svg" alt="Appen" width="150"></a>
  <br><br>
  <a href="https://arxiv.org/"><img src="https://img.shields.io/badge/Paper-coming%20soon-7b61ff" alt="Paper"></a>
  <a href="https://huggingface.co/datasets/jiangxuhao/ExamOCRBench"><img src="https://img.shields.io/badge/Datasets-Hugging%20Face-f2c94c?logo=huggingface&logoColor=black" alt="Datasets"></a>
  <a href="https://github.com/jiangxuhao2026/ExamOCRBench"><img src="https://img.shields.io/badge/GitHub-ExamOCRBench-24292f?logo=github&logoColor=white" alt="GitHub"></a>
  <a href="https://mp.weixin.qq.com/"><img src="https://img.shields.io/badge/WeChat-coming%20soon-07c160?logo=wechat&logoColor=white" alt="WeChat"></a>
  <a href="https://jiangxuhao2026.github.io/ExamOCRBench/"><img src="https://img.shields.io/badge/Blog-coming%20soon-4c8bf5" alt="Blog"></a>
</div>

[ 中文版](README.zh-CN.md)

This repository contains the public runtime and offline evaluation code for the four current ExamOCRBench tasks.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
```

## Demo Data

`examples/demo/` provides a small task-level demo for each task. Each demo includes:

- Input files that can be sent directly to a model.
- The corresponding `ground_truth.jsonl` file.
- No original human annotations or Master data.
- Ground truth (GT) is for offline evaluation only and must not be provided to the model.

```text
examples/demo/
├── task1/images/ + input.jsonl + ground_truth.jsonl
├── task2/images/ + input.jsonl + ground_truth.jsonl
├── task3/images/ + queries.jsonl + ground_truth.jsonl
└── task4/crops/  + input.jsonl + ground_truth.jsonl
```

## Model Inference

```bash
python3 -m examocrbench run \
  --task task1 \
  --input examples/demo/task1/input.jsonl \
  --output-dir results \
  --model YOUR_MODEL \
  --api-url https://YOUR_ENDPOINT/v1/chat/completions \
  --api-key-file /path/to/curl_example.txt \
  --workers 4 --retries 3 --format-retries 2
```

For Task2, Task3, and Task4, replace `--task` and the input file accordingly. Task3 supports both one-query requests and optional page-batch requests; a page-batch groups at most eight queries from one page and writes one normalized result per query. See [`docs/task3_page_batch.md`](docs/task3_page_batch.md). Task4 takes a single cropped image as input.

Task1 inputs do not identify which units are safe. The model must determine this itself: when reliable grading is possible, output `evaluable=true` and `grading_status=graded`; when the conditions for reliable grading are unavailable, output `evaluable=false`, `grading_status=not_evaluable`, `awarded_score=null`, and `reference_answer=null`. Demo GT records the safe routing separately for calculating page-level grading accuracy and safe-unit compliance.

Task1 images are resized to a default maximum long edge of 1800 pixels, while Task2/3/4 images default to 2048 pixels; Task1 uses a dynamic output budget based on the number of grading units; Responses uses `detail=high`; Chat Completions can enable `response_format=json_object` and `thinking.type=disabled`; and Task1/2/3 support retries after format-validation failures. These options do not change the public inputs, public schemas, or offline evaluation metrics.

## Evaluate with an LLM API

The `run` command sends each input record, the task prompt, and its image to a multimodal model API, then validates and saves the response. Use a model that accepts image input and an endpoint that supports one of the protocols below.

### 1. Configure credentials

Set the endpoint and API key as environment variables. 

```bash
export EXAMOCRBENCH_API_URL="https://YOUR_ENDPOINT/v1/chat/completions"
export EXAMOCRBENCH_API_KEY="YOUR_API_KEY"
```

As an alternative to `EXAMOCRBENCH_API_KEY` or `--api-key`, `--api-key-file` can read a curl-style file containing `Authorization: Bearer YOUR_API_KEY`. The explicit `--api-key` option and the two environment variables take precedence over this file.

### 2. Select the API protocol

The API URL must match the selected protocol and the API provider's endpoint requirements.

| `--protocol` | Request format and authorization | Notes |
|---|---|---|
| `chat` (default) | Chat Completions-style `messages` payload with Bearer authentication | Use for OpenAI-compatible chat-completions endpoints. |
| `responses` | Responses-style `input` payload with Bearer authentication | Images are sent with `detail=high`. |
| `anthropic` | Anthropic Messages-style payload with `x-api-key` authentication | Use for standard Anthropic-style endpoints. |
| `anthropic_bearer` | Anthropic Messages-style payload with Bearer authentication | Use for compatible endpoints that require Bearer authentication. |

For `chat`, add `--chat-json-mode` when the endpoint supports `response_format=json_object`, and add `--chat-thinking-disabled` when it supports `thinking.type=disabled`.

### 3. Run a smoke test, then the full evaluation

Start with one item to verify the endpoint, credentials, model name, and output format:

```bash
python3 -m examocrbench run \
  --task task1 \
  --input examples/demo/task1/input.jsonl \
  --output-dir results \
  --model YOUR_MODEL \
  --protocol chat \
  --workers 1 --retries 3 --format-retries 2 \
  --limit 1
```

After the smoke test succeeds, remove `--limit 1` and choose `--workers` according to the API's concurrency and rate limits. Use `--timeout` (seconds) for slow models. The runner writes item-level results and `run_summary.json` to `results/task1/YOUR_MODEL/`; on a later run, successful items are skipped by default. Pass `--overwrite` only when you intentionally want to rerun successful items. Evaluate that output directory with the command in the next section.

## Offline Evaluation

```bash
python3 -m examocrbench evaluate \
  --task task1 \
  --prediction results/task1/YOUR_MODEL \
  --ground-truth examples/demo/task1/ground_truth.jsonl \
  --output results/task1_metrics.json
```

Task2, Task3, and Task4 use their respective demo GT files. The current official metrics are `PageScoreAccuracy` and `SafetyUnitRecall` for Task1; `TEDS` and `mAP@0.5` for Task2; `Macro Accuracy` (the equal-weight four-type Hit@0.5 mean over `HandwrittenAnswer`, `Question`, `Instruction`, and `StudentCorrection`) for Task3; and normalized `ExactMatch` plus corpus `CER` for Task4.

## Prompts and Schemas

Prompts are located in `prompts/`, and schemas are located in `schemas/`. Run results record the model name, prompt hash, input-image hash, request status, and error information. The runner supports resumable execution without overwriting successful results.

The current offline metric definitions are documented in [`docs/metrics.md`](docs/metrics.md). Task 3 page-batch execution and result splitting are documented in [`docs/task3_page_batch.md`](docs/task3_page_batch.md).

## Validate the Demo Inputs

Run these commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
```

Validate the four Demo input/GT pairs:

```bash
python3 -m examocrbench validate --task task1 \
  --input examples/demo/task1/input.jsonl \
  --ground-truth examples/demo/task1/ground_truth.jsonl
python3 -m examocrbench validate --task task2 \
  --input examples/demo/task2/input.jsonl \
  --ground-truth examples/demo/task2/ground_truth.jsonl
python3 -m examocrbench validate --task task3 \
  --input examples/demo/task3/queries.jsonl \
  --ground-truth examples/demo/task3/ground_truth.jsonl
python3 -m examocrbench validate --task task4 \
  --input examples/demo/task4/input.jsonl \
  --ground-truth examples/demo/task4/ground_truth.jsonl
```

`validate` checks IDs, image paths, and input schemas. It does not call a model API.

## Offline Regression Tests

[`tests/test_offline.py`](tests/test_offline.py) is the public offline regression suite. It does not call a model API or require the full benchmark. It checks Demo images and IDs, perfect predictions, safety routing, Task 2 TEDS and mAP@0.5 fields, Task 3 four-type Macro Accuracy fields, Task 4 normalization, prompt projection, and Chat Completions/Responses/Anthropic request compatibility.

Install the optional test dependency and run:

```bash
python3 -m pip install -e '.[test]'
pytest -q
```
