# Demo Usage

Demo inputs and GT are separate interfaces:

```text
input.jsonl / queries.jsonl + images/crops
  -> model inference
  -> results/
  -> ground_truth.jsonl
  -> offline evaluation
```

Never send `ground_truth.jsonl` to a model. Demo GT exists so users can verify the evaluator locally; official benchmark GT remains withheld.

Task 1 uses a privacy-safe page and an anonymous public packet. The input does not reveal the safety-unit route. Task 2 uses a privacy-safe page and structural input. Task 3 uses a privacy-safe page and a query without the GT box. Task 4 uses one handwritten answer crop.
