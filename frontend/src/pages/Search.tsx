import { useState } from "react";
import { stockApi } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import { Search as SearchIcon } from "lucide-react";

export default function Search() {
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState("KR");
  const [exchange, setExchange] = useState("NAS");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async () => {
    if (!symbol) return;
    setLoading(true);
    setError("");
    setData(null);
    try {
      const res = market === "KR"
        ? await stockApi.kr(symbol)
        : await stockApi.us(symbol, exchange);
      setData(res.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || "종목 조회 실패. 종목코드를 확인하세요.");
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
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>종목코드로 상세 분석을 조회하세요</p>
      </div>

      {/* Search bar */}
      <div className="card" style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 24 }}>
        <select value={market} onChange={(e) => setMarket(e.target.value)}
          style={{ padding: "9px 12px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 13, outline: "none" }}>
          <option value="KR">국내</option>
          <option value="US">미국</option>
        </select>
        {market === "US" && (
          <select value={exchange} onChange={(e) => setExchange(e.target.value)}
            style={{ padding: "9px 12px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 13, outline: "none" }}>
            <option value="NAS">나스닥</option>
            <option value="NYS">뉴욕</option>
          </select>
        )}
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder={market === "KR" ? "종목코드 (예: 005930)" : "티커 (예: AAPL)"}
          style={{ flex: 1, padding: "9px 12px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none" }}
        />
        <button className="btn btn-primary" onClick={handleSearch} disabled={loading}>
          <SearchIcon size={14} />
          {loading ? "조회 중..." : "검색"}
        </button>
      </div>

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
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>내일 상승 확률</p>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{ flex: 1, height: 8, background: "var(--bg-secondary)", borderRadius: 4, overflow: "hidden" }}>
                        <div style={{ width: `${pred.probability}%`, height: "100%", background: pred.probability >= 65 ? "var(--green)" : pred.probability >= 45 ? "var(--yellow)" : "var(--red)", borderRadius: 4 }} />
                      </div>
                      <span style={{ fontSize: 18, fontWeight: 700 }}>{pred.probability}%</span>
                    </div>
                    <p style={{ fontSize: 13, fontWeight: 600, marginTop: 6 }}>{pred.signal}</p>
                  </div>
                  {pred.target_price && (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      <div style={{ background: "rgba(52,211,153,0.07)", borderRadius: 7, padding: 10 }}>
                        <p style={{ fontSize: 11, color: "var(--text-muted)" }}>목표가</p>
                        <p style={{ color: "var(--green)", fontWeight: 700 }}>
                          {isKR ? `₩${pred.target_price.toLocaleString()}` : `$${pred.target_price.toFixed(2)}`}
                        </p>
                      </div>
                      <div style={{ background: "rgba(248,113,113,0.07)", borderRadius: 7, padding: 10 }}>
                        <p style={{ fontSize: 11, color: "var(--text-muted)" }}>손절가</p>
                        <p style={{ color: "var(--red)", fontWeight: 700 }}>
                          {isKR ? `₩${pred.stop_loss?.toLocaleString()}` : `$${pred.stop_loss?.toFixed(2)}`}
                        </p>
                      </div>
                    </div>
                  )}
                  <ul style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {pred.reasons?.map((r: string, i: number) => (
                      <li key={i} style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", gap: 6 }}>
                        <span style={{ color: "var(--accent)", flexShrink: 0 }}>•</span>{r}
                      </li>
                    ))}
                  </ul>
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
              <h3 style={{ fontWeight: 600, marginBottom: 12, fontSize: 14 }}>관련 뉴스</h3>
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
