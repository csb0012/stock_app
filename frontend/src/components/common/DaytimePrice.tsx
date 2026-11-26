import { fmtPrice } from "./format";

/** 미국 정규장 밖 가격 — 주간거래(한국 낮, KIS 블루오션) / 프리마켓·애프터마켓(Yahoo 5분봉). 정규장 가격과 따로 표시. 없으면 아무것도 안 그림 */
export default function DaytimePrice({ d, size = 12 }: { d?: any; size?: number }) {
  if (!d) return null;
  const label = d.label || "주간거래";
  if (d.error) {
    return <span style={{ fontSize: 11, color: "var(--yellow)" }} title={d.error}>{label} ⚠ 조회 실패</span>;
  }
  const up = d.change_rate > 0, down = d.change_rate < 0;
  const yahoo = String(d.source || "").startsWith("Yahoo");
  const tip = yahoo
    ? `미국 ${label} 마지막 체결가 (한국시간 ${d.hours_kst}) · Yahoo 5분봉 ${d.et_time || ""} (몇 분 늦을 수 있음)` +
      (d.base ? ` · 정규장 종가 ${fmtPrice(d.base, "US")} 대비` : "") + " · 예측 확률 계산에는 쓰지 않음"
    : `미국 주간거래 체결가 (한국시간 ${d.hours_kst}, 한국투자증권) · ${d.time} 조회` +
      (d.base ? ` · 직전 정규장 종가 ${fmtPrice(d.base, "US")} 대비` : "") + " · 예측 확률 계산에는 쓰지 않음";
  return (
    <span data-testid="daytime-price" title={tip}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: size, whiteSpace: "nowrap" }}>
      <span className="badge badge-accent" style={{ padding: "1px 6px" }}>{label}</span>
      <strong style={{ fontVariantNumeric: "tabular-nums", color: "var(--text-primary)" }}>{fmtPrice(d.price, "US")}</strong>
      <span style={{ color: up ? "var(--green)" : down ? "var(--red)" : "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
        {up ? "+" : ""}{Number(d.change_rate).toFixed(2)}%
      </span>
      <span style={{ color: "var(--text-muted)", fontSize: size - 1 }}>{d.time}</span>
    </span>
  );
}
