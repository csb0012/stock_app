/** 매집 점수 배지 (매집 탐지 화면과 같은 기준) */
export default function AccumBadge({ score }: { score?: number | null }) {
  if (score == null) return <span style={{ color: "var(--text-muted)", fontSize: 12 }}>-</span>;
  const color = score >= 70 ? "var(--green)" : score >= 50 ? "var(--yellow)" : "var(--text-muted)";
  return (
    <span title="매집·바닥 다지기 점수 (100점, 매집 탐지 메뉴 참고)" style={{
      fontSize: 12, fontWeight: 600, color, padding: "2px 8px", borderRadius: 999,
      background: `color-mix(in srgb, ${color} 12%, transparent)`, fontVariantNumeric: "tabular-nums",
    }}>{score}</span>
  );
}
