Parse a complete deidentified answered exam page and recover its printed exam structure.

- Allowed elements: `Page`, `Section`, `Instruction`, `Question`, `Figure`, `Table`, `ResponseSlot`.
- Do not transcribe student answers, grade the exam, or output correction events.
- Use `normalized_1000` boxes `[x1,y1,x2,y2]`.
- There must be exactly one Page node with `parent_id=null`, `bbox=[0,0,1000,1000]`, and `reading_order=0`.
- `Question.text` and `Instruction.text` contain printed text only; `Section/Figure/Table/ResponseSlot.text=null`.
- `Table` is one node covering a complete printed table or grid. Do not split its cells into separate `Table` nodes.
- Every independent answer position inside a table must still be emitted as a separate `ResponseSlot`.
- Set `Table.parent_id` to the owning `Question` or `Instruction` when possible, otherwise to `Section`. A `ResponseSlot` inside a table remains a child of its `Question`, not of `Table`.
- Parent-child relations and reading order must be valid.
- Output one complete JSON object conforming to the dynamic schema.

Output schema:
{{OUTPUT_SCHEMA}}

Public parsing input:
{{TASK_INPUT}}
