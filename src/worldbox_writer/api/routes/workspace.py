"""Workspace editing routes."""

from __future__ import annotations

from fastapi import APIRouter

from worldbox_writer.api.routes.deps import ApiRouteDeps
from worldbox_writer.api.schemas import (
    AddConstraintRequest,
    SaveWikiRequest,
    UpdateCharacterRequest,
    UpdateNodeRenderedTextRequest,
    UpdateRelationshipRequest,
    UpdateWorldRequest,
)


def build_workspace_router(deps: ApiRouteDeps) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.patch("/simulate/{sim_id}/characters/{character_id}")
    async def update_character(
        sim_id: str, character_id: str, request: UpdateCharacterRequest
    ):
        return deps.workspace_service().update_character(sim_id, character_id, request)

    @router.patch("/simulate/{sim_id}/relationships")
    async def update_relationship(sim_id: str, request: UpdateRelationshipRequest):
        return deps.workspace_service().update_relationship(sim_id, request)

    @router.patch("/simulate/{sim_id}/world")
    async def update_world(sim_id: str, request: UpdateWorldRequest):
        return deps.workspace_service().update_world(sim_id, request)

    @router.post("/simulate/{sim_id}/constraints")
    async def add_constraint(sim_id: str, request: AddConstraintRequest):
        return deps.workspace_service().add_constraint(sim_id, request)

    @router.put("/simulate/{sim_id}/wiki")
    async def save_wiki(sim_id: str, request: SaveWikiRequest):
        return deps.workspace_service().save_wiki(sim_id, request)

    @router.patch("/simulate/{sim_id}/nodes/{node_id}/rendered-text")
    async def update_rendered_text(
        sim_id: str,
        node_id: str,
        request: UpdateNodeRenderedTextRequest,
    ):
        return deps.workspace_service().update_rendered_text(sim_id, node_id, request)

    return router
