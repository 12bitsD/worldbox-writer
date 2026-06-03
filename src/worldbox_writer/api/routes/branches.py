"""Branch timeline routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from worldbox_writer.api.routes.deps import ApiRouteDeps
from worldbox_writer.api.schemas import (
    CreateBranchRequest,
    SwitchBranchRequest,
    UpdateBranchPacingRequest,
)


def build_branch_router(deps: ApiRouteDeps) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/simulate/{sim_id}/branch")
    async def create_branch(sim_id: str, request: CreateBranchRequest):
        return deps.branch_service().create_branch(
            sim_id, request, asyncio.get_running_loop()
        )

    @router.post("/simulate/{sim_id}/branch/switch")
    async def switch_branch(sim_id: str, request: SwitchBranchRequest):
        return deps.branch_service().switch_branch(sim_id, request)

    @router.get("/simulate/{sim_id}/branch/compare")
    async def compare_branches(sim_id: str):
        return deps.branch_service().compare_branches(sim_id)

    @router.post("/simulate/{sim_id}/branch/pacing")
    async def update_branch_pacing(sim_id: str, request: UpdateBranchPacingRequest):
        return deps.branch_service().update_pacing(sim_id, request)

    return router
