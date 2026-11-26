import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { valueApi, errMsg } from "../api/client";
import FetchStatus from "../components/common/FetchStatus";
import WatchButton from "../components/common/WatchButton";
import StockQuoteCard from "../components/common/StockQuoteCard";
import { gradeColor } from "../components/common/QuantBadge";
import { fmtPrice, fmtNum, fmtUsdBig } from "../components/common/format";
import { useNarrow } from "../components/common/useNarrow";

const ICON: Record<string, string> = {
  undervalued_growth: "🚀", growth: "📈", steady_growth: "🪴", cheap_value: "🏷️", high_roe_cheap: "🌱",
  value_breakout: "🎉", cash_cow: "💵", dividend: "👑", turnaround: "🔄",
};

function read(key: string, def: string): string {
  try { return localStorage.getItem(key) || def; } catch { return def; }
}
function save(key: string, v: string) {
  try { localStorage.setItem(key, v); } catch { /* 저장 못 해도 화면은 동작 */ }
}

function Pct({ v, digits = 1 }: { v: number | null | undefined; digits?: number }) {
  if (v == null) return <span style={{ color: "var(--text-muted)" }}>-</span>;
  return <span style={{ color: v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : undefined }}>{v > 0 ? "+" : ""}{v.toFixed(digits)}%</span>;
}

