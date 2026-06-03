from worldbox_writer.api import server, session, session_store, state
from worldbox_writer.api.services import simulation_service, workspace_service


def test_server_reexports_shared_api_state() -> None:
    assert server._sessions is state._sessions
    assert server._executor is state._executor
    assert server._VALID_PACING_VALUES is state._VALID_PACING_VALUES
    assert server._WORKSPACE_MUTABLE_STATUSES is state._WORKSPACE_MUTABLE_STATUSES


def test_server_reexports_session_helpers() -> None:
    assert server.SimulationSession is session.SimulationSession
    assert server._build_simulation_payload is session.build_simulation_payload
    assert (
        server._merge_rendered_nodes_from_world
        is session.merge_rendered_nodes_from_world
    )


def test_server_reexports_session_store_helpers() -> None:
    assert server._persist_session is session_store.persist_session
    assert server._load_session_into_memory is session_store.load_session_into_memory
    assert server._recover_sessions is session_store.recover_sessions
    assert server._restore_world_at_node is session_store.restore_world_at_node


def test_server_reexports_simulation_service_helpers() -> None:
    assert server._append_telemetry_event is simulation_service.append_telemetry_event
    assert server._branch_status is simulation_service.branch_status
    assert server._restore_branch_world is simulation_service.restore_branch_world


def test_server_reexports_workspace_service_helpers() -> None:
    assert (
        server._ensure_workspace_mutable is workspace_service.ensure_workspace_mutable
    )
    assert server._validate_wiki_request is workspace_service.validate_wiki_request
    assert server._apply_wiki_request is workspace_service.apply_wiki_request
