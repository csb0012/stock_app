import BuyPrice from "./BuyPrice";
import { fmtPrice } from "./format";

/** 추천 매입가 · 목표가(익절) · 손절가 3칸 — AI 추천·관심종목·종목 탐색 공통 */
export default function PriceLevels({ pred, market, dense = false }: { pred: any; market: string; dense?: boolean }) {
  if (!pred?.target_price) return null;
  const box = (bg: string): React.CSSProperties => ({
    background: `color-mix(in srgb, ${bg} 7%, transparent)`, borderRadius: 7, padding: dense ? "6px 8px" : "8px 10px", minWidth: 0,
  });
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: dense ? 6 : 8 }}>
      <BuyPrice pred={pred} market={market} dense={dense} />
      <div style={box("var(--green)")} title="현재가 + 최근 14일 평균 변동폭(ATR) × 2">
        <p style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>목표가 (익절)</p>
        <p style={{ fontWeight: 700, color: "var(--green)", fontSize: dense ? 12.5 : 13 }}>{fmtPrice(pred.target_price, market)}</p>
      </div>
      <div style={box("var(--red)")} title="추천 매입가 지지선이 깨지는 가격 (매입가 − ATR, 현재가 − ATR×1.5 중 낮은 값)">
        <p style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>손절가</p>
        <p style={{ fontWeight: 700, color: "var(--red)", fontSize: dense ? 12.5 : 13 }}>{fmtPrice(pred.stop_loss, market)}</p>
      </div>
    </div>
  );
}
