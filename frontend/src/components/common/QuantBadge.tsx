/** 퀀트 점수 배지 (국내 전 종목 중 순위 기반 등급) — 마우스를 올리면 요인별 등급·과거 검증 */

export const FACTOR_NAMES: Record<string, string> = {
  rs: "모멘텀(RS)", trend: "추세", updown: "거래량 매집", lowvol: "안정성", high52: "고점 근접",
  value: "가치", quality: "수익성", flow: "수급",
};

export function gradeOf(p: number | null | undefined): string {
  if (p == null) return "-";
  return p >= 90 ? "A+" : p >= 80 ? "A" : p >= 65 ? "B+" : p >= 50 ? "B" : p >= 35 ? "C" : p >= 20 ? "D" : "F";
}

export function gradeColor(g: string): string {
  return g.startsWith("A") ? "var(--green)" : g.startsWith("B") ? "var(--accent)" : g === "C" ? "var(--yellow)" : "var(--red)";
}

export default function QuantBadge({ q, size = 11.5 }: { q?: any; size?: number }) {
  if (!q) return null;
  const factors = Object.entries(q.factors || {}).map(([k, v]) => `${FACTOR_NAMES[k] || k} ${gradeOf(v as number)}(${v ?? "-"})`).join(" · ");
  const tip = `퀀트 점수 ${q.score}/10 — 국내 ${q.universe?.toLocaleString?.() ?? ""}종목 중 상위 ${100 - q.pct}% (${q.date} 기준)\n` +
    `요인: ${factors}\n` +
    (q.beat_rate != null ? `과거 검증: 이 구간(${q.bucket}) 종목이 20거래일 뒤 전 종목 중간값을 이긴 비율 ${q.beat_rate}% (기준 50%)` : "검증 데이터 부족");
  const c = gradeColor(q.grade);
  return (
    <span data-testid="quant-badge" title={tip} className="badge"
      style={{ background: `color-mix(in srgb, ${c} 12%, transparent)`, color: c, gap: 4, fontSize: size, whiteSpace: "nowrap" }}>
      퀀트 {q.grade} · {q.score}/10
    </span>
  );
}

/** 종목별 최근 90일 예측 적중 기록 (표본 10건 미만이면 흐리게) */
export function TrackBadge({ t, size = 11 }: { t?: any; size?: number }) {
  if (!t || !t.n) return null;
  const low = t.enough && t.accuracy != null && t.accuracy < 45;
  const tip = `이 종목 최근 ${t.days}일 예측 기록 (백테스트 + 실제 예측): 방향 적중 ${t.hit}/${t.n}` +
    (t.conf_n ? ` · 확신 예측(55%↑/45%↓) ${t.conf_hit}/${t.conf_n}` : "") +
    (t.enough ? "" : " · 10건 미만이라 참고만") + (low ? " · 이 종목은 예측이 잘 안 맞았음" : "");
  return (
    <span data-testid="track-badge" title={tip}
      style={{ fontSize: size, whiteSpace: "nowrap", color: low ? "var(--red)" : t.enough ? "var(--text-secondary)" : "var(--text-muted)" }}>
      예측 적중 {t.accuracy ?? "-"}% <span style={{ color: "var(--text-muted)" }}>({t.n}건)</span>
    </span>
  );
}
