You are performing ExamOCRBench Task3: single-target visual localization.

Locate the unique target in the complete exam-page image according to the query.

Requirements:
1. Output only one JSON object. Do not output Markdown or explanations.
2. When the target is found, set `found=true` and output a `bbox` in normalized_1000 coordinates.
3. When the target is not found, set `found=false`; `bbox` must be `null`.
4. Do not output multiple candidate boxes or guess targets beyond the query.
5. The query may refer to a handwritten answer, a printed question stem, response instructions, or a correction area. Locate only the one unique target explicitly indicated by the query.
6. If the page contains multiple similar targets, distinguish them using the text, question context, or number provided in the query. Do not return an adjacent target or a large box around the entire question.
7. The `bbox` must tightly enclose the actual target area. Do not expand it to the entire line, question, or page.

Output schema:
{{OUTPUT_SCHEMA}}

Task input:
{{TASK_INPUT}}
