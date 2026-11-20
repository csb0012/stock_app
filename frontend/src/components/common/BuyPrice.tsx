import { fmtPrice } from "./format";

/** 추천 매입가 (지지선·ATR 기반) — compact 는 한 줄 표시 */
export default function BuyPrice({ pred, market, compact = false, label = "추천 매입가" }: {
  pred: any; market: string; compact?: boolean; label?: string;
}) {
  const price = pred?.buy_price ?? pred?.entry_price;
  if (price == null) return null;
  const gap = pred.buy_gap_pct;
  const gapTxt = gap == null ? "" : gap >= -0.05 ? "현재가 부근" : `현재가 대비 ${gap.toFixed(1)}%`;

  if (compact) {
    return (
      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 6 }}>
        <span style={{ color: "var(--accent)", fontWeight: 700 }}>{label} {fmtPrice(price, market)}</span>
        <span style={{ color: "var(--text-muted)" }}> ({gapTxt}) · {pred.buy_comment || pred.entry_comment}</span>
      </p>
    );
  }
  return (
    <div style={{ background: "rgba(79,142,247,0.07)", borderRadius: 7, padding: "8px 10px" }}>
      <p style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>{label}</p>
      <p style={{ fontWeight: 700, color: "var(--accent)", fontSize: 13 }}>{fmtPrice(price, market)}</p>
      <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
        {gapTxt}
        {pred.buy_low != null && pred.buy_high != null && pred.buy_high > pred.buy_low && (
          <> · {fmtPrice(pred.buy_low, market)}~{fmtPrice(pred.buy_high, market)}</>
        )}
      </p>
    </div>
  );
}
