import { useState } from "react";
import { stockApi, errMsg } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import StockSearchBox from "../components/common/StockSearchBox";
import BuyPrice from "../components/common/BuyPrice";
import PredictionReasons from "../components/common/PredictionReasons";

export default function Search() {
  const [picked, setPicked] = useState<any>(null);
  const [market, setMarket] = useState("KR");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 자동완성에서 고른 종목 조회 — 미국은 종목마스터의 거래소(NAS/NYS/AMS)를 그대로 사용
  const handleSelect = async (item: any) => {
    setPicked(item);
    setMarket(item.market);
    setLoading(true);
    setError("");
    setData(null);
    try {
      const res = item.market === "KR"
        ? await stockApi.kr(item.symbol)
        : await stockApi.us(item.symbol, item.exchange || "NAS");
      setData(res.data);
    } catch (e: any) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  };

  const price = data?.price;
  const pred = data?.prediction;
  const ind = data?.indicators;
  const isKR = market === "KR";

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>종목 검색</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>종목명 또는 코드로 검색해 상세 분석을 조회하세요</p>
      </div>

      {/* Search bar */}
      <div style={{ marginBottom: 16 }}>
        <StockSearchBox onSelect={handleSelect} />
      </div>
      {picked && (
        <p style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>
          {picked.name}
          <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 12, marginLeft: 8 }}>
            {picked.symbol} · {picked.exchange}
          </span>
          {loading && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 12, marginLeft: 8 }}>조회 중...</span>}
        </p>
      )}

      {error && <p style={{ color: "var(--red)", marginBottom: 16 }}>{error}</p>}

      {data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* 현재가 */}
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p style={{ fontSize: 20, fontWeight: 700 }}>
                  {isKR ? `₩${price?.price?.toLocaleString()}` : `$${price?.price?.toFixed(2)}`}
                </p>
                <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                  <ChangeTag value={price?.change_rate || 0} />
                  {price?.per > 0 && <span className="badge badge-neutral">PER {price.per}</span>}
                  {price?.pbr > 0 && <span className="badge badge-neutral">PBR {price.pbr}</span>}
                </div>
              </div>
              <div style={{ textAlign: "right", fontSize: 12, color: "var(--text-muted)" }}>
                <p>고가 {isKR ? `₩${price?.high?.toLocaleString()}` : `$${price?.high?.toFixed(2)}`}</p>
                <p>저가 {isKR ? `₩${price?.low?.toLocaleString()}` : `$${price?.low?.toFixed(2)}`}</p>
                <p>거래량 {price?.volume?.toLocaleString()}</p>
              </div>
            </div>
          </div>

          {/* 기술지표 + 예측 */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="card">
              <h3 style={{ fontWeight: 600, marginBottom: 12, fontSize: 14 }}>기술적 지표</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  { label: "RSI (14)", value: ind?.rsi?.toFixed(1), warn: ind?.rsi < 30 ? "과매도" : ind?.rsi > 70 ? "과매수" : null },
                  { label: "MACD", value: ind?.macd?.toFixed(4) },
                  { label: "Signal", value: ind?.macd_signal?.toFixed(4) },
                  { label: "MA 5일", value: isKR ? ind?.ma5?.toLocaleString() : ind?.ma5?.toFixed(2) },
                  { label: "MA 20일", value: isKR ? ind?.ma20?.toLocaleString() : ind?.ma20?.toFixed(2) },
                  { label: "BB 상단", value: isKR ? ind?.bb_upper?.toLocaleString() : ind?.bb_upper?.toFixed(2) },
                  { label: "BB 하단", value: isKR ? ind?.bb_lower?.toLocaleString() : ind?.bb_lower?.toFixed(2) },
                ].map(({ label, value, warn }) => (
                  <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{label}</span>
                    <span style={{ fontSize: 13, fontWeight: 500 }}>
                      {value ?? "-"}
                      {warn && <span style={{ color: "var(--yellow)", fontSize: 11, marginLeft: 6 }}>{warn}</span>}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <h3 style={{ fontWeight: 600, marginBottom: 12, fontSize: 14 }}>AI 분석 결과</h3>
              {pred && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>{pred?.target_label || "다음 거래일"} 상승 확률</p>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{ flex: 1, height: 8, background: "var(--bg-secondary)", borderRadius: 4, overflow: "hidden" }}>
                        <div style={{ width: `${pred.probability}%`, height: "100%", background: pred.probability >= 65 ? "var(--green)" : pred.probability >= 45 ? "var(--yellow)" : "var(--red)", borderRadius: 4 }} />
                      </div>
                      <span style={{ fontSize: 18, fontWeight: 700 }}>{pred.probability}%</span>
                    </div>
                    <p style={{ fontSize: 13, fontWeight: 600, marginTop: 6 }}>{pred.signal}</p>
                  </div>
                  {pred.target_price && (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                      <BuyPrice pred={pred} market={market} />
                      <div style={{ background: "color-mix(in srgb, var(--green) 7%, transparent)", borderRadius: 7, padding: 10 }}>
                        <p style={{ fontSize: 11, color: "var(--text-muted)" }}>목표가</p>
                        <p style={{ color: "var(--green)", fontWeight: 700 }}>
                          {isKR ? `₩${pred.target_price.toLocaleString()}` : `$${pred.target_price.toFixed(2)}`}
                        </p>
                      </div>
                      <div style={{ background: "color-mix(in srgb, var(--red) 7%, transparent)", borderRadius: 7, padding: 10 }}>
                        <p style={{ fontSize: 11, color: "var(--text-muted)" }}>손절가</p>
                        <p style={{ color: "var(--red)", fontWeight: 700 }}>
                          {isKR ? `₩${pred.stop_loss?.toLocaleString()}` : `$${pred.stop_loss?.toFixed(2)}`}
                        </p>
                      </div>
                    </div>
                  )}
                  {(pred.buy_comment || pred.entry_comment) && (
                    <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>💡 {pred.buy_comment || pred.entry_comment}</p>
                  )}
                  <PredictionReasons pred={pred} defaultOpen />
                  <p style={{ fontSize: 11, color: "var(--text-muted)", borderTop: "1px solid var(--border)", paddingTop: 8 }}>
                    {pred.disclaimer}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* 뉴스 */}
          {data.news && data.news.length > 0 && (
            <div className="card">
              <h3 style={{ fontWeight: 600, marginBottom: 12, fontSize: 14 }}>
                관련 뉴스
                {data.news_source && <span style={{ fontWeight: 400, fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>출처: {data.news_source}</span>}
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {data.news.filter((n: any) => n.title).map((n: any, i: number) => (
                  <a key={i} href={n.url} target="_blank" rel="noopener noreferrer"
                    style={{ display: "flex", justifyContent: "space-between", textDecoration: "none", color: "inherit", padding: "8px 0", borderBottom: i < data.news.length - 1 ? "1px solid var(--border)" : "none" }}>
                    <span style={{ fontSize: 13, color: "var(--text-primary)" }}>{n.title}</span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0, marginLeft: 12 }}>{n.date}</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
