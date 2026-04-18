import type { SimulationState, StoryNode, TelemetryEvent } from "../types";

function mergeNode(existing: StoryNode, incoming: StoryNode): StoryNode {
  return {
    ...existing,
    ...incoming,
    rendered_text: incoming.rendered_text ?? existing.rendered_text ?? null,
    streaming_text:
      incoming.rendered_text != null
        ? undefined
        : incoming.streaming_text ?? existing.streaming_text,
  };
}

export function upsertNode(
  nodes: StoryNode[],
  incoming: StoryNode
): StoryNode[] {
  const index = nodes.findIndex((node) => node.id === incoming.id);
  if (index === -1) {
    return [...nodes, incoming];
  }

  const next = [...nodes];
  next[index] = mergeNode(nodes[index], incoming);
  return next;
}

function resolveStreamingNodeId(
  nodes: StoryNode[],
  requestedNodeId?: string
): string | null {
  if (requestedNodeId && nodes.some((node) => node.id === requestedNodeId)) {
    return requestedNodeId;
  }

  for (let index = nodes.length - 1; index >= 0; index -= 1) {
    const node = nodes[index];
    if (!node.rendered_text) {
      return node.id;
    }
  }

  return nodes.length > 0 ? nodes[nodes.length - 1].id : null;
}

export function appendStreamingToken(
  nodes: StoryNode[],
  token: string,
  nodeId?: string
): StoryNode[] {
  const targetId = resolveStreamingNodeId(nodes, nodeId);
  if (!targetId) {
    return nodes;
  }

  return nodes.map((node) =>
    node.id === targetId
      ? {
          ...node,
          streaming_text: `${node.streaming_text ?? ""}${token}`,
        }
      : node
  );
}

export function mergeTelemetryEvents(
  current: TelemetryEvent[],
  incoming: TelemetryEvent[]
): TelemetryEvent[] {
  const merged = new Map<string, TelemetryEvent>();

  for (const event of current) {
    merged.set(event.event_id, event);
  }
  for (const event of incoming) {
    merged.set(event.event_id, {
      ...merged.get(event.event_id),
      ...event,
    });
  }

  return [...merged.values()].sort((left, right) => {
    if (left.tick !== right.tick) {
      return left.tick - right.tick;
    }
    return left.ts.localeCompare(right.ts);
  });
}

export function mergeSimulationSnapshot(
  current: SimulationState | null,
  incoming: SimulationState
): SimulationState {
  if (!current) {
    return incoming;
  }

  const currentBranchId = current.world?.active_branch_id ?? "main";
  const incomingBranchId = incoming.world?.active_branch_id ?? "main";
  const shouldReplaceTimeline =
    current.sim_id !== incoming.sim_id || currentBranchId !== incomingBranchId;

  let nodes = incoming.nodes;
  let telemetry = incoming.telemetry;

  if (!shouldReplaceTimeline) {
    nodes = current.nodes;
    for (const node of incoming.nodes) {
      nodes = upsertNode(nodes, node);
    }

    telemetry = mergeTelemetryEvents(current.telemetry, incoming.telemetry);
  }

  return {
    ...current,
    ...incoming,
    world: incoming.world ?? current.world,
    nodes,
    telemetry,
    intervention_context:
      incoming.intervention_context ?? current.intervention_context,
    error: incoming.error ?? current.error,
  };
}
