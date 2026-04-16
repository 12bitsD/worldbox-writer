import { useState } from "react";

interface StartPanelProps {
  onStart: (premise: string, maxTicks: number) => void;
  loading: boolean;
}

const EXAMPLES = [
  "一个被门派抛弃的天才修仙者，在废土赛博朋克世界中寻求复仇",
  "末日后的地下城市，三个势力争夺最后的净水源",
  "古代侠客发现自己的师父是幕后大反派，决定揭露真相",
  "星际殖民地上，AI 觉醒后与人类签订了一份奇怪的协议",
];

export function StartPanel({ onStart, loading }: StartPanelProps) {
  const [premise, setPremise] = useState("");
  const [maxTicks, setMaxTicks] = useState(8);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (premise.trim()) onStart(premise.trim(), maxTicks);
  };

  return (
    <div
      className="watermark-bg"
      style={{
        minHeight: "calc(100vh - 52px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 40,
      }}
    >
      <div style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: 640 }}>
        {/* Title block */}
        <div style={{ marginBottom: 48 }}>
          <div className="display-xl" style={{ marginBottom: 16 }}>
            WORLD
            <br />
            BOX
          </div>
          <p style={{ color: "var(--color-text-secondary)", fontSize: 16, maxWidth: 400 }}>
            输入一句话，Agent 集群将为你构建并推演一个完整的故事世界。你是上帝，你来干预。
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <div className="label" style={{ marginBottom: 8 }}>
              故事前提
            </div>
            <textarea
              className="input textarea"
              placeholder="描述你的故事世界和主角，一句话即可..."
              value={premise}
              onChange={(e) => setPremise(e.target.value)}
              rows={3}
              disabled={loading}
            />
          </div>

          {/* Examples */}
          <div style={{ marginBottom: 20 }}>
            <div className="label" style={{ marginBottom: 8 }}>
              示例前提
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {EXAMPLES.map((ex, i) => (
                <button
                  key={i}
                  type="button"
                  className="btn btn-ghost"
                  style={{
                    justifyContent: "flex-start",
                    textAlign: "left",
                    fontSize: 12,
                    padding: "6px 10px",
                    fontWeight: 400,
                  }}
                  onClick={() => setPremise(ex)}
                  disabled={loading}
                >
                  <span style={{ color: "var(--color-text-muted)", minWidth: 20 }}>
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {ex}
                </button>
              ))}
            </div>
          </div>

          {/* Ticks selector */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              marginBottom: 24,
              padding: "12px 16px",
              border: "1px solid var(--color-border)",
            }}
          >
            <div>
              <div className="label">推演深度</div>
              <div style={{ fontSize: 12, color: "var(--color-text-secondary)", marginTop: 2 }}>
                故事节点数量（越多越详细）
              </div>
            </div>
            <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
              {[4, 6, 8, 12].map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`btn ${maxTicks === t ? "btn-primary" : ""}`}
                  style={{ padding: "4px 12px", fontSize: 12 }}
                  onClick={() => setMaxTicks(t)}
                  disabled={loading}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%", justifyContent: "center", padding: "12px 24px", fontSize: 14 }}
            disabled={loading || !premise.trim()}
          >
            {loading ? "初始化世界中..." : "开始推演 →"}
          </button>
        </form>
      </div>
    </div>
  );
}
