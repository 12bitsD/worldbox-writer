import { useEffect, useMemo, useRef, useState } from "react";
import type { StoryNode } from "../types";
import { updateRenderedText } from "../utils/api";
import {
  buildDraftKey,
  clearDraft,
  loadDraft,
  saveDraft,
} from "../utils/draftStore";

interface RichTextEditorProps {
  simId: string;
  activeBranchId: string;
  nodes: StoryNode[];
  onSaved: () => void;
}

function escapeHtml(text: string) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function htmlFromNode(node: StoryNode | undefined) {
  if (!node) return "<p></p>";
  if (node.editor_html) return node.editor_html;
  if (node.rendered_text) {
    return node.rendered_text
      .split(/\n{2,}/)
      .map((paragraph) => `<p>${escapeHtml(paragraph).replaceAll("\n", "<br />")}</p>`)
      .join("");
  }
  return "<p></p>";
}

function plainTextFromHtml(html: string) {
  if (typeof document === "undefined") return html;
  const container = document.createElement("div");
  container.innerHTML = html;
  return (container.textContent ?? "").trim();
}

export default function RichTextEditor({
  simId,
  activeBranchId,
  nodes,
  onSaved,
}: RichTextEditorProps) {
  const editableNodes = useMemo(
    () => nodes.filter((node) => node.rendered_text || node.editor_html),
    [nodes]
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    editableNodes.at(-1)?.id ?? null
  );
  const [html, setHtml] = useState<string>("");
  const [plainText, setPlainText] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [restoredDraftAt, setRestoredDraftAt] = useState<string | null>(null);
  const editorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!editableNodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(editableNodes.at(-1)?.id ?? null);
    }
  }, [editableNodes, selectedNodeId]);

  const selectedNode = editableNodes.find((node) => node.id === selectedNodeId);
  const draftKey = selectedNode
    ? buildDraftKey(simId, activeBranchId, selectedNode.id)
    : null;

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      if (!selectedNode || !draftKey) {
        setHtml("<p></p>");
        setPlainText("");
        setDirty(false);
        setRestoredDraftAt(null);
        return;
      }

      const storedDraft = await loadDraft(draftKey);
      if (cancelled) return;

      const nextHtml = storedDraft?.html || htmlFromNode(selectedNode);
      setHtml(nextHtml);
      setPlainText(storedDraft?.plainText || plainTextFromHtml(nextHtml));
      setDirty(Boolean(storedDraft));
      setRestoredDraftAt(storedDraft?.updatedAt ?? null);
    }

    void hydrate();
    return () => {
      cancelled = true;
    };
  }, [draftKey, selectedNode]);

  useEffect(() => {
    if (editorRef.current && editorRef.current.innerHTML !== html) {
      editorRef.current.innerHTML = html || "<p></p>";
    }
  }, [html]);

  useEffect(() => {
    if (!dirty || !draftKey || !selectedNode) return;
    const timer = window.setTimeout(() => {
      void saveDraft({
        key: draftKey,
        simId,
        branchId: activeBranchId,
        nodeId: selectedNode.id,
        html,
        plainText,
        updatedAt: new Date().toISOString(),
      });
    }, 1200);

    return () => window.clearTimeout(timer);
  }, [activeBranchId, dirty, draftKey, html, plainText, selectedNode, simId]);

  const syncFromEditor = () => {
    const nextHtml = editorRef.current?.innerHTML ?? "<p></p>";
    setHtml(nextHtml);
    setPlainText(plainTextFromHtml(nextHtml));
    setDirty(true);
    setStatus(null);
  };

  const runCommand = (command: string, value?: string) => {
    if (!editorRef.current) return;
    editorRef.current.focus();
    if (typeof document !== "undefined" && typeof document.execCommand === "function") {
      document.execCommand(command, false, value);
      syncFromEditor();
    }
  };

  const handleSave = async () => {
    if (!selectedNode) return;
    setSaving(true);
    setStatus(null);
    try {
      await updateRenderedText(simId, selectedNode.id, {
        rendered_text: plainText,
        rendered_html: html,
      });
      if (draftKey) {
        await clearDraft(draftKey);
      }
      setDirty(false);
      setRestoredDraftAt(null);
      setStatus("已保存到故事节点");
      onSaved();
    } catch (error) {
      setStatus(String(error));
    } finally {
      setSaving(false);
    }
  };

  if (editableNodes.length === 0) {
    return (
      <div style={{ color: "var(--color-text-muted)", fontSize: 12 }}>
        当前还没有可润色的正文节点。
      </div>
    );
  }

  const toolbarButtonStyle: React.CSSProperties = {
    padding: "6px 10px",
    border: "1px solid var(--color-border)",
    background: "var(--color-bg)",
    fontSize: 11,
    cursor: "pointer",
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 16 }}>
      <div style={{ borderRight: "1px solid var(--color-border-light)", paddingRight: 16 }}>
        <div className="label" style={{ marginBottom: 10 }}>
          可编辑正文
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {editableNodes.map((node) => (
            <button
              key={node.id}
              type="button"
              onClick={() => setSelectedNodeId(node.id)}
              style={{
                textAlign: "left",
                padding: "10px 12px",
                border: "1px solid var(--color-border)",
                background:
                  node.id === selectedNodeId ? "var(--color-bg-card)" : "transparent",
                cursor: "pointer",
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 600 }}>{node.title}</div>
              <div style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
                第 {node.tick} 步
              </div>
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div>
            <div className="heading">{selectedNode?.title}</div>
            <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
              富文本润色工作区，支持自动草稿恢复。
            </div>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={saving || !dirty}
            onClick={handleSave}
          >
            {saving ? "保存中..." : "保存润色稿"}
          </button>
        </div>

        {restoredDraftAt && (
          <div
            style={{
              padding: "8px 10px",
              fontSize: 12,
              border: "1px solid rgba(230, 126, 34, 0.25)",
              background: "rgba(230, 126, 34, 0.08)",
              color: "var(--color-warning)",
            }}
          >
            已恢复本地草稿：{new Date(restoredDraftAt).toLocaleString()}
          </div>
        )}

        {status && (
          <div
            style={{
              padding: "8px 10px",
              fontSize: 12,
              border: "1px solid var(--color-border)",
              background: "var(--color-bg-card)",
            }}
          >
            {status}
          </div>
        )}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" style={toolbarButtonStyle} onClick={() => runCommand("bold")}>
            加粗
          </button>
          <button type="button" style={toolbarButtonStyle} onClick={() => runCommand("italic")}>
            斜体
          </button>
          <button
            type="button"
            style={toolbarButtonStyle}
            onClick={() => runCommand("formatBlock", "<blockquote>")}
          >
            引文
          </button>
          <button
            type="button"
            style={toolbarButtonStyle}
            onClick={() => runCommand("insertUnorderedList")}
          >
            列表
          </button>
        </div>

        <div
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          onInput={syncFromEditor}
          style={{
            minHeight: 320,
            border: "1px solid var(--color-border)",
            background: "var(--color-bg-card)",
            padding: 18,
            outline: "none",
            lineHeight: 1.8,
            fontSize: 15,
          }}
        />
      </div>
    </div>
  );
}