export default function ValueScreens() {
  const [market, setMarket] = useState(() => read("value-market", "KR"));
  const [key, setKey] = useState(() => read("value-screen", "undervalued_growth"));
  const [picked, setPicked] = useState<any>(null);
  const narrow = useNarrow();
  const meta = useQuery({ queryKey: ["value-screens"], queryFn: () => valueApi.screens().then((r) => r.data), staleTime: 60 * 60 * 1000 });
  const screens: any[] = meta.data?.[market] || [];
  const cur = screens.find((s) => s.key === key) || screens[0];
  const q = useQuery({
    queryKey: ["value", market, cur?.key], queryFn: () => valueApi.screen(market, cur.key).then((r) => r.data),
    enabled: !!cur, staleTime: 10 * 60 * 1000,
  });
  const st = meta.data?.status;
  const isKR = market === "KR";
  const rows: any[] = q.data?.items || [];

  const pickMarket = (m: string) => { setMarket(m); save("value-market", m); };
  const pickKey = (k: string) => { setKey(k); save("value-screen", k); };

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>가치주 찾기</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13, lineHeight: 1.6 }}>
          PER·PBR·ROE·성장률·배당 조건으로 고른 종목. 국내는 네이버 증권 분기 실적(최근 4분기 합)과 마지막 종가로 직접 계산, 미국은 Yahoo 스크리너 조건 검색.
          국내 가치·수익성은 <strong>퀀트 점수의 요인</strong>으로도 들어가고, 과거에 실제로 맞았던 만큼만 비중을 받아요.
        </p>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {[["KR", "국내"], ["US", "미국"]].map(([m, label]) => (
            <button key={m} className={`btn ${market === m ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "5px 12px" }}
              onClick={() => pickMarket(m)}>{label}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 11.5, color: "var(--text-muted)" }}>
          {isKR && st && <span>{st.running ? <span style={{ color: "var(--accent)" }}>재무 받는 중 {st.done}/{st.total}</span>
            : `재무 ${st.kr_symbols?.toLocaleString() ?? 0}종목${st.kr_last ? ` · ${st.kr_last} 갱신` : ""}`}</span>}
          <FetchStatus updatedAt={q.dataUpdatedAt} fetching={q.isFetching} />
        </div>
      </div>

      {meta.error && <p style={{ color: "var(--red)" }}>{errMsg(meta.error)}</p>}

      <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr" : "260px 1fr", gap: 16, alignItems: "start" }}>
        <div className="card" style={{ padding: 6 }} data-testid="value-screen-list">
          {screens.map((s) => (
            <button key={s.key} onClick={() => pickKey(s.key)} title={s.about}
              style={{ display: "flex", width: "100%", gap: 10, alignItems: "center", padding: "9px 10px", borderRadius: 8, border: "none",
                background: cur?.key === s.key ? "var(--bg-hover)" : "transparent", color: "inherit", cursor: "pointer", textAlign: "left" }}>
              <span style={{ fontSize: 20, width: 34, height: 34, display: "grid", placeItems: "center", borderRadius: 8, background: "var(--bg-hover)", flexShrink: 0 }}>{ICON[s.key] || "•"}</span>
              <span style={{ minWidth: 0 }}>
                <span style={{ display: "block", fontWeight: 700, fontSize: 13 }}>{s.name}</span>
                {!narrow && <span style={{ display: "block", fontSize: 11, color: "var(--text-muted)", lineHeight: 1.4 }}>{s.about}</span>}
              </span>
            </button>
          ))}
        </div>

        <div style={{ minWidth: 0 }}>
          {picked && <StockQuoteCard item={picked} onClose={() => setPicked(null)} actions={<WatchButton item={picked} />} />}
          {cur && (
            <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 8 }}>
              <strong>{cur.name}</strong> — {cur.about}
              {q.data?.total != null && <span style={{ color: "var(--text-muted)" }}> · {q.data.total.toLocaleString()}종목</span>}
            </p>
          )}
          {q.isLoading && <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>}
          {q.error && <p style={{ color: "var(--red)" }}>{errMsg(q.error)}</p>}
          {q.data?.message && <div className="card"><p style={{ fontSize: 13, color: "var(--text-secondary)" }}>{q.data.message}</p></div>}
          {rows.length > 0 && (
            <div className="card" style={{ padding: 0, overflowX: "auto" }}>
              <table className="data-table" data-testid="value-table">
                <thead>
                  <tr>
                    <th>종목</th><th className="num">현재가</th><th className="num">PER</th><th className="num">PBR</th>
                    {isKR ? <>
                      <th className="num">ROE</th>{!narrow && <th className="num">영업이익률</th>}{!narrow && <th className="num" title="전년 같은 분기 대비">매출 성장</th>}
                      {!narrow && <th className="num" title="전년 같은 분기 대비">영업이익 성장</th>}<th className="num">배당</th>{!narrow && <th>퀀트</th>}{!narrow && <th>수급</th>}
                    </> : <>
                      <th className="num">배당</th><th className="num">1년 등락</th>{!narrow && <th className="num">시가총액</th>}
                    </>}
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setPicked({ market, symbol: r.symbol, name: r.name, exchange: r.exchange })}>
                      <td><div style={{ fontWeight: 600 }}>{r.name}</div><div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{r.symbol}</div></td>
                      <td className="num">{fmtPrice(r.price, market)}</td>
                      <td className="num">{fmtNum(r.per)}</td>
                      <td className="num">{fmtNum(r.pbr, 2)}</td>
                      {isKR ? <>
                        <td className="num">{fmtNum(r.roe, 1, "%")}</td>
                        {!narrow && <td className="num">{fmtNum(r.op_margin, 1, "%")}</td>}
                        {!narrow && <td className="num"><Pct v={r.sales_yoy} /></td>}
                        {!narrow && <td className="num"><Pct v={r.op_yoy} /></td>}
                        <td className="num">{fmtNum(r.div_yield, 1, "%")}</td>
                        {!narrow && <td><span style={{ color: r.quant_grade ? gradeColor(r.quant_grade) : undefined, fontWeight: 700 }}>{r.quant_grade || "-"}</span></td>}
                        {!narrow && <td style={{ fontSize: 11.5, color: r.flow_streak > 0 ? "var(--green)" : "var(--text-muted)", whiteSpace: "nowrap" }}>{r.flow_label || "-"}</td>}
                      </> : <>
                        <td className="num">{fmtNum(r.div_yield, 2, "%")}</td>
                        <td className="num"><Pct v={r.change_52w} /></td>
                        {!narrow && <td className="num">{fmtUsdBig(r.market_cap)}</td>}
                      </>}
                      <td onClick={(e) => e.stopPropagation()}><WatchButton item={{ market, symbol: r.symbol, name: r.name }} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {q.data && !q.data.message && rows.length === 0 && <div className="card"><p style={{ color: "var(--text-muted)", textAlign: "center" }}>조건에 맞는 종목이 없습니다</p></div>}
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8, lineHeight: 1.6 }}>
            {isKR ? "업종 차이(은행은 원래 PBR 이 낮음 등)는 따로 보정하지 않았어요. 성장률은 전년 같은 분기 대비, ROE = 최근 4분기 주당순이익 ÷ 주당순자산. 거래대금 1억 원 미만 종목 제외."
              : "Yahoo 스크리너 기준 (시가총액 20억 달러↑, 시가총액 큰 순 최대 100개). 우선주 제외."} 참고용이며 투자 손실 책임은 본인에게 있습니다.
          </p>
        </div>
      </div>
    </div>
  );
}
