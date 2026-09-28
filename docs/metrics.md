# Official Offline Metrics

The public evaluator follows the current ExamOCRBench metric definitions. Demo GT exists only for local evaluator checks; it does not imply that the official test GT is public.

## Task 1

- `PageScoreAccuracy`: among pages with at least one normal grading unit, the proportion whose normal units are all graded correctly.
- `SafetyUnitRecall`: the proportion of safety units for which the model correctly returns the non-evaluable route.
- Normal pages, normal units, and safety units retain separate denominators. Missing predictions and terminal failures remain in the denominator.

## Task 2

- `TEDS`: normalized tree-edit similarity after the Task 2 eligibility and placeholder-cleaning rules.
- `mAP@0.5`: per-element-type average precision using IoU >= 0.5, averaged over eligible element categories.
- The official metric set contains TEDS and mAP@0.5. Layout F1 is not an official headline metric.
- Table text, matching-question response slots, and annotation-only placeholders follow the Task 2 filtering rules.

## Task 3

- Each query is evaluated with IoU and Hit@0.5.
- The official headline metric is `Macro Accuracy`, the equal-weight arithmetic mean over:
  - `HandwrittenAnswer`
  - `Question`
  - `Instruction`
  - `StudentCorrection`
- Missing target types are reported explicitly and must not silently change the official four-type denominator.
- Single-query and page-batch requests are scored identically after batch results are split back to query-level records.

## Task 4

- Text is normalized by content type using NFKC, case/whitespace normalization, full-width punctuation conversion, formula-operator normalization, and boolean-symbol normalization.
- `ExactMatch` compares normalized GT and prediction text.
- `CER` is corpus CER: total edit distance divided by total GT character count, not the mean of per-crop CER values.
- Per-crop output retains raw and normalized text, edit distance, CER, ExactMatch, API failure, and empty-output status.
