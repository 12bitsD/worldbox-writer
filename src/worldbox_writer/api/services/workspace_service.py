"""Workspace editing service for mutable simulation state."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from fastapi import HTTPException

from worldbox_writer.api.core.serialization import serialize_node, serialize_world
from worldbox_writer.api.schemas import (
    AddConstraintRequest,
    SaveWikiRequest,
    UpdateCharacterRequest,
    UpdateNodeRenderedTextRequest,
    UpdateRelationshipRequest,
    UpdateWorldRequest,
    WikiCharacterPayload,
    WikiEntityPayload,
)
from worldbox_writer.api.services.simulation_service import append_telemetry_event
from worldbox_writer.api.session import SimulationSession, upsert_rendered_node
from worldbox_writer.api.session_store import (
    load_session_into_memory,
    persist_session,
)
from worldbox_writer.api.state import _WORKSPACE_MUTABLE_STATUSES
from worldbox_writer.core.models import (
    Character,
    CharacterStatus,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    RelationshipLabel,
)


def ensure_workspace_mutable(session: SimulationSession, action_label: str) -> None:
    if session.status not in _WORKSPACE_MUTABLE_STATUSES:
        allowed = ", ".join(sorted(_WORKSPACE_MUTABLE_STATUSES))
        raise HTTPException(
            status_code=400,
            detail=(
                f"当前状态为 {session.status}，只能在干预暂停或已完成等创作阶段（{allowed}）"
                f"下{action_label}，运行中的推演不能修改创作工作台内容。"
            ),
        )


def wiki_issue(level: str, path: str, message: str) -> Dict[str, str]:
    return {"level": level, "path": path, "message": message}


def validate_wiki_request(
    session: SimulationSession, request: SaveWikiRequest
) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    if not request.title.strip():
        issues.append(wiki_issue("error", "title", "作品标题不能为空"))
    if not request.premise.strip():
        issues.append(wiki_issue("error", "premise", "故事前提不能为空"))

    for index, rule in enumerate(request.world_rules):
        if not rule.strip():
            issues.append(
                wiki_issue("error", f"world_rules[{index}]", "世界规则不能是空字符串")
            )

    def validate_unique_names(
        items: Sequence[WikiEntityPayload | WikiCharacterPayload],
        path: str,
        label: str,
    ) -> None:
        seen: Dict[str, int] = {}
        for index, item in enumerate(items):
            name = item.name.strip()
            if not name:
                issues.append(
                    wiki_issue("error", f"{path}[{index}].name", f"{label}名称不能为空")
                )
                continue
            if name in seen:
                first_index = seen[name]
                issues.append(
                    wiki_issue(
                        "error",
                        f"{path}[{index}].name",
                        f"{label}名称重复：与 {path}[{first_index}] 冲突",
                    )
                )
            else:
                seen[name] = index

    validate_unique_names(request.characters, "characters", "角色")
    validate_unique_names(request.factions, "factions", "势力")
    validate_unique_names(request.locations, "locations", "地点")

    if session.world is None:
        raise RuntimeError("Cannot apply wiki request: session.world is None")
    referenced_character_ids = {
        character_id
        for node in session.world.nodes.values()
        for character_id in node.character_ids
    }
    provided_character_ids = {
        character.id for character in request.characters if character.id is not None
    }
    missing_character_ids = sorted(referenced_character_ids - provided_character_ids)
    if missing_character_ids:
        issues.append(
            wiki_issue(
                "error",
                "characters",
                "不能删除已被历史节点引用的角色；请保留其 ID 后再编辑设定。",
            )
        )

    for index, item in enumerate(request.factions):
        if not item.description.strip():
            issues.append(
                wiki_issue(
                    "warning",
                    f"factions[{index}].description",
                    "建议为势力补充说明，避免后续检索召回过弱。",
                )
            )
    for index, item in enumerate(request.locations):
        if not item.description.strip():
            issues.append(
                wiki_issue(
                    "warning",
                    f"locations[{index}].description",
                    "建议为地点补充说明，方便世界设定检索。",
                )
            )

    return issues


def materialize_character(
    payload: WikiCharacterPayload, existing: Optional[Character]
) -> Character:
    try:
        status = CharacterStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"无效的角色状态: {payload.status}"
        ) from exc

    character_id = payload.id or (str(existing.id) if existing else None)
    kwargs: Dict[str, Any] = {
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "personality": payload.personality.strip(),
        "goals": [goal.strip() for goal in payload.goals if goal.strip()],
        "status": status,
        "relationships": existing.relationships if existing else {},
        "memory": existing.memory if existing else [],
        "metadata": {**(existing.metadata if existing else {}), **payload.metadata},
    }
    if character_id:
        kwargs["id"] = character_id
    return Character(**kwargs)


def apply_wiki_request(session: SimulationSession, request: SaveWikiRequest) -> None:
    existing_world = session.world
    if existing_world is None:
        raise RuntimeError("Cannot apply wiki request: session.world is None")
    existing_characters = existing_world.characters
    next_characters: Dict[str, Character] = {}
    for payload in request.characters:
        existing = existing_characters.get(payload.id or "")
        character = materialize_character(payload, existing)
        next_characters[str(character.id)] = character

    existing_world.title = request.title.strip()
    existing_world.premise = request.premise.strip()
    existing_world.world_rules = [
        rule.strip() for rule in request.world_rules if rule.strip()
    ]
    existing_world.factions = [
        {
            "name": item.name.strip(),
            "description": item.description.strip(),
            **item.metadata,
        }
        for item in request.factions
    ]
    existing_world.locations = [
        {
            "name": item.name.strip(),
            "description": item.description.strip(),
            **item.metadata,
        }
        for item in request.locations
    ]
    existing_world.characters = next_characters


class WorkspaceService:
    def _load_mutable_session(
        self, sim_id: str, action_label: str
    ) -> SimulationSession:
        session = load_session_into_memory(sim_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
        ensure_workspace_mutable(session, action_label)
        if not session.world:
            raise HTTPException(status_code=400, detail="世界尚未初始化")
        return session

    def update_character(
        self, sim_id: str, character_id: str, request: UpdateCharacterRequest
    ) -> Dict[str, Any]:
        session = self._load_mutable_session(sim_id, "编辑角色")
        assert session.world is not None

        char = session.world.get_character(character_id)
        if not char:
            raise HTTPException(status_code=404, detail=f"角色 {character_id} 不存在")

        if request.name is not None:
            char.name = request.name
        if request.description is not None:
            char.description = request.description
        if request.personality is not None:
            char.personality = request.personality
        if request.goals is not None:
            char.goals = request.goals
        if request.status is not None:
            try:
                char.status = CharacterStatus(request.status)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"无效的角色状态: {request.status}"
                )

        session.world.characters[character_id] = char
        persist_session(session)

        return {
            "message": "角色已更新",
            "character": {
                "id": str(char.id),
                "name": char.name,
                "personality": char.personality,
                "goals": char.goals,
                "status": char.status.value,
            },
        }

    def update_relationship(
        self, sim_id: str, request: UpdateRelationshipRequest
    ) -> Dict[str, Any]:
        session = self._load_mutable_session(sim_id, "编辑角色关系")
        assert session.world is not None

        source = session.world.get_character(request.source_character_id)
        target = session.world.get_character(request.target_character_id)
        if not source or not target:
            raise HTTPException(status_code=404, detail="关系两端角色不存在")
        if source.id == target.id:
            raise HTTPException(status_code=400, detail="不能给同一个角色建立自关系")

        try:
            label = RelationshipLabel(request.label)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"无效的关系标签: {request.label}，允许值为 "
                    f"{', '.join(label.value for label in RelationshipLabel)}"
                ),
            )

        affinity = max(-100, min(100, request.affinity))
        source.update_relationship(
            str(target.id),
            label.value,
            affinity=affinity,
            label=label,
            note=request.note,
            updated_at_tick=session.world.tick,
        )
        session.world.characters[str(source.id)] = source

        if request.bidirectional:
            target.update_relationship(
                str(source.id),
                label.value,
                affinity=affinity,
                label=label,
                note=request.note,
                updated_at_tick=session.world.tick,
            )
            session.world.characters[str(target.id)] = target

        persist_session(session)

        return {
            "message": "关系已更新",
            "relationship": source.relationships[str(target.id)].model_dump(
                mode="json"
            ),
        }

    def update_world(self, sim_id: str, request: UpdateWorldRequest) -> Dict[str, Any]:
        session = self._load_mutable_session(sim_id, "编辑世界设定")
        assert session.world is not None

        if request.title is not None:
            session.world.title = request.title
        if request.premise is not None:
            session.world.premise = request.premise
        if request.world_rules is not None:
            session.world.world_rules = request.world_rules

        persist_session(session)

        return {
            "message": "世界设定已更新",
            "world": {
                "title": session.world.title,
                "premise": session.world.premise,
                "world_rules": session.world.world_rules,
            },
        }

    def add_constraint(
        self, sim_id: str, request: AddConstraintRequest
    ) -> Dict[str, Any]:
        session = self._load_mutable_session(sim_id, "添加约束")
        assert session.world is not None

        try:
            constraint_type = ConstraintType(request.constraint_type)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"无效的约束类型: {request.constraint_type}"
            )
        try:
            severity = ConstraintSeverity(request.severity)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"无效的严重级别: {request.severity}"
            )

        constraint = Constraint(
            name=request.name,
            description=request.description,
            constraint_type=constraint_type,
            severity=severity,
            rule=request.rule,
        )
        session.world.add_constraint(constraint)
        persist_session(session)

        return {
            "message": "约束已添加",
            "constraint": {
                "id": str(constraint.id),
                "name": constraint.name,
                "rule": constraint.rule,
                "severity": constraint.severity.value,
                "type": constraint.constraint_type.value,
            },
        }

    def save_wiki(self, sim_id: str, request: SaveWikiRequest) -> Dict[str, Any]:
        session = self._load_mutable_session(sim_id, "保存 Wiki 设定")
        assert session.world is not None

        issues = validate_wiki_request(session, request)
        blocking_errors = [issue for issue in issues if issue["level"] == "error"]
        if blocking_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Wiki 校验失败，请先修正错误项。",
                    "issues": blocking_errors,
                },
            )

        apply_wiki_request(session, request)
        append_telemetry_event(
            session,
            {
                "tick": session.world.tick,
                "agent": "user",
                "stage": "wiki_saved",
                "span_kind": "user",
                "message": "设定 Wiki 已保存",
                "payload": {
                    "characters": len(session.world.characters),
                    "factions": len(session.world.factions),
                    "locations": len(session.world.locations),
                    "issues": issues,
                },
            },
        )
        persist_session(session)
        return {
            "message": "Wiki 已保存",
            "issues": issues,
            "world": serialize_world(session.world),
        }

    def update_rendered_text(
        self, sim_id: str, node_id: str, request: UpdateNodeRenderedTextRequest
    ) -> Dict[str, Any]:
        session = self._load_mutable_session(sim_id, "保存正文润色")
        assert session.world is not None

        node = session.world.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")

        node.rendered_text = request.rendered_text
        node.is_rendered = True
        if request.rendered_html is not None:
            node.metadata["editor_html"] = request.rendered_html
        session.world.nodes[node_id] = node

        node_payload = serialize_node(node, session.world)
        upsert_rendered_node(session, node_payload)
        append_telemetry_event(
            session,
            {
                "tick": session.world.tick,
                "agent": "user",
                "stage": "rendered_text_updated",
                "span_kind": "user",
                "message": "正文润色稿已保存",
                "payload": {
                    "node_id": node_id,
                    "text_length": len(request.rendered_text),
                },
                "branch_id": node.branch_id,
            },
        )
        persist_session(session)

        return {
            "message": "正文润色稿已保存",
            "node": node_payload,
        }
