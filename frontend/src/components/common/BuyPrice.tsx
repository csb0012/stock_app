import { fmtPrice } from "./format";

/** 추천 매입가 (지지선·ATR 기반) — compact 는 한 줄 표시, dense 는 3칸 안에 들어가는 작은 상자 */
export default function BuyPrice({ pred, market, compact = false, dense = false, label = "추천 매입가" }: {
  pred: any; market: string; compact?: boolean; dense?: boolean; label?: string;
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
    <div style={{ background: "color-mix(in srgb, var(--accent) 7%, transparent)", borderRadius: 7, padding: dense ? "6px 8px" : "8px 10px", minWidth: 0 }}
      title={pred.buy_comment || pred.entry_comment || undefined}>
      <p style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>{label}</p>
      <p style={{ fontWeight: 700, color: "var(--accent)", fontSize: dense ? 12.5 : 13 }}>{fmtPrice(price, market)}</p>
      <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
        {gapTxt}
        {!dense && pred.buy_low != null && pred.buy_high != null && pred.buy_high > pred.buy_low && (
          <> · {fmtPrice(pred.buy_low, market)}~{fmtPrice(pred.buy_high, market)}</>
        )}
      </p>
    </div>
  );
}
