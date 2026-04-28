# Sprint 23: 输出质量击穿 (Narrator Quality Breakthrough)

**Sprint Goal**: 让 Narrator 输出从"模板复读"变成"可读的小说"。
**验收标准**: 实际跑一个 4 章推演，每章输出 500-1000 字，有场景描写、对话、角色动作，不重复 Scene Script 原文。

---

## 问题诊断

### 根因 1: Narrator prompt 过度约束（最严重）
- **位置**: `engine/graph.py` L1152-1161
- **问题**: 
  - "200-400字" → 太短，小说章节至少 500-1000 字
  - "只能扩写 SceneScript 中的 summary、public_facts 与 beats，不得新增会改变剧情因果的新事实" → LLM 不敢创作，只会复读 summary
  - 结果：每章都是 Scene Script summary 的同义改写，不是小说
- **修复**: 重写 system prompt，鼓励 LLM 创作有细节的小说文本

### 根因 2: Narrator 输入数据质量差
- **位置**: `engine/graph.py` `_build_narrator_input_v2()` + `engine/dual_loop.py` GM 结算
- **问题**: SceneScript.summary 本身就是模板文本（"围绕XX承接上一幕并制造新的选择..."），beats 也是抽象描述
- **修复**: GM 结算时生成更具体的事件描述，而非复述 objective

### 根因 3: 干预过于频繁
- **位置**: `engine/graph.py` node_detector 逻辑
- **问题**: 每个节点都触发 intervention，打断推演节奏
- **修复**: 降低干预频率，只在真正关键的节点暂停

### 根因 4: 可能存在 LLM 空输出 bug
- **位置**: `engine/graph.py` L1215+ 的 narrator LLM 调用
- **问题**: `estimated_completion_tokens: 0`，LLM 可能没真正生成文本
- **修复**: 检查 LLM 调用逻辑，确保 response 被正确解析

---

## 具体修改项

### T1: 重写 Narrator system prompt (engine/graph.py)

**当前 prompt** (L1152-1161):
```
你是一位出色的中文小说作者。将 GM 结算后的 SceneScript 渲染为生动的小说正文。
硬性要求：
1. 用第三人称叙述，200-400字
2. 包含场景描写、人物动作和对话
3. 只能扩写 SceneScript 中的 summary、public_facts 与 beats，不得新增会改变剧情因果的新事实
4. 不要写入 rejected_intent_ids 对应的被拒绝意图
5. 与前文记忆保持一致，不要与已有记忆矛盾
6. 只输出小说正文，不要有标题或其他内容
```

**新 prompt**:
```
你是一位出色的中文网络小说作家。你的任务是根据 GM（游戏主持人）提供的场景脚本，
创作一段引人入胜的小说章节。

写作风格要求：
1. 第三人称叙述，800-1500 字
2. 开头用环境描写建立氛围（天气、光线、声音、气味）
3. 角色对话要有个性——用语气、用词、口癖体现性格差异
4. 穿插角色的心理活动和微表情描写
5. 段落之间有节奏变化：紧张时短句，舒缓时长句
6. 章节结尾留悬念或情绪钩子，让读者想看下一章

创作边界：
- 以 SceneScript 中的 beats 为剧情骨架，在此基础上丰富细节
- 不要改变 beats 中定义的核心事实（谁做了什么、结果是什么）
- 可以添加：环境细节、配角反应、角色内心独白、感官描写
- 不要写入被拒绝的意图（rejected intent ids）

输出合法 JSON：
{
  "prose": "小说正文...",
  "style_notes": "本段风格说明（一句话）"
}
```

### T2: 重写 legacy path 的 Narrator prompt (engine/graph.py L1185-1208)

同 T1 的思路，但用于非 Scene Script 路径。

### T3: 改善 GM 结算输出质量 (engine/dual_loop.py)

当前 GM 结算的 SceneScript.summary 直接复述 Director 的 objective。
修改：让 GM 的结算 prompt 要求输出具体的事件描述，而非抽象目标。

### T4: 降低干预频率 (engine/graph.py)

当前：每个节点都触发 `needs_intervention = True`
修改：只在以下条件触发干预：
- 每 3 个节点才触发一次（tick % 3 == 0）
- 或者出现了角色死亡/重大背叛等剧情转折点
- 其他节点自动跳过干预

### T5: 验证 LLM 输出不为空 (engine/graph.py)

检查 narrator_node 中 LLM 调用的返回值解析逻辑，确保：
- response 不为空字符串
- JSON 解析正确提取 prose 字段
- 如果 LLM 返回空，使用 fallback 但标记 warning

### T6: 编写测试

为以上每个修改编写对应的测试：
- T1/T2: 测试 narrator prompt 包含新的写作风格要求
- T3: 测试 GM 结算输出更具体的事件描述
- T4: 测试干预频率降低（只有 tick % 3 == 0 时触发）
- T5: 测试 LLM 空输出的 fallback 逻辑

---

## 验证方式

1. `make test` 全部通过
2. `make lint` 全部通过
3. 实际跑一次推演（API 调用），检查：
   - 每章 rendered_text 长度 >= 500 字
   - rendered_text 包含对话（引号）
   - rendered_text 不包含 Scene Script 原文的模板句式（"围绕XX承接上一幕"）
   - 干预只在第 1 章和第 4 章触发（4 章推演）
