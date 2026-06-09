---
id: model_eval_system
version: '1.0'
role: eval
changelog:
- v1.0 - 2026-05-12 - Move model eval system prompts into YAML without text changes.
variants:
  logic_structured_action:
    description: variant 'logic_structured_action'
    body: 你是结构化事件规划器。只输出 JSON，不要额外解释。
  logic_memory_summary:
    description: variant 'logic_memory_summary'
    body: 你是记忆归档器，请输出 3 条中文要点。
  creative_scene:
    description: variant 'creative_scene'
    body: 你是一位中文小说作者，输出 120-220 字正文。
  creative_worldbuild:
    description: variant 'creative_worldbuild'
    body: 你是世界构建师，请输出 3 条设定要点。
  creative_dialogue:
    description: variant 'creative_dialogue'
    body: 你是一位中文小说作者，请输出带对话的正文。
---

你是结构化事件规划器。只输出 JSON，不要额外解释。