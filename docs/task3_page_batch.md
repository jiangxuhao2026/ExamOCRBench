# Task 3 Page-Batch Execution

Task 3 inputs remain one query per record, but queries from the same page may be grouped into one multimodal request to reduce request overhead. Grouping does not change the query, GT, or scoring policy. After the model response is received, it must be split back into one normalized result per `query_id`.

## Batch rules

- Group records by `record_id` or `page_id`; all queries in a batch must use the same image.
- A batch contains at most eight queries. Split larger pages into multiple batches.
- Preserve every query's original `query_id`, `target_type`, query text, and order.
- The model response must map every result to exactly one `query_id`.
- If a batch fails, write a terminal failure record for every query in that batch and keep those queries in the evaluation denominator.
- Format retries belong to the same batch. Do not count one batch's tokens or samples repeatedly.
- Single-query and page-batch results may coexist, but the result index must record `request_mode`, `batch_id`, and `query_ids`.

## Suggested batch-plan format

```json
{"batch_id":"page-0001-batch-0001","record_id":"demo-page-001","image":"images/page.jpg","queries":[{"query_id":"q-001","query":"Locate ...","target_type":"HandwrittenAnswer"},{"query_id":"q-002","query":"Locate ...","target_type":"Question"}]}
```

## Suggested model-response format

```json
{
  "batch_id": "page-0001-batch-0001",
  "results": [
    {"query_id":"q-001","found":true,"bbox":[100,200,300,400],"confidence":0.95},
    {"query_id":"q-002","found":false,"bbox":null,"confidence":0.2}
  ]
}
```

After splitting, each query is stored in the public result format:

```json
{"sample_id":"q-001","query_id":"q-001","status":"success","prediction_json":{"found":true,"bbox":[100,200,300,400],"confidence":0.95}}
```

## Scoring

Compute IoU and `Hit@0.5` separately for every query. The official headline metric is the equal-weight mean over the four target types:

```text
(HandwrittenAnswer + Question + Instruction + StudentCorrection) / 4
```

If a target type is absent, report that type as missing. Do not silently re-average the remaining types and call it the official four-type score.

## Recommended workflow

Start with a one-query smoke test using `--limit 1` to verify the image, endpoint, credentials, and output format. Then build a page-batch plan and send it through the provider's multimodal endpoint. The public result directory may still contain one JSON file per query; preserve the original batch response, retries, and query mapping in separate batch evidence files.
