# Public Data Contract

The public repository starts at model-visible inputs. Users do not need the original human annotations, `R*.result.json` files, or Master data.

## Task 1

`input.jsonl` contains a privacy-safe page and an anonymous public packet. `ground_truth.jsonl` contains reference answers, grading routes, scores, and page-level labels for the local demo only. A model must never receive the GT file.

## Task 2

`input.jsonl` contains a privacy-safe page and the allowed structural element types. GT is a separate structure tree with element types, bounding boxes, parent IDs, and reading order. The official metrics are TEDS and layout mAP@0.5; Layout F1 is not part of the current official metric set.

## Task 3

`queries.jsonl` contains a privacy-safe page and a single-target query without the GT bounding box. GT stores the target type and reference box by `query_id`. Requests may be sent one query at a time or as a page-batch of at most eight queries. Results must be split back to one normalized result per query. The official metric is Macro Accuracy: the equal-weight Hit@0.5 mean over HandwrittenAnswer, Question, Instruction, and StudentCorrection.

## Task 4

`input.jsonl` points to one answer crop. GT stores the handwritten text and content type. Task 4 does not require the original question or answer-region source in the model input. The official metrics are normalized ExactMatch and corpus CER.

## IDs and paths

The demo uses `sample_id`, `query_id`, and relative paths. A public release may use its own stable anonymous IDs, but must not include local absolute paths, internal source IDs, private mappings, or API credentials.
