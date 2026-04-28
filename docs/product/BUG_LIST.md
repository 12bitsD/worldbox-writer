# WorldBox Writer Bug List

**日期**: 2026-04-28
**测试方式**: 浏览器手动操作 + API 直接调用 + 源码审查

---

## 🔴 Critical (阻塞核心流程)

### BUG-01: "开始推演" 按钮点击无响应
- **现象**: 在 StartPanel 中填写故事前提后，点击"开始推演 →"按钮，页面无任何变化。不出现 loading 状态，不跳转，不报错。
- **复现**: 浏览器打开 http://localhost:5173 → 点击示例前提填充文本框 → 点击"开始推演 →"
- **影响**: 用户无法通过 UI 创建新故事。但通过 `document.querySelector('form').dispatchEvent(new Event('submit'))` 可以触发。
- **根因推测**: 按钮是 `type="submit"`，click 事件可能被表单外层的某个元素（watermark-bg 的 `onClick` 或事件冒泡）拦截/吞掉了。或者存在 CSS overlay 问题阻挡了点击事件传递到按钮。从 accessibility tree 看按钮 ref 不带 `[disabled]`，说明 disabled 不是问题。

### BUG-02: 点击"最近会话"列表项无法打开已有会话
- **现象**: 在 StartPanel 底部"最近会话"区域，点击任何会话按钮（如 "0c59eaf7 · waiting · 4 节点 打开"），页面不变。
- **复现**: 浏览器打开首页 → 点击任一最近会话按钮
- **影响**: 用户无法恢复之前的推演会话，所有历史推演数据无法通过 UI 访问。
- **根因推测**: 同 BUG-01，可能是通用的事件传递问题，或者 `openSession` 内部的 `getSimulation` 调用在某种条件下静默失败。

### BUG-03: 推演永远卡在 "initializing" 状态
- **现象**: 通过 API 或偶尔通过 UI 创建的新会话，状态一直停留在 "initializing"，节点数为 0，不会自动恢复。当前 DB 中有 4 个 stuck 的 initializing 会话。
- **复现**: `curl -X POST http://localhost:8000/api/simulate/start -d '{"premise":"test","max_ticks":4}'`，等待 60 秒后状态仍为 initializing。
- **影响**: 推演引擎完全无法启动新的推演。
- **根因推测**: 后端推演线程可能在 Director/WorldBuilder 初始化阶段挂起或抛出未捕获异常，导致状态无法从 initializing 转为 running 或 error。没有超时/自愈机制。

### BUG-04: error 状态会话无错误信息展示
- **现象**: 会话列表中有 6 个 status=error 的会话，但 UI 上只显示 "error" 标签，不展示具体错误原因（如 "Server restarted during simulation"）。点击也无法查看详情。
- **API 响应**: `{"status":"error","error":"Server restarted during simulation","nodes":0}`
- **影响**: 用户无法判断失败原因，也无法决定是否重试。

---

## 🟡 Major (严重影响体验)

### BUG-05: 生成文本严重重复，质量远低于可用标准
- **现象**: 所有 4 个节点的 rendered_text 几乎完全一样（仅替换 "第N幕"），每段约 280 字且高度模板化：
  ```
  第N幕：流亡破局者、秩序追猎者的局势推进继续展开。
  在第N幕：...中，流亡破局者围绕"推进主线目标"采取具体行动，
  沿"围绕流亡破局者、秩序追猎者承接上一幕并制造新的选择、阻力或推进，
  承接线索：..."推进线索，并制造新的阻力或选择；
  秩序追猎者围绕"阻止破局者"主动设置阻碍...
  人物在既有事实和约束下推进选择，新的局势也随之积蓄。
  ```
- **影响**: 生成的内容不是小说，而是 Scene Objective 的复读。完全不可读。
- **根因**: Narrator 的 system prompt (要求 200-400 字高质量小说) 虽然合理，但输入的 Scene Script 内容本身是 Director 的 objective 模板文本，LLM (gpt-4.1-mini) 可能只是在"扩写" objective 而非创作小说。另外 `estimated_completion_tokens: 0` 说明 LLM 可能返回了空 completion。

### BUG-06: 角色命名高度模板化，非真实人名
- **现象**: 所有角色自动命名为 "流亡破局者"、"秩序追猎者"、"弃徒剑修"、"玄门追猎者" 等模板化代号，而非像 "李青山"、"苏婉儿" 这样的真实角色名。
- **影响**: 阅读体验极差，像在读工程文档而非小说。
- **根因**: Director 的角色生成 prompt 倾向于用"功能定位"而非"人名"来命名角色。

### BUG-07: 每个节点都触发 requires_intervention=true
- **现象**: 4 个节点全部标记 `requires_intervention: true`，意味着每推演一步都要等用户干预。
- **影响**: 用户被迫在每个节点都输入干预指令或点击"跳过"，完全打断阅读和推演节奏。对于 max_ticks=4 的推演，用户需要干预 4 次才能看完。
- **根因**: NodeDetector 的干预检测逻辑过于敏感，几乎所有事件都被标记为"高优先级分歧"。

