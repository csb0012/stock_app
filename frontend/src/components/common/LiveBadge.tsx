import { liveTime } from "./useLivePrices";

/** 'KIS 실시간 체결가로 받은 가격' 표시 — 체결 시각 (없으면 아무것도 안 그림) */
export default function LiveBadge({ t }: { t?: string }) {
  if (!t) return null;
  return (
    <span data-testid="live-badge" title="KIS 실시간 체결가 (웹소켓) — 2초마다 갱신" style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10.5,
      color: "var(--green)", fontWeight: 500, whiteSpace: "nowrap" }}>
      <span style={{ width: 6, height: 6, borderRadius: 3, background: "var(--green)" }} />실시간 {liveTime(t)}
    </span>
  );
}
