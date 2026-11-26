import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { flowApi, errMsg } from "../api/client";
import FetchStatus from "../components/common/FetchStatus";
import WatchButton from "../components/common/WatchButton";
import StockQuoteCard from "../components/common/StockQuoteCard";
import { fmtPrice, fmtWon } from "../components/common/format";
import { useNarrow } from "../components/common/useNarrow";

const LISTS: [string, string, string][] = [
  ["double", "쌍끌이", "외국인과 기관이 같은 날 함께 순매수 (연속 일수 순)"],
  ["foreign", "외국인 순매수", "최근 5거래일 외국인 순매수 금액 순"],
  ["institution", "기관 순매수", "최근 5거래일 기관 순매수 금액 순"],
  ["retail_buy", "개미 순매수", "최근 5거래일 개인 순매수 금액 순 — 외국인·기관이 팔 때 개인이 받는 경우가 많아요"],
  ["retail_sell", "개미 순매도", "최근 5거래일 개인 순매도 금액 순"],
  ["double_sell", "동반 순매도", "외국인과 기관이 2일 넘게 함께 순매도"],
];

function Amt({ v }: { v: number | null | undefined }) {
  return <span style={{ color: v == null ? undefined : v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-muted)" }}>{fmtWon(v)}</span>;
}

/** 날짜별 개인·외국인·기관 순매수 막대 (0 기준 위/아래) */
function DailyBars({ daily }: { daily: any[] }) {
  const max = Math.max(1, ...daily.flatMap((d) => [Math.abs(d.prsn), Math.abs(d.frgn), Math.abs(d.orgn)]));
  const series: [string, string, string][] = [["prsn", "개인(개미)", "var(--yellow)"], ["frgn", "외국인", "var(--accent)"], ["orgn", "기관", "var(--green)"]];
  return (
    <div>
      <div style={{ display: "flex", gap: 12, fontSize: 11.5, color: "var(--text-secondary)", marginBottom: 6 }}>
        {series.map(([k, label, c]) => <span key={k}><span style={{ display: "inline-block", width: 9, height: 9, background: c, borderRadius: 2, marginRight: 4 }} />{label}</span>)}
      </div>
      <div style={{ display: "flex", alignItems: "stretch", gap: 3, height: 140, overflowX: "auto" }}>
        {daily.map((d) => (
          <div key={d.date} title={`${d.date} · 개인 ${fmtWon(d.prsn)} · 외국인 ${fmtWon(d.frgn)} · 기관 ${fmtWon(d.orgn)} · 쌍끌이 ${d.double}종목 (${d.n}종목 합계)`}
            style={{ flex: "1 0 22px", display: "flex", flexDirection: "column", minWidth: 22 }}>
            <div style={{ flex: 1, display: "flex", alignItems: "flex-end", gap: 1 }}>
              {series.map(([k, , c]) => <div key={k} style={{ flex: 1, background: c, height: `${d[k] > 0 ? (d[k] / max) * 100 : 0}%`, borderRadius: "2px 2px 0 0" }} />)}
            </div>
            <div style={{ height: 1, background: "var(--border)" }} />
            <div style={{ flex: 1, display: "flex", alignItems: "flex-start", gap: 1 }}>
              {series.map(([k, , c]) => <div key={k} style={{ flex: 1, background: c, opacity: 0.55, height: `${d[k] < 0 ? (-d[k] / max) * 100 : 0}%`, borderRadius: "0 0 2px 2px" }} />)}
            </div>
            <div style={{ fontSize: 9.5, color: "var(--text-muted)", textAlign: "center", marginTop: 2 }}>{d.date.slice(8)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Flows() {
  const [list, setList] = useState("double");
  const [picked, setPicked] = useState<any>(null);
  const narrow = useNarrow();
  const { data, isLoading, error, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ["flows-overview"], queryFn: () => flowApi.overview().then((r) => r.data), staleTime: 10 * 60 * 1000,
  });
  const rows: any[] = data?.lists?.[list] || [];
  const daily: any[] = data?.daily || [];
  const last = daily[daily.length - 1];
  const st = data?.status;
  const sum5 = daily.slice(-5).reduce((a, d) => ({ prsn: a.prsn + d.prsn, frgn: a.frgn + d.frgn, orgn: a.orgn + d.orgn }), { prsn: 0, frgn: 0, orgn: 0 });

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>수급 동향 (쌍끌이 · 개미)</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13, lineHeight: 1.6 }}>
          국내 종목별 외국인·기관·개인 순매수 (KIS, 매일 18:10 이후 확정치). 금액은 수량 × 그날 종가로 어림.
          외국인+기관 순매수는 퀀트 점수의 <strong>수급 요인</strong>으로 들어가고, 과거 20거래일 뒤 성과와 맞았던 만큼만 비중을 받아요.
        </p>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, alignItems: "center", fontSize: 11.5, color: "var(--text-muted)", marginBottom: 10 }}>
        {st?.running && <span style={{ color: "var(--accent)" }}>수급 받는 중 {st.done}/{st.total}</span>}
        {data?.date && <span>{data.date} 기준 · {data.n?.toLocaleString()}종목</span>}
        <FetchStatus updatedAt={dataUpdatedAt} fetching={isFetching} />
      </div>
      {isLoading && <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>}
      {error && <p style={{ color: "var(--red)" }}>{errMsg(error)}</p>}
      {data && !data.date && (
        <div className="card" style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            아직 수급 데이터가 없습니다 — 전 종목 스캔(퀀트 점수)이 끝난 뒤 거래대금 1억 원↑ 종목의 최근 30일 수급을 KIS 에서 받습니다
            (서버 시작 5분 뒤부터, 실서버 약 3~5분).
          </p>
        </div>
      )}

      {daily.length > 0 && (
        <section className="card" style={{ marginBottom: 16 }} data-testid="flow-daily">
          <h2 style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>개미 투자 동향 — 날짜별 순매수 합계</h2>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 12.5, marginBottom: 10 }}>
            <span>최근 5일 개인 <strong><Amt v={sum5.prsn} /></strong></span>
            <span>외국인 <strong><Amt v={sum5.frgn} /></strong></span>
            <span>기관 <strong><Amt v={sum5.orgn} /></strong></span>
            {last && <span style={{ color: "var(--text-muted)" }}>{last.date} 쌍끌이 {last.double}종목</span>}
          </div>
          <DailyBars daily={daily} />
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
            수집한 종목(거래대금 1억↑ + 추천·관심 종목)만 더한 값이라 거래소 발표 합계와 조금 다를 수 있어요. 막대에 마우스를 올리면 금액.
          </p>
        </section>
      )}

      {data?.retail && (
        <section className="card" style={{ marginBottom: 16, fontSize: 12.5, lineHeight: 1.7 }} data-testid="flow-retail">
          <h2 style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>개미만 사는 종목은 약했나? (과거 사례로 판단)</h2>
          {data.retail.retail?.n ? (
            <>
              <div>
                '{data.retail.rule}' 종목을 다음 날 종가에 샀다면 {data.retail.horizon}거래일 뒤 같은 날 전 종목 중간값 대비 평균{" "}
                <strong style={{ color: (data.retail.retail.avg_excess ?? 0) < 0 ? "var(--red)" : "var(--green)" }}>
                  {data.retail.retail.avg_excess > 0 ? "+" : ""}{data.retail.retail.avg_excess}%p</strong>, 이긴 비율 <strong>{data.retail.retail.beat_rate}%</strong>
                {" "}({data.retail.retail.n.toLocaleString()}건 · {data.retail.dates}일).
                {data.retail.double?.n ? <> 참고: 쌍끌이 2일↑ 종목은 평균 {data.retail.double.avg_excess > 0 ? "+" : ""}{data.retail.double.avg_excess}%p ({data.retail.double.n.toLocaleString()}건).</> : null}
              </div>
              <div style={{ fontWeight: 600, color: data.retail.active ? "var(--red)" : "var(--text-secondary)" }}>
                {data.retail.active ? `→ 실제로 약했음 — AI 모의투자·KIS 주문 판단에서 AI 점수 −${data.retail.penalty}점`
                  : `→ 감점 안 함 (기준: ${data.retail.need})`}
              </div>
            </>
          ) : <span style={{ color: "var(--text-muted)" }}>판단할 과거 사례가 아직 없습니다 — 수급이 쌓이고 20거래일 뒤 결과가 나와야 계산됩니다 (그동안 감점 안 함).</span>}
        </section>
      )}

      {picked && <StockQuoteCard item={picked} onClose={() => setPicked(null)} actions={<WatchButton item={picked} />} />}

      {data?.date && (
        <>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
            {LISTS.map(([k, label]) => (
              <button key={k} className={`btn ${list === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "5px 10px" }}
                onClick={() => setList(k)}>{label} <span style={{ opacity: 0.7 }}>{data.lists?.[k]?.length ?? 0}</span></button>
            ))}
          </div>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>{LISTS.find((x) => x[0] === list)?.[2]}</p>
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="data-table" data-testid="flow-table">
              <thead>
                <tr><th>종목</th><th>신호</th><th className="num">외국인 5일</th><th className="num">기관 5일</th><th className="num">개인 5일</th>
                  {!narrow && <th className="num" title="5일 외국인+기관 순매수 ÷ 5일 거래대금">강도</th>}{!narrow && <th className="num">종가</th>}<th></th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol} style={{ cursor: "pointer" }} onClick={() => setPicked({ market: "KR", symbol: r.symbol, name: r.name })}>
                    <td><div style={{ fontWeight: 600 }}>{r.name}</div><div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{r.symbol}</div></td>
                    <td style={{ fontSize: 11.5, whiteSpace: "nowrap", color: r.streak > 0 ? "var(--green)" : r.sell_streak > 1 ? "var(--red)" : "var(--text-secondary)" }}>{r.label || "-"}</td>
                    <td className="num"><Amt v={r.frgn_amt5} /></td>
                    <td className="num"><Amt v={r.orgn_amt5} /></td>
                    <td className="num"><Amt v={r.prsn_amt5} /></td>
                    {!narrow && <td className="num">{r.intensity == null ? "-" : `${r.intensity > 0 ? "+" : ""}${r.intensity}%`}</td>}
                    {!narrow && <td className="num">{fmtPrice(r.price, "KR")}</td>}
                    <td onClick={(e) => e.stopPropagation()}><WatchButton item={{ market: "KR", symbol: r.symbol, name: r.name }} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <p style={{ padding: 20, color: "var(--text-muted)", textAlign: "center" }}>해당 종목이 없습니다</p>}
          </div>
        </>
      )}
    </div>
  );
}
