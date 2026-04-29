"""LLM-as-judge evaluation for prose and story quality.

The rubric lives in prompts. This module only calls the model, parses JSON, and
aggregates scores.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from worldbox_writer.core.dual_loop import SceneScript
from worldbox_writer.utils.llm import chat_completion

DEFAULT_JUDGE_MODEL = "gpt-5.5"
JUDGE_MODEL_ENV = "WORLDBOX_JUDGE_MODEL"


def _resolve_judge_model(model: str | None) -> str:
    return model or os.environ.get(JUDGE_MODEL_ENV, DEFAULT_JUDGE_MODEL)


def build_prose_judge_prompt(text: str) -> str:
    """Build the prose-quality judge prompt."""
    return f"""你是一位资深中文小说编辑，也是一位严厉的质量把关人。
请只根据文本本身评估文笔质量。所有分数使用 0-10 分制：
0=完全失败，5=明显不足但有可修空间，7=合格线（网文可用），8=精品（付费水准），9=出版级，10=经典文学。
7 分是合格线，不要把流畅但平庸的文本打到 7 分以上。

【文笔 12 维评分】
1. sentence_variety: 句式多样性。判断长短句、句型、停顿和语气是否有变化，是否避免机械重复。
2. rhythm_flow: 行文流动性。判断句与句之间是否自然推进，停顿、转折和重音是否顺。
3. pacing_micro: 微观节奏。判断单段内动作、描写、心理和对白的快慢是否有层次。
4. imagery_freshness: 意象/比喻新鲜度。判断比喻、意象、修辞是否具体、新鲜、贴合场景，是否避免陈词滥调。
5. description_precision: 描写精准度。判断场景、动作、感官和情绪是否清楚、有可感细节，是否能让画面立住。
6. sensory_richness: 感官丰富度。判断颜色、质地、声音、气味、温度等是否具体且不过量。
7. dialogue_distinctiveness: 对话辨识度。判断遮去人名后是否能区分角色口吻，是否符合人物处境。
8. dialogue_subtext: 对话潜台词。判断角色是否有回避、试探、压抑、误导或言外之意，而不是直白说明。
9. character_voice_consistency: 角色声音一致性。判断人物口吻、词汇和表达习惯是否稳定。
10. information_density: 信息密度。判断句子是否承载情节、情绪、关系或氛围信息，是否存在注水废句。
11. word_economy: 文字经济性。判断是否用尽量少的句子完成有效表达，是否有空泛重复。
12. tone_consistency: 语调一致性。判断叙述气质、情绪温度和文体选择是否稳定。

【AI 写作问题检测】
请把以下项目作为质量问题评估，分数越高代表问题越少、控制越好：
1. over_metaphor: 过度比喻。警惕每句都堆叠比喻、修辞喧宾夺主、像在炫技。
2. over_parallelism: 过度排比。警惕三连排比成瘾、句式整齐到机械、情绪被格式化。
3. paragraph_fragmentation: 段落断裂。警惕段落之间突然跳转、因果缺失、时间或视角不连贯。
4. readability_issue: 可读性问题。判断是否顺畅、清楚、自然，是否存在读不下去的拗口或混乱段落。
5. ai_flavor: AI味综合。判断整体是否像人类作者有选择地书写，还是显得空泛、平均、模板化。
6. emotional_flatness: 情绪扁平。警惕情绪只有标签、没有行为细节和情境压力。
7. show_dont_tell_violation: 展示不足。警惕用“他很悲伤/她很愤怒”直接解释，而不是用动作、对白和细节呈现。

请返回严格 JSON，不要 Markdown，不要解释 JSON 之外的内容。字段必须齐全：
{{
  "score": 7.5,
  "dimensions": {{
    "sentence_variety": 7.0,
    "rhythm_flow": 7.0,
    "pacing_micro": 7.0,
    "imagery_freshness": 7.0,
    "description_precision": 7.0,
    "sensory_richness": 7.0,
    "dialogue_distinctiveness": 7.0,
    "dialogue_subtext": 7.0,
    "character_voice_consistency": 7.0,
    "information_density": 7.0,
    "word_economy": 7.0,
    "tone_consistency": 7.0
  }},
  "ai_issues": {{
    "over_metaphor": 7.0,
    "over_parallelism": 7.0,
    "paragraph_fragmentation": 7.0,
    "readability_issue": 7.0,
    "ai_flavor": 7.0,
    "emotional_flatness": 7.0,
    "show_dont_tell_violation": 7.0
  }},
  "reasoning": "50字以内说明主要优点和最主要问题"
}}

待评测文本：
---
{text}
---
"""


def build_story_judge_prompt(text: str) -> str:
    """Build the story-quality judge prompt."""
    return f"""你是一位资深故事编辑，负责评估小说片段或场景脚本的故事力。
请只根据文本本身评估，不补写设定，不假设缺失内容。所有分数使用 0-10 分制：
0=完全失败，5=明显不足但有可修空间，7=合格线（网文可用），8=精品（付费水准），9=出版级，10=经典文学。
7 分是合格线，不要把只是完整但缺少吸引力的文本打到 7 分以上。

