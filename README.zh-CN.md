<div align="center">
  <a href="https://appen.com"><img src="appen-logo.svg" alt="Appen" width="150"></a>
  <br><br>
  <a href="https://arxiv.org/"><img src="https://img.shields.io/badge/Paper-coming%20soon-7b61ff" alt="论文"></a>
  <a href="https://huggingface.co/datasets/jiangxuhao/ExamOCRBench"><img src="https://img.shields.io/badge/Datasets-Hugging%20Face-f2c94c?logo=huggingface&logoColor=black" alt="数据集"></a>
  <a href="https://github.com/jiangxuhao2026/ExamOCRBench"><img src="https://img.shields.io/badge/GitHub-ExamOCRBench-24292f?logo=github&logoColor=white" alt="GitHub"></a>
  <a href="https://mp.weixin.qq.com/s/tTKRsXB8azZInE4kSiB76g"><img src="https://img.shields.io/badge/WeChat-ExamOCRBench-07c160?logo=wechat&logoColor=white" alt="微信公众号"></a>
  <a href="https://jiangxuhao2026.github.io/ExamOCRBench/"><img src="https://img.shields.io/badge/Blog-coming%20soon-4c8bf5" alt="博客"></a>
</div>

[ English](README.md)

这是 ExamOCRBench 当前四个任务的公开运行和离线评测代码。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
```

## Demo 数据

`examples/demo/` 提供少量任务级 Demo。每个任务都包含：

- 可直接送入模型的输入文件；
- 对应的 `ground_truth.jsonl`；
- 不包含原始人工标注和 Master；
- GT 只用于离线评测，不应传给模型。

```text
examples/demo/
├── task1/images/ + input.jsonl + ground_truth.jsonl
├── task2/images/ + input.jsonl + ground_truth.jsonl
├── task3/images/ + queries.jsonl + ground_truth.jsonl
└── task4/crops/  + input.jsonl + ground_truth.jsonl
```

## 模型推理

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

Task2、Task3、Task4 只需替换 `--task` 和输入文件。Task3 支持单 query 请求，也支持可选的 page-batch 请求：同一页最多合并 8 条 query，并在返回后拆成每条 query 的标准结果。详见 [`docs/task3_page_batch.md`](docs/task3_page_batch.md)。Task4 输入是单 crop 图片。

Task1 输入不会标记哪些单元是安全单元。模型必须自己判断：可可靠判分时输出 `evaluable=true`、`grading_status=graded`；缺少可靠判分条件时输出 `evaluable=false`、`grading_status=not_evaluable`、`awarded_score=null` 和 `reference_answer=null`。Demo GT 会单独记录安全路由，用于计算页面判分正确率和安全单元合规率。

Task1 图片默认压缩到长边 1800，Task2/3/4 默认压缩到长边 2048；Task1 使用按评分单元数量计算的动态输出预算；Responses 使用 `detail=high`；Chat Completions 可开启 `response_format=json_object` 和 `thinking.type=disabled`；Task1/2/3 支持格式校验失败后的重试。公开输入、公开 Schema 和离线评测指标不因此改变。

## 使用大模型 API 进行测评

`run` 命令会将每条输入记录、任务 Prompt 和对应图片发送到多模态模型 API，再校验并保存模型响应。请使用支持图像输入的模型，并选择下文所列的 API 协议之一。

### 1. 配置鉴权信息

推荐通过环境变量配置 API 端点和密钥。

```bash
export EXAMOCRBENCH_API_URL="https://YOUR_ENDPOINT/v1/chat/completions"
export EXAMOCRBENCH_API_KEY="YOUR_API_KEY"
```

除 `EXAMOCRBENCH_API_KEY` 或 `--api-key` 外，也可以通过 `--api-key-file` 读取一个包含 `Authorization: Bearer YOUR_API_KEY` 的 curl 格式文件。显式传入的 `--api-key` 及这两个环境变量优先于该文件。

### 2. 选择 API 协议

API URL 必须与所选协议以及服务商要求的端点格式匹配。

| `--protocol` | 请求格式与鉴权方式 | 说明 |
|---|---|---|
| `chat`（默认） | Chat Completions 风格的 `messages` 请求体，使用 Bearer 鉴权 | 用于兼容 OpenAI Chat Completions 的端点。 |
| `responses` | Responses 风格的 `input` 请求体，使用 Bearer 鉴权 | 图片会以 `detail=high` 发送。 |
| `anthropic` | Anthropic Messages 风格的请求体，使用 `x-api-key` 鉴权 | 用于标准 Anthropic 风格端点。 |
| `anthropic_bearer` | Anthropic Messages 风格的请求体，使用 Bearer 鉴权 | 用于要求 Bearer 鉴权的兼容端点。 |

使用 `chat` 时，如果端点支持 `response_format=json_object`，可增加 `--chat-json-mode`；如果端点支持 `thinking.type=disabled`，可增加 `--chat-thinking-disabled`。

### 3. 先试跑，再进行完整测评

先使用一条数据确认端点、鉴权信息、模型名和输出格式均正确：

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

试跑成功后，删除 `--limit 1` 即可进行完整测评，并根据 API 的并发和限流要求设置 `--workers`。对于响应较慢的模型，可通过 `--timeout` 设置超时秒数。运行器会将单条结果和 `run_summary.json` 写入 `results/task1/YOUR_MODEL/`；再次运行时默认跳过已成功的样本。如需主动重跑已成功样本，才应传入 `--overwrite`。随后使用下一节的命令对该输出目录进行离线评测。

## 离线评测

```bash
python3 -m examocrbench evaluate \
  --task task1 \
  --prediction results/task1/YOUR_MODEL \
  --ground-truth examples/demo/task1/ground_truth.jsonl \
  --output results/task1_metrics.json
