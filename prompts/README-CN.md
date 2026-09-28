# Prompt 版本

[ English](README.md)

当前公开 Prompt：

| 任务 | 文件 | 输出 |
|---|---|---|
| Task1 | `task1.md` | 结构化判分 JSON |
| Task2 | `task2.md` | 页面结构 JSON |
| Task3 | `task3.md` | 单目标 bbox JSON |
| Task4 | `task4.md` | 纯手写文本 |

运行器会把任务输入和输出 Schema 注入 `{{TASK_INPUT}}`、`{{OUTPUT_SCHEMA}}`。正式评测时应记录 Prompt 文件版本和哈希，防止 Prompt 变化后混用结果。
