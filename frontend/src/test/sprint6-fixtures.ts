import type { TelemetryEvent, WorldData } from "../types";

export const sprint6WorldFixture: WorldData = {
  title: "断桥同盟",
  premise: "两名敌对继承人在灭国危机前被迫联手。",
  tick: 3,
  is_complete: false,
  factions: [
    { name: "北境军", description: "驻守边境的王朝军团" },
    { name: "赤潮盟", description: "游离于王朝之外的旧部联盟" },
  ],
  locations: [{ name: "断桥渡口", description: "旧战场边缘的渡口" }],
  world_rules: ["第一幕不得直接覆灭王朝"],
  constraints: [
    {
      name: "第一幕不能灭国",
      rule: "在前三个 tick 内不得直接触发王朝覆灭",
      severity: "hard",
      type: "narrative",
    },
  ],
  characters: [
    {
      id: "char-alice",
      name: "阿璃",
      personality: "冷静",
      goals: ["守住边境"],
      status: "alive",
      memory: [],
      relationships: {
        "char-bob": {
          target_id: "char-bob",
          affinity: 20,
          label: "trust",
          note: "在断桥下暂时结盟。",
          updated_at_tick: 3,
        },
      },
    },
    {
      id: "char-bob",
      name: "白夜",
      personality: "执拗",
      goals: ["查明内乱真相"],
      status: "alive",
      memory: [],
      relationships: {
        "char-alice": {
          target_id: "char-alice",
          affinity: 20,
          label: "trust",
          note: "在断桥下暂时结盟。",
          updated_at_tick: 3,
        },
        "char-carol": {
          target_id: "char-carol",
          affinity: -25,
          label: "rival",
          note: "赤霄在雨夜中发动袭击。",
          updated_at_tick: 3,
        },
      },
    },
    {
      id: "char-carol",
      name: "赤霄",
      personality: "沉默",
      goals: ["夺取军印"],
      status: "alive",
      memory: [],
      relationships: {
        "char-bob": {
          target_id: "char-bob",
          affinity: -25,
          label: "rival",
          note: "赤霄在雨夜中发动袭击。",
          updated_at_tick: 3,
        },
      },
    },
  ],
};

export const sprint6TelemetryFixture: TelemetryEvent[] = [
  {
    event_id: "evt-1",
    sim_id: "sim-1",
    tick: 0,
    agent: "director",
    stage: "world_initialized",
    level: "info",
    message: "世界骨架初始化完成",
    payload: { characters: 3 },
    ts: "2026-04-17T10:00:00+00:00",
  },
  {
    event_id: "evt-2",
    sim_id: "sim-1",
    tick: 2,
    agent: "gate_keeper",
    stage: "rejected",
    level: "warning",
    message: "候选事件被边界层拒绝",
    payload: { reason: "第一幕不能灭国" },
    ts: "2026-04-17T10:00:02+00:00",
  },
  {
    event_id: "evt-3",
    sim_id: "sim-1",
    tick: 3,
    agent: "node_detector",
    stage: "node_committed",
    level: "info",
    message: "新故事节点已固化",
    payload: { node_id: "node-3" },
    ts: "2026-04-17T10:00:03+00:00",
  },
];
