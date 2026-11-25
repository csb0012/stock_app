import { useQuery } from "@tanstack/react-query";
import { useLivePrices } from "./useLivePrices";
import LiveBadge from "./LiveBadge";
import { X, Newspaper } from "lucide-react";
import { stockApi, errMsg } from "../../api/client";
import ChangeTag from "./ChangeTag";
import PredictionReasons from "./PredictionReasons";
import PriceLevels from "./PriceLevels";
import DaytimePrice from "./DaytimePrice";
import QuantBadge, { TrackBadge } from "./QuantBadge";
import NewsLink, { NewsSource } from "./NewsLink";
import { fmtPrice, probColor, probLabel, sessionLabel } from "./format";

/** 검색으로 고른 종목 1개의 상세: 시세(+미국 주간거래) · 내일 전망 · 매입가/목표가/손절가 · 기술 지표 · 최근 뉴스
 *  (예전 '종목검색' 화면 기능을 종목 탐색 안으로 합침) */
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
    refetchInterval: 15_000,  // 현재가·상승 확률 15초마다 갱신
    refetchIntervalInBackground: false,
  });
  const live = useLivePrices(item.market === "KR" ? [item.symbol] : [])[item.symbol];   // 국내: KIS 실시간 현재가 (2초)
  const pred = data?.prediction;
  const ind = data?.indicators || {};
  const m = item.market;
  const headlines: any[] = (data?.news?.headlines || []).filter((h: any) => h.title);

  const indRows: [string, any, string?][] = [
    ["RSI(14)", ind.rsi != null ? ind.rsi.toFixed?.(1) ?? ind.rsi : null, ind.rsi < 30 ? "과매도" : ind.rsi > 70 ? "과매수" : undefined],
    ["MACD 히스토그램", ind.macd_hist != null ? Number(ind.macd_hist).toFixed(m === "KR" ? 0 : 3) : null],
    ["20일선", ind.ma20 ? fmtPrice(ind.ma20, m) : null],
    ["60일선", ind.ma60 ? fmtPrice(ind.ma60, m) : null],
    ["볼린저 상단", ind.bb_upper ? fmtPrice(ind.bb_upper, m) : null],
    ["볼린저 하단", ind.bb_lower ? fmtPrice(ind.bb_lower, m) : null],
  ];

  return (
    <div className="card" data-testid="quote-card" style={{ position: "relative", marginBottom: 20 }}>
      <button onClick={onClose} aria-label="닫기" style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
        <X size={16} />
      </button>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap", paddingRight: 24 }}>
        <span style={{ fontWeight: 700, fontSize: 16 }}>{item.name}</span>
        <span className="badge badge-neutral">{item.symbol}</span>
        <span className="badge badge-neutral">{m === "KR" ? "국내" : "미국"}</span>
      </div>

      {isLoading && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>시세 불러오는 중...</p>}
      {error && <p style={{ color: "var(--red)", fontSize: 13 }}>{errMsg(error)}</p>}

      {data && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20 }}>
          {/* 시세 + 지표 */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{ fontSize: 22, fontWeight: 700 }}>{fmtPrice(live?.price ?? data.price, m)}</span>
              <ChangeTag value={live?.change_rate ?? data.change_rate} />
              <LiveBadge t={live?.time} />
            </div>
            {data.daytime && <div style={{ marginTop: 4 }}><DaytimePrice d={data.daytime} /></div>}
            {(data.quant || data.track) && (
              <div style={{ marginTop: 6, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <QuantBadge q={data.quant} /><TrackBadge t={data.track} />
              </div>
            )}
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
              {data.per > 0 && <span>PER {data.per.toFixed(1)}</span>}
              {data.pbr > 0 && <span>PBR {data.pbr.toFixed(2)}</span>}
              {data.volume > 0 && <span>거래량 {Number(data.volume).toLocaleString()}</span>}
            </div>
            <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 14 }}>
              {indRows.filter(([, v]) => v != null).map(([label, value, warn]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
                  <span style={{ color: "var(--text-muted)" }}>{label}</span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>
                    {value}{warn && <span style={{ color: "var(--yellow)", fontSize: 11, marginLeft: 4 }}>{warn}</span>}
                  </span>
                </div>
              ))}
            </div>
            {actions && <div style={{ display: "flex", gap: 6, marginTop: 12 }}>{actions}</div>}
          </div>

          {/* 전망 + 가격대 */}
          {pred && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div>
                <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>{sessionLabel(pred)} 전망</p>
                <p style={{ fontWeight: 700, color: probColor(pred.probability) }}>
                  상승 확률 {pred.probability}% · {probLabel(pred.probability)}
                  <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-muted)", marginLeft: 8 }}>신뢰도 {pred.confidence}</span>
                </p>
              </div>
              <PriceLevels pred={pred} market={m} />
              {(pred.buy_comment || pred.entry_comment) && (
                <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>💡 {pred.buy_comment || pred.entry_comment}</p>
              )}
              <PredictionReasons pred={pred} />
            </div>
          )}

          {/* 최근 뉴스 */}
          {headlines.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
              <p style={{ fontSize: 11, color: "var(--text-muted)" }}>
                최근 뉴스{data.news?.source ? ` · ${data.news.source}` : ""}
              </p>
              {headlines.slice(0, 6).map((h: any, i: number) => (
                <div key={i} style={{ display: "flex", gap: 6, fontSize: 12, alignItems: "baseline", minWidth: 0 }}>
                  <Newspaper size={11} style={{ flexShrink: 0, color: h.tone === "pos" ? "var(--green)" : h.tone === "neg" ? "var(--red)" : "var(--text-muted)" }} />
                  <NewsSource item={h} />
                  <NewsLink item={h} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} />
                </div>
              ))}
              {headlines.some((h: any) => h.weighted === false) && (
                <p style={{ fontSize: 10.5, color: "var(--text-muted)" }}>국내 종목은 해외 주요 매체 기사만 상승 확률에 반영 ("참고" 기사는 보여주기만)</p>
              )}
            </div>
          )}
        </div>
      )}
      {pred?.disclaimer && <p style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 12 }}>{pred.disclaimer}</p>}
    </div>
  );
}
