# Sprint 22: 极简主义重构与 3-Column 布局 (Minimalist 3-Column UI Refactor)

## 1. 目标与定位 (Goal & Scope)

**Sprint Goal**:
从网文创作者的真实核心路径出发，对前端界面进行大刀阔斧的“减法”，彻底摒弃冗余的“工程师玩具”功能。将界面重塑为极简的 3-Column 布局：**左侧纯净设定 (Lorebook) | 中间纯净阅读 (Manuscript) | 右侧统一控制台 (Control)**。

**定位**:
这是对 Sprint 21 视觉升级的“结构性收尾”。目标是消除一切阻碍阅读沉浸感的悬浮窗、弹框和无关痛痒的遥测数据，让工具的交互逻辑完美贴合“写文 -> 查设 -> 扭转走向 -> 导出成书”的闭环。

## 2. 核心痛点与减法决策 (Pain Points & Subtractions)

通过重新审视用户使用场景，我们识别出以下三个必须被砍掉的伪需求：

1. ❌ **废弃 `CreativeStudio.tsx` (剧情诊断)**：写手需要的是最终导出，而不是看 LLM 评价自己的文章。该底部面板完全占用空间，必须移除。
2. ❌ **废弃居中的 `InterventionPanel.tsx` (幽灵命令行)**：干预输入框不应该悬浮在小说正文上方遮挡视线，它属于“控制”范畴，必须被合并到右侧的“时间线”下方。
3. ❌ **废弃杂乱的 `ProgressPanel.tsx` / `TelemetryPanel.tsx` 遗留**：用户不关心系统推演了多少个节点，只关心当前处于哪条世界线。

## 3. 架构预期：3-Column 极简布局 (Expected Layout)

重构后的主界面 (`App.tsx`) 必须严格遵循三栏结构，不再有任何底部抽屉或居中悬浮窗：

*   **Left Column: 设定集 (Lorebook)**
    *   职责：纯只读的参考 Wiki。
    *   组件：保留原有的卡片化世界观、角色列表。
*   **Middle Column: 故事正文 (Manuscript)**
    *   职责：纯粹的沉浸式阅读区。
    *   组件：仅包含 `StoryFeed.tsx`，依靠划词菜单处理内联操作。移除底部任何干预框。
*   **Right Column: 世界控制台 (Control)**
    *   职责：全局走向控制与产物输出。
    *   结构（自上而下排列）：
        1.  **导出成书 (Publish)**：`ExportPanel.tsx` 提权至右栏顶部。
        2.  **时间线与引导 (Plot Guide)**：`BranchPanel.tsx` 下方紧接重构后的极简 `InterventionPanel.tsx`，实现“边看分支边干预”。
        3.  **关系网 (Network)**：`RelationshipPanel.tsx` 作为折叠画板放在最下方。

## 4. Backlog & TDD 实施计划 (Execution Plan)

严格遵循 `AGENTS.md` 和 TDD 流程：先删代码 -> 调整布局 -> 修复/编写测试 -> 验证通过。

*   [ ] **S22-01: 移除废弃组件与测试 (Subtractions)**
    *   删除 `frontend/src/components/CreativeStudio.tsx` 及其测试。
    *   删除 `frontend/src/components/ProgressPanel.tsx` 及其测试。
    *   删除 `frontend/src/components/TelemetryPanel.tsx` 及其测试（如果 Sprint 21 仍有残留）。
*   [ ] **S22-02: 整合右栏功能区 (Right Column Refactor)**
    *   修改 `App.tsx` 的 Grid 布局。
    *   将 `ExportPanel` 从原先的 Tab 隐藏状态提取出来，作为右栏的常驻顶部功能。
    *   将 `InterventionPanel` 从绝对定位的悬浮窗，改为普通的 Flex 块级元素，并放置在 `BranchPanel` 的下方。
*   [ ] **S22-03: 修复与更新测试 (TDD Validation)**
    *   更新 `App.test.tsx` 以匹配新的 3-Column 结构断言。
    *   更新 `InterventionPanel.test.tsx` 和 `BranchPanel.test.tsx` 适应新的布局层级。
*   [ ] **S22-04: 全局质量门禁验证**
    *   运行 `make lint` 和 `make test-frontend`。

## 5. 验收标准 (Acceptance Criteria)

*   主界面中不再存在任何遮挡 `StoryFeed` (故事正文) 的底部弹框或悬浮输入框。
*   导出按钮清晰可见，且无需切换 Tab 即可点击。
*   剧情引导（干预）输入框与时间线在视觉和逻辑上强绑定在右侧栏。
*   前端所有 20+ 测试用例全部一次性绿灯通过。
