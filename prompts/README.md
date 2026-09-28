# Prompt Versions

[ Chinese version](README-CN.md)

The currently public prompts are:

| Task | File | Output |
|---|---|---|
| Task1 | `task1.md` | Structured grading JSON |
| Task2 | `task2.md` | Page-layout JSON |
| Task3 | `task3.md` | Single-target bbox JSON |
| Task4 | `task4.md` | Handwritten text only |

The runner injects the task input and output schema into `{{TASK_INPUT}}` and `{{OUTPUT_SCHEMA}}`. During formal evaluation, record the prompt file version and hash to prevent results from different prompt versions from being mixed.