```

Task2、Task3、Task4 使用各自的 Demo GT。当前正式指标为：Task1 `PageScoreAccuracy` 和 `SafetyUnitRecall`；Task2 `TEDS` 和 `mAP@0.5`；Task3 四类目标（HandwrittenAnswer、Question、Instruction、StudentCorrection）Hit@0.5 的等权平均，名称为 `Macro Accuracy`；Task4 归一化 `ExactMatch` 和 corpus `CER`。

## Prompt 和 Schema

Prompt 位于 `prompts/`，Schema 位于 `schemas/`。运行结果记录模型名、Prompt 哈希、输入图片哈希、请求状态和错误信息，支持不覆盖成功结果的断点续跑。

当前离线指标口径见 [`docs/metrics.md`](docs/metrics.md)，Task3 page-batch 的分组、重试和结果拆分见 [`docs/task3_page_batch.md`](docs/task3_page_batch.md)。



## 评测命令

以下命令都在仓库根目录执行。先安装依赖并设置模块路径：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
```

### 先校验 Demo 输入

```bash
python3 -m examocrbench validate \
  --task task1 \
  --input examples/demo/task1/input.jsonl \
  --ground-truth examples/demo/task1/ground_truth.jsonl

python3 -m examocrbench validate \
  --task task2 \
  --input examples/demo/task2/input.jsonl \
  --ground-truth examples/demo/task2/ground_truth.jsonl

python3 -m examocrbench validate \
  --task task3 \
  --input examples/demo/task3/queries.jsonl \
  --ground-truth examples/demo/task3/ground_truth.jsonl

python3 -m examocrbench validate \
  --task task4 \
  --input examples/demo/task4/input.jsonl \
  --ground-truth examples/demo/task4/ground_truth.jsonl
```

`validate` 只检查输入/GT 的 ID 集合、图片路径和输入 Schema，不调用模型 API。

### 使用模型 API 推理

先用一条样本试跑，确认端点、鉴权、图片输入和输出格式：

```bash
export EXAMOCRBENCH_API_URL="https://YOUR_ENDPOINT/v1/chat/completions"
export EXAMOCRBENCH_API_KEY="YOUR_API_KEY"

python3 -m examocrbench run \
  --task task1 \
  --input examples/demo/task1/input.jsonl \
  --output-dir results/task1/YOUR_MODEL \
  --model YOUR_MODEL \
  --protocol chat \
  --workers 1 \
  --retries 3 \
  --format-retries 2 \
  --limit 1
```

