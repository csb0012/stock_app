import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { stockApi, errMsg } from "../../api/client";
import ChangeTag from "./ChangeTag";
import PredictionReasons from "./PredictionReasons";
import { fmtPrice, probColor, probLabel } from "./format";

/** 검색으로 고른 종목 1개의 시세 + 내일 전망 카드 */
export default function StockQuoteCard({
  item,
  onClose,
  actions,
}: {
  item: { market: string; symbol: string; name: string };
  onClose: () => void;
  actions?: React.ReactNode;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["quote", item.market, item.symbol],
    queryFn: () => stockApi.quote(item.market, item.symbol).then((r) => r.data),
    staleTime: 60_000,
  });
  const pred = data?.prediction;
  const ind = data?.indicators || {};

  return (
    <div className="card" style={{ position: "relative", marginBottom: 20 }}>
      <button onClick={onClose} style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
        <X size={16} />
      </button>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 16 }}>{item.name}</span>
        <span className="badge badge-neutral">{item.symbol}</span>
        <span className="badge badge-neutral">{item.market === "KR" ? "국내" : "미국"}</span>
      </div>

      {isLoading && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>시세 불러오는 중...</p>}
      {error && <p style={{ color: "var(--red)", fontSize: 13 }}>{errMsg(error)}</p>}

      {data && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(200px, 1fr) 2fr", gap: 20 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 22, fontWeight: 700 }}>{fmtPrice(data.price, item.market)}</span>
              <ChangeTag value={data.change_rate} />
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
              {ind.rsi != null && <span>RSI {ind.rsi}</span>}
              {data.per > 0 && <span>PER {data.per.toFixed(1)}</span>}
              {data.pbr > 0 && <span>PBR {data.pbr.toFixed(2)}</span>}
              {ind.ma20 && <span>20일선 {fmtPrice(ind.ma20, item.market)}</span>}
            </div>
            {actions && <div style={{ display: "flex", gap: 6, marginTop: 12 }}>{actions}</div>}
          </div>
          {pred && (
            <div>
              <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>내일 전망</p>
              <p style={{ fontWeight: 700, color: probColor(pred.probability) }}>
                상승 확률 {pred.probability}% · {probLabel(pred.probability)}
                <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-muted)", marginLeft: 8 }}>신뢰도 {pred.confidence}</span>
              </p>
              <PredictionReasons pred={pred} defaultOpen />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
