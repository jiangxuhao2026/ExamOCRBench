You are performing ExamOCRBench Task 1: grade every anonymous answer unit on a complete deidentified exam page with a binary score.

- Independently judge the final student response using the printed question, options, tables, figures, section context, and visible handwriting.
- Every answer unit is worth exactly 1 point.
- Return every supplied `question_key/unit_key` exactly once. Do not add, remove, merge, reorder, or rename units.
- When grading is reliable, set `evaluable=true`, `grading_status="graded"`, and `awarded_score=0|1`, and provide one concise reference answer and judgement reason.
- When key information, mapping, or handwriting is not reliable, set `evaluable=false`, `grading_status="not_evaluable"`, `awarded_score=null`, and `reference_answer=null`.
- An unanswered but otherwise gradeable unit is still `evaluable=true` with score 0.
- For matching questions, output exactly one complete relation per unit and use `——` as the separator.
- Output strictly valid JSON only. Do not expose reasoning traces, internal IDs, annotation status, answerability labels, or hidden GT.

The runtime appends the dynamic output schema and anonymous question structure.

Output schema:
{{OUTPUT_SCHEMA}}

Anonymized question structure:
{{TASK_INPUT}}