试跑通过后，去掉 `--limit 1`，并按照 API 限流能力增加 `--workers`：

```bash
python3 -m examocrbench run \
  --task task1 \
  --input examples/demo/task1/input.jsonl \
  --output-dir results/task1/YOUR_MODEL \
  --model YOUR_MODEL \
  --protocol chat \
  --workers 4 \
  --retries 3 \
  --format-retries 2
```

Task2、Task3、Task4 只需要替换 `--task`、输入文件和输出目录。例如 Task3：

```bash
python3 -m examocrbench run \
  --task task3 \
  --input examples/demo/task3/queries.jsonl \
  --output-dir results/task3/YOUR_MODEL \
  --model YOUR_MODEL \
  --protocol chat \
  --workers 4 \
  --retries 3 \
  --format-retries 2
```

如果使用 Responses 或 Anthropic 兼容端点，可将 `--protocol` 改为 `responses`、`anthropic` 或 `anthropic_bearer`。Chat Completions 端点如支持 JSON mode 和关闭 thinking，可增加：

```bash
--chat-json-mode --chat-thinking-disabled
```

### 离线评测模型结果

每个任务的 `--prediction` 可以是包含单条 JSON 结果的目录，也可以是 JSONL 文件。GT 只用于离线评测，不能传给模型。

```bash
python3 -m examocrbench evaluate \
  --task task1 \
  --prediction results/task1/YOUR_MODEL \
  --ground-truth examples/demo/task1/ground_truth.jsonl \
  --output results/task1/YOUR_MODEL_metrics.json

python3 -m examocrbench evaluate \
  --task task2 \
  --prediction results/task2/YOUR_MODEL \
  --ground-truth examples/demo/task2/ground_truth.jsonl \
  --output results/task2/YOUR_MODEL_metrics.json

python3 -m examocrbench evaluate \
  --task task3 \
  --prediction results/task3/YOUR_MODEL \
  --ground-truth examples/demo/task3/ground_truth.jsonl \
  --output results/task3/YOUR_MODEL_metrics.json

python3 -m examocrbench evaluate \
  --task task4 \
  --prediction results/task4/YOUR_MODEL \
  --ground-truth examples/demo/task4/ground_truth.jsonl \
  --output results/task4/YOUR_MODEL_metrics.json
```

当前正式指标名称为：

- Task1：`PageScoreAccuracy`、`SafetyUnitRecall`；
- Task2：`TEDS`、`mAP@0.5`；
- Task3：`Macro Accuracy`，即四类目标 Hit@0.5 的等权平均；
- Task4：归一化 `ExactMatch`、corpus `CER`。

完整定义见 [`docs/metrics.md`](docs/metrics.md)。

### Task3 page-batch

Task3 可以按同一页最多 8 条 query 组成一次 page-batch 请求，返回后必须拆成每条 query 的标准 JSON 结果。批次计划、输出格式、失败重试和评分注意事项见 [`docs/task3_page_batch.md`](docs/task3_page_batch.md)。

### 测试脚本的用途

[tests/test_offline.py](tests/test_offline.py) 是公开仓库的离线回归测试，不调用模型 API，也不需要完整 Benchmark。它验证：

- 四个 Demo 输入和图片路径完整；
- Task1–4 完美预测可以得到满分；
- Task1 安全单元路由和页面级指标；
- Task2 TEDS 与 `mAP@0.5` 字段；
- Task3 四类指标字段和 IoU@0.5；
- Task4 公式、布尔、空白和大小写归一化；
- Prompt 投影不会把内部 record ID 注入模型 Prompt；
- Chat Completions、Responses、Anthropic 三类 API payload 结构正确。

安装测试依赖后运行：

```bash
python3 -m pip install -e '.[test]'
pytest -q
```

如果环境没有安装 pytest，也可以直接调用测试函数进行最小回归检查；但正式开发建议使用 pytest。