【故事力 12 维评分】
1. hook: 钩子。判断开场或核心信息是否制造阅读欲望，是否让读者想继续读。
2. inciting_incident_clarity: 诱因清晰度。判断改变局面的触发事件是否明确、有压力且不可忽略。
3. rising_action_tension: 上升动作张力。判断阻碍是否逐步加码，场景是否越推进越紧。
4. structural_completeness: 结构完整性。判断开端、发展、变化、收束是否成形，节奏是否塌掉。
5. conflict_density: 冲突密度。判断外部冲突、人物关系张力、目标阻碍是否充分且集中；同时观察 stakes_clarity 是否足够。
6. conflict_variety: 冲突类型丰富度。判断是否有行动、关系、价值、信息差等不同层面的冲突。
7. twist_effectiveness: 反转有效性。判断转折是否意外但合理，并检查 twist_foreshadowing 是否让揭示有伏笔。
8. character_motivation_consistency: 人物动机一致性。判断人物决策是否能被读者倒推解释，是否符合欲望、恐惧和处境。
9. character_arc_progression: 人物弧线推进。判断人物是否因事件产生选择、代价、认知或关系上的变化。
10. antagonist_strength: 对抗力量强度。判断反派、环境、制度或命运压力是否足够具体且有压迫感。
11. suspense_maintenance: 悬念维持。判断关键问题是否持续牵引读者，是否保留下一步期待。
12. world_immersion: 世界沉浸感。判断设定、场景和规则是否通过行动显现，而非空泛说明。

请返回严格 JSON，不要 Markdown，不要解释 JSON 之外的内容。字段必须齐全：
{{
  "score": 7.5,
  "dimensions": {{
    "hook": 7.0,
    "inciting_incident_clarity": 7.0,
    "rising_action_tension": 7.0,
    "structural_completeness": 7.0,
    "conflict_density": 7.0,
    "conflict_variety": 7.0,
    "twist_effectiveness": 7.0,
    "character_motivation_consistency": 7.0,
    "character_arc_progression": 7.0,
    "antagonist_strength": 7.0,
    "suspense_maintenance": 7.0,
    "world_immersion": 7.0
  }},
  "reasoning": "50字以内说明主要优点和最主要问题"
}}