### BUG-08: 角色记忆条目被截断且互相复制
- **现象**: 
  - 两个角色（流亡破局者 和 秩序追猎者）的记忆条目完全相同
  - 记忆内容被截断在固定长度（约 100 字符），以 "承" 结尾
  - 每条记忆都是 "在第N幕：...的局势推进中，流亡破局者围绕..." 的模板复读
- **影响**: 记忆系统形同虚设，角色无法基于差异化记忆做出不同决策。
- **根因**: 
  1. memory 写入的来源可能是 Scene Script summary 而非角色特定的行为
  2. 20 条上限的 `max_length` 限制导致截断（Character model 的 `memory: List[str] = Field(default_factory=list, max_length=20)`，但截断发生在更早的地方）

### BUG-09: 节点标题全部相同模板
- **现象**: 所有节点标题都是 "第N幕：{角色名}的局势推进"，完全缺乏叙事性。
- **对比**: 好的标题应该是 "废墟中的第一次交锋"、"水井边的秘密交易" 等。
- **根因**: Director._derive_scene_title() 方法使用固定模板 `f"第{world.tick + 1}幕：{focus}的{pressure_label}"`，没有调用 LLM 生成有创意的标题。

---

## 🟠 Moderate (影响体验但不阻塞)

### BUG-10: 推演卡住时无超时/取消机制
- **现象**: 会话停留在 "initializing" 或 "running" 状态，UI 显示 "Agent 集群正在推演下一个故事节点..." 但永远不会结束。没有超时自动终止，也没有手动取消按钮。
- **影响**: 用户唯一的选择是"重置"，丢失所有进度。
- **建议**: 增加 60 秒超时自动转 error + 手动取消按钮。

### BUG-11: 世界标题被截断
- **现象**: 世界标题显示为 "《末日后的地下城市，三个势》"，"力" 字被截断。
- **根因**: Director 生成标题时使用了固定字符数截断，但中文按字节而非字符截断。

### BUG-12: factions 和 locations 始终为空
- **现象**: 4 个推演会话的 factions 和 locations 列表全部为空 `[]`。
- **影响**: 左侧"设定集 (Lorebook)" 面板中的势力和地点部分永远是空的，世界设定不够丰富。

### BUG-13: "开始推演" 按钮在 loading 期间的行为不一致
- **现象**: 按钮文案在 loading 时变为 "初始化世界中..."，但由于 BUG-01，用户看不到这个状态变化。
- **额外问题**: 如果 loading 状态卡住（如 BUG-03），按钮会永远显示 "初始化世界中..." 且不可点击。

### BUG-14: 关系图谱在推演过程中始终为空
- **现象**: 角色之间没有建立任何关系（relationships: {}），即使推演了 4 幕。
- **影响**: 右侧"关系网"面板无法展示有意义的角色关系。
- **根因**: Actor/GM 流程没有自动更新角色关系。

### BUG-15: 推演日志中 narrative_pressure 始终为 "balanced"
- **现象**: 所有 4 个 Scene Plan 的 narrative_pressure 都是 "balanced"，没有变化。
- **影响**: 故事节奏单调，没有"平静 → 紧张 → 高潮"的起伏。
- **根因**: Director 没有根据故事进展动态调整叙事压力。

---

## 🔵 Minor (小问题)

### BUG-16: 页面刷新后 sessionStorage 恢复行为不可预测
- **现象**: 如果上次会话是 error 状态，刷新页面后会自动尝试恢复该 error 会话。
- **建议**: 恢复时应检查状态，error/initializing 的会话不应自动恢复。

### BUG-17: 错误会话在列表中没有清理入口
- **现象**: 6 个 error 会话 + 4 个 initializing 会话堆在列表中，用户无法删除。
- **建议**: 增加删除/清理按钮，或自动隐藏 error 会话。

### BUG-18: 端口冲突时后端静默启动失败
- **现象**: 当 8000 端口已被占用时，`make dev-api` 报 `address already in use` 然后退出，但前端仍在运行。
- **建议**: 检测端口冲突时给出更友好的提示，或者自动 kill 旧进程。

### BUG-19: Character model 中 memory 的 max_length=20 会静默丢弃
- **现象**: `add_memory()` 方法在超过 20 条时只保留最近 20 条，但没有归档机制。
- **影响**: 早期重要记忆被静默丢弃，角色随时间推演会"遗忘"早期事件。
- **根因**: 虽然有三层记忆系统（working/episodic/reflective），但 character.memory 只是 working memory，丢弃的数据没有写入 episodic memory。

---

## 📊 统计

| 严重度 | 数量 |
|:---|:---:|
| 🔴 Critical | 4 |
| 🟡 Major | 5 |
| 🟠 Moderate | 6 |
| 🔵 Minor | 4 |
| **总计** | **19** |

5. 
