// WorldBox Writer — EditPanel Component
// Allows editing characters and world settings during intervention pause

import { useState } from "react";
import type { WorldData } from "../types";
import { updateCharacter, updateWorld, addConstraint } from "../utils/api";

interface EditPanelProps {
  simId: string;
  world: WorldData;
  onUpdated: () => void;
}

export function EditPanel({ simId, world, onUpdated }: EditPanelProps) {
  const [expandedChar, setExpandedChar] = useState<string | null>(null);
  const [showWorldEdit, setShowWorldEdit] = useState(false);
  const [showConstraintForm, setShowConstraintForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Character edit state
  const [charEdits, setCharEdits] = useState<Record<string, {
    name: string;
    personality: string;
    goals: string;
  }>>({});

  // World edit state
  const [worldTitle, setWorldTitle] = useState(world.title);
  const [worldPremise, setWorldPremise] = useState(world.premise);
  const [worldRules, setWorldRules] = useState(world.world_rules.join("\n"));

  // Constraint form
  const [newConstraint, setNewConstraint] = useState({
    name: "",
    description: "",
    rule: "",
  });

  const initCharEdit = (charId: string) => {
    if (!charEdits[charId]) {
      const char = world.characters.find((c) => c.id === charId);
      if (char) {
        setCharEdits((prev) => ({
          ...prev,
          [charId]: {
            name: char.name,
            personality: char.personality,
            goals: char.goals.join("\n"),
          },
        }));
      }
    }
    setExpandedChar(expandedChar === charId ? null : charId);
  };

  const saveCharacter = async (charId: string) => {
    const edit = charEdits[charId];
    if (!edit) return;
    setSaving(true);
    setError(null);
    try {
      await updateCharacter(simId, charId, {
        name: edit.name,
        personality: edit.personality,
        goals: edit.goals.split("\n").filter((g) => g.trim()),
      });
      onUpdated();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const saveWorld = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateWorld(simId, {
        title: worldTitle,
        premise: worldPremise,
        world_rules: worldRules.split("\n").filter((r) => r.trim()),
      });
      setShowWorldEdit(false);
      onUpdated();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const saveConstraint = async () => {
    if (!newConstraint.name || !newConstraint.rule) return;
    setSaving(true);
    setError(null);
    try {
      await addConstraint(simId, {
        name: newConstraint.name,
        description: newConstraint.description || newConstraint.name,
        constraint_type: "narrative",
        severity: "hard",
        rule: newConstraint.rule,
      });
      setNewConstraint({ name: "", description: "", rule: "" });
      setShowConstraintForm(false);
      onUpdated();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "6px 8px",
    fontSize: 12,
    background: "var(--color-bg)",
    border: "1px solid var(--color-border)",
    color: "var(--color-text)",
    outline: "none",
    boxSizing: "border-box",
    fontFamily: "inherit",
  };

  const btnStyle: React.CSSProperties = {
    padding: "5px 12px",
    fontSize: 11,
    cursor: saving ? "wait" : "pointer",
    border: "1px solid var(--color-border)",
    background: "var(--color-bg)",
    color: "var(--color-text)",
  };

  return (
    <div
      style={{
        borderTop: "1px solid var(--color-border)",
        background: "rgba(0,0,0,0.02)",
        padding: "16px 24px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div className="label">编辑设定</div>
        <span style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
          干预暂停时可修改
        </span>
      </div>

      {error && (
        <div
          style={{
            padding: "6px 10px",
            marginBottom: 8,
            fontSize: 11,
            color: "var(--color-danger)",
            background: "rgba(192, 57, 43, 0.06)",
            border: "1px solid rgba(192, 57, 43, 0.2)",
          }}
        >
          {error}
        </div>
      )}

      {/* Characters */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginBottom: 6 }}>
          角色
        </div>
        {world.characters.map((char) => (
          <div key={char.id} style={{ marginBottom: 4 }}>
            <div
              onClick={() => initCharEdit(char.id)}
              style={{
                padding: "6px 8px",
                cursor: "pointer",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: 12,
                background: expandedChar === char.id ? "var(--color-bg)" : "transparent",
                border: "1px solid",
                borderColor: expandedChar === char.id ? "var(--color-border)" : "transparent",
              }}
            >
              <span>{char.name}</span>
              <span style={{ color: "var(--color-text-muted)", fontSize: 10 }}>
                {expandedChar === char.id ? "收起" : "编辑"}
              </span>
            </div>

            {expandedChar === char.id && charEdits[char.id] && (
              <div
                style={{
                  padding: "8px",
                  border: "1px solid var(--color-border)",
                  borderTop: "none",
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                <label style={{ fontSize: 11, color: "var(--color-text-muted)" }}>名字</label>
                <input
                  style={inputStyle}
                  value={charEdits[char.id].name}
                  onChange={(e) =>
                    setCharEdits((prev) => ({
                      ...prev,
                      [char.id]: { ...prev[char.id], name: e.target.value },
                    }))
                  }
                />
                <label style={{ fontSize: 11, color: "var(--color-text-muted)" }}>性格</label>
                <input
                  style={inputStyle}
                  value={charEdits[char.id].personality}
                  onChange={(e) =>
                    setCharEdits((prev) => ({
                      ...prev,
                      [char.id]: { ...prev[char.id], personality: e.target.value },
                    }))
                  }
                />
                <label style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
                  目标（每行一个）
                </label>
                <textarea
                  style={{ ...inputStyle, minHeight: 48, resize: "vertical" }}
                  value={charEdits[char.id].goals}
                  onChange={(e) =>
                    setCharEdits((prev) => ({
                      ...prev,
                      [char.id]: { ...prev[char.id], goals: e.target.value },
                    }))
                  }
                />
                <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                  <button
                    style={btnStyle}
                    disabled={saving}
                    onClick={() => saveCharacter(char.id)}
                  >
                    保存角色
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* World settings */}
      <div style={{ marginBottom: 12 }}>
        <div
          onClick={() => setShowWorldEdit(!showWorldEdit)}
          style={{
            fontSize: 11,
            color: "var(--color-text-muted)",
            cursor: "pointer",
            marginBottom: showWorldEdit ? 6 : 0,
          }}
        >
          世界设定 {showWorldEdit ? "收起" : "编辑"}
        </div>
        {showWorldEdit && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ fontSize: 11, color: "var(--color-text-muted)" }}>标题</label>
            <input
              style={inputStyle}
              value={worldTitle}
              onChange={(e) => setWorldTitle(e.target.value)}
            />
            <label style={{ fontSize: 11, color: "var(--color-text-muted)" }}>前提</label>
            <textarea
              style={{ ...inputStyle, minHeight: 48, resize: "vertical" }}
              value={worldPremise}
              onChange={(e) => setWorldPremise(e.target.value)}
            />
            <label style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
              世界规则（每行一条）
            </label>
            <textarea
              style={{ ...inputStyle, minHeight: 64, resize: "vertical" }}
              value={worldRules}
              onChange={(e) => setWorldRules(e.target.value)}
            />
            <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
              <button style={btnStyle} disabled={saving} onClick={saveWorld}>
                保存设定
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add constraint */}
      <div>
        <div
          onClick={() => setShowConstraintForm(!showConstraintForm)}
          style={{
            fontSize: 11,
            color: "var(--color-text-muted)",
            cursor: "pointer",
            marginBottom: showConstraintForm ? 6 : 0,
          }}
        >
          添加约束 {showConstraintForm ? "收起" : "+"}
        </div>
        {showConstraintForm && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <input
              style={inputStyle}
              placeholder="约束名称"
              value={newConstraint.name}
              onChange={(e) =>
                setNewConstraint((prev) => ({ ...prev, name: e.target.value }))
              }
            />
            <input
              style={inputStyle}
              placeholder="规则描述（如：主角不能在第一幕死亡）"
              value={newConstraint.rule}
              onChange={(e) =>
                setNewConstraint((prev) => ({ ...prev, rule: e.target.value }))
              }
            />
            <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
              <button
                style={btnStyle}
                disabled={saving || !newConstraint.name || !newConstraint.rule}
                onClick={saveConstraint}
              >
                添加约束
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