待评测文本：
---
{text}
---
"""


def _fenced_blocks(raw: str) -> list[str]:
    blocks: list[str] = []
    cursor = 0
    fence = "```"
    while True:
        start = raw.find(fence, cursor)
        if start == -1:
            break
        content_start = raw.find("\n", start + len(fence))
        if content_start == -1:
            break
        end = raw.find(fence, content_start + 1)
        if end == -1:
            break
        blocks.append(raw[content_start + 1 : end].strip())
        cursor = end + len(fence)
    return blocks


def _json_candidates(raw: str) -> list[str]:
    candidates = _fenced_blocks(raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1].strip())
    candidates.append(raw.strip())
    return candidates


def parse_judge_response(raw: str) -> dict[str, Any]:
    """Parse a judge response, falling back to a neutral parse error result."""
    for candidate in _json_candidates(raw):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {"score": 5.0, "error": "parse_failed", "raw": raw}


def _score(value: Any, default: float = 5.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _nonspace_length(text: str) -> int:
    return sum(1 for character in text if not character.isspace())


def _dialogue_character_count(text: str) -> int:
    count = 0
    closing_quote = ""
    quote_pairs = {"“": "”", "‘": "’", '"': '"', "'": "'"}
    for character in text:
        if closing_quote:
            if character == closing_quote:
                closing_quote = ""
            elif not character.isspace():
                count += 1
            continue
        if character in quote_pairs:
            closing_quote = quote_pairs[character]
    return count


def _count_phrase(text: str, phrase: str) -> int:
    count = 0
    cursor = 0
    while True:
        index = text.find(phrase, cursor)
        if index == -1:
            return count
        count += 1
        cursor = index + len(phrase)


def objective_metrics(text: str) -> dict[str, Any]:
    """Compute deterministic prose metrics for comparable eval reports."""
    normalized = str(text or "")
    word_count = _nonspace_length(normalized)
    dialogue_chars = _dialogue_character_count(normalized)
    metaphor_markers = ("仿佛", "好像", "如同", "宛如", "犹如", "像")
    metaphor_count = sum(
        _count_phrase(normalized, marker) for marker in metaphor_markers
    )
    dialogue_ratio = dialogue_chars / word_count if word_count else 0.0
    metaphor_density = metaphor_count * 1000 / word_count if word_count else 0.0
    return {
        "word_count": word_count,
        "dialogue_char_count": dialogue_chars,
        "dialogue_ratio": round(dialogue_ratio, 4),
        "metaphor_count": metaphor_count,
        "metaphor_density_per_1k": round(metaphor_density, 2),
    }


def _call_judge_llm(prompt: str, *, model: str, max_tokens: int) -> str:
    return chat_completion(
        messages=[
            {"role": "system", "content": "你是严格的小说质量评委，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        role="narrator",
        model=model,
        temperature=0.2,
        max_tokens=max_tokens,
    )


def judge_prose(text: str, model: str | None = None) -> dict[str, Any]:
    """Judge prose quality with an LLM."""
    selected_model = _resolve_judge_model(model)
    try:
        raw = _call_judge_llm(
            build_prose_judge_prompt(text),
            model=selected_model,
            max_tokens=1300,
        )
        parsed = parse_judge_response(raw)
    except Exception as exc:
        parsed = {"score": 5.0, "error": "llm_call_failed", "raw": str(exc)}

    return {
        "score": _score(parsed.get("score")),
        "dimensions": _dict_value(parsed.get("dimensions")),
        "ai_issues": _dict_value(parsed.get("ai_issues")),
        "reasoning": str(parsed.get("reasoning") or ""),
        "model": selected_model,
        "error": parsed.get("error"),
    }


def judge_story(text: str, model: str | None = None) -> dict[str, Any]:
    """Judge story quality with an LLM."""
    selected_model = _resolve_judge_model(model)
    try:
        raw = _call_judge_llm(
            build_story_judge_prompt(text),
            model=selected_model,
            max_tokens=1100,
        )
        parsed = parse_judge_response(raw)
    except Exception as exc:
        parsed = {"score": 5.0, "error": "llm_call_failed", "raw": str(exc)}

    return {
        "score": _score(parsed.get("score")),
        "dimensions": _dict_value(parsed.get("dimensions")),
        "reasoning": str(parsed.get("reasoning") or ""),
        "model": selected_model,
        "error": parsed.get("error"),
    }


def _scene_script_story_text(script: SceneScript) -> str:
    parts = [
        f"title: {script.title}",
        f"summary: {script.summary}",
    ]
    for index, beat in enumerate(script.beats, start=1):
        parts.append(f"beat {index} summary: {beat.summary}")
        parts.append(f"beat {index} outcome: {beat.outcome}")
    return "\n".join(part for part in parts if part.strip())


def _scene_script_beat_texts(script: SceneScript) -> list[str]:
    texts: list[str] = []
    for beat in script.beats:
        beat_text = "\n".join(part for part in (beat.summary, beat.outcome) if part)
        if beat_text.strip():
            texts.append(beat_text)
    return texts


def judge_scene_script(script: SceneScript, model: str | None = None) -> dict[str, Any]:
    """Judge a SceneScript by combining story and beat-level prose scores."""
    selected_model = _resolve_judge_model(model)
    story = judge_story(_scene_script_story_text(script), model=selected_model)

    prose_results = [
        judge_prose(beat_text, model=selected_model)
        for beat_text in _scene_script_beat_texts(script)
    ]
    prose_score = (
        sum(result["score"] for result in prose_results) / len(prose_results)
        if prose_results
        else 5.0
    )
    composite_score = round(story["score"] * 0.6 + prose_score * 0.4, 2)

    return {
        "score": composite_score,
        "composite_score": composite_score,
        "script_id": script.script_id,
        "scene_id": script.scene_id,
        "story": story,
        "prose": {
            "score": round(prose_score, 2),
            "beat_results": prose_results,
        },
        "model": selected_model,
        "error": story.get("error"),
    }


def _judge_item(item: dict[str, Any], *, model: str) -> dict[str, Any]:
    item_type = item.get("type", "prose")
    if item_type == "story":
        return judge_story(str(item.get("text") or ""), model=model)
    if item_type == "scene_script":
        script = item.get("script")
        if isinstance(script, SceneScript):
            return judge_scene_script(script, model=model)
        return {"score": 5.0, "model": model, "error": "invalid_script"}
    if item_type == "simulation_chapter":
        script = item.get("scene_script") or item.get("script")
        if isinstance(script, dict):
            try:
                script = SceneScript.model_validate(script)
            except Exception:
                script = None
        rendered_text = str(item.get("rendered_text") or item.get("text") or "")
        if not isinstance(script, SceneScript):
            story_result = {
                "score": 5.0,
                "dimensions": {},
                "reasoning": "",
                "model": model,
                "error": "invalid_script",
            }
            scene_script_result = {
                "score": 5.0,
                "story": story_result,
                "model": model,
                "error": "invalid_script",
            }
        else:
            scene_script_result = judge_scene_script(script, model=model)
            story_result = _dict_value(scene_script_result.get("story"))
        prose_result = judge_prose(rendered_text, model=model)
        story_score = _score(story_result.get("score"))
        prose_score = _score(prose_result.get("score"))
        composite_score = round((story_score + prose_score) / 2, 2)
        return {
            "score": composite_score,
            "story": story_result,
            "scene_script": scene_script_result,
            "prose": prose_result,
            "objective_metrics": objective_metrics(rendered_text),
            "model": model,
            "error": scene_script_result.get("error") or prose_result.get("error"),
        }
    return judge_prose(str(item.get("text") or ""), model=model)


def batch_judge(
    items: list[dict[str, Any]],
    model: str | None = None,
    max_concurrency: int = 3,
) -> list[dict[str, Any]]:
    """Evaluate multiple judge items with bounded worker concurrency."""
    selected_model = _resolve_judge_model(model)
    workers = max(1, max_concurrency)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda item: _judge_item(item, model=selected_model),
                items,
            )
        )
