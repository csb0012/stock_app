import { useState } from "react";
import { ChevronDown, ChevronUp, ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";

type Factor = { name: string; short: string; detail: string; impact: "up" | "down" | "neutral"; score: number; max: number };

const IMPACT = {
  up: { color: "var(--green)", Icon: ArrowUpRight },
  down: { color: "var(--red)", Icon: ArrowDownRight },
  neutral: { color: "var(--text-muted)", Icon: Minus },
};

/** 내일 전망 근거: 한 줄 요약 + 펼치면 지표별 상세 */
/** compact: 요약 2줄까지만(전체는 마우스 올리면), 모델 상태 문구는 펼쳤을 때만 — 좁은 카드용 */
export default function PredictionReasons({ pred, defaultOpen = false, compact = false }: { pred: any; defaultOpen?: boolean; compact?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  if (!pred) return null;
  const factors: Factor[] = pred.factors || [];
  const ups = factors.filter((f) => f.impact === "up").length;
  const downs = factors.filter((f) => f.impact === "down").length;

  return (
    <div style={{ marginTop: compact ? 0 : 8 }}>
      {pred.summary && (
        <p className={compact && !open ? "clamp-2" : undefined} title={compact ? pred.summary : undefined}
          style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>{pred.summary}</p>
      )}
      {pred.model_status && (!compact || open) && (
        <p style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5, marginTop: 2 }}>ⓘ {pred.model_status}</p>
      )}
      {factors.length > 0 && (
        <button
          onClick={() => setOpen(!open)}
          style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 4, background: "none", border: "none", padding: 0, cursor: "pointer", color: "var(--accent)", fontSize: 11 }}
        >
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          근거 {open ? "접기" : "자세히"} (상승 {ups} · 하락 {downs} · 중립 {factors.length - ups - downs})
        </button>
      )}
      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
          {factors.map((f) => {
            const { color, Icon } = IMPACT[f.impact] || IMPACT.neutral;
            return (
              <div key={f.name} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12, background: "var(--bg-secondary)", borderRadius: 6, padding: "6px 8px" }}>
                <Icon size={13} style={{ color, flexShrink: 0, marginTop: 1 }} />
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 600, color }}>{f.name}</span>
                  <span style={{ color: "var(--text-secondary)", marginLeft: 6 }}>{f.detail}</span>
                </div>
                <span style={{ color: "var(--text-muted)", fontSize: 11, flexShrink: 0 }}>{f.max ? `${f.score}/${f.max}` : "반영 안 함"}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
