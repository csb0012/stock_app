import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { marketApi, errMsg } from "../../api/client";
import FetchStatus from "./FetchStatus";

const COLOR: Record<string, string> = { "상승 추세": "var(--green)", "상승 압박": "var(--yellow)", "하락 추세": "var(--red)" };

export function useRegime() {
  return useQuery({
    queryKey: ["market-regime"],
    queryFn: () => marketApi.regime().then((r) => r.data),
    staleTime: 30 * 60 * 1000,
  });
}

const sgn = (v: number | null | undefined) => (v == null ? "-" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`);

/** 대시보드: 지수별 시장 상태 (CAN SLIM 'M') + 상태별 과거 검증 */
export default function MarketRegimePanel() {
  const { data, error, isLoading, isFetching } = useRegime();
  const [open, setOpen] = useState(false);
  const items: any[] = data ? Object.values(data.items || {}) : [];
  return (
    <section className="card" data-testid="market-regime" style={{ marginBottom: 20, padding: "14px 16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <h2 style={{ fontSize: 13, fontWeight: 700 }}>
          시장 상태 <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: 11 }}>· 지수 추세(50·200일선) + 매도 흔적(분산일) — 개별 종목 신호를 믿을 만한 장인지</span>
        </h2>
        {data && <FetchStatus updatedAt={data.updated_at} fetching={isFetching || data.refreshing} error={data.refresh_error} />}
      </div>
      {isLoading && <p style={{ fontSize: 12, color: "var(--text-muted)" }}>지수 5년치로 계산 중…</p>}
      {error && <p style={{ fontSize: 12, color: "var(--red)" }}>{errMsg(error)}</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 8 }}>
        {items.map((x) => (
          <div key={x.key} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "9px 11px", minWidth: 0 }} title={x.error || x.advice}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>{x.name}</span>
              {x.error ? <span style={{ color: "var(--red)", fontSize: 11 }}>조회 실패</span>
                : <span style={{ color: COLOR[x.state], fontWeight: 700, fontSize: 13 }}>{x.state}</span>}
            </div>
            {!x.error && (
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 3, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span>50일선 {sgn(x.vs_ma50)}</span>
                <span>200일선 {sgn(x.vs_ma200)}{x.ma200_up ? " ↗" : " ↘"}</span>
                {x.dist_days != null && <span style={{ color: x.dist_days >= 5 ? "var(--yellow)" : undefined }}>분산일 {x.dist_days}</span>}
                <span style={{ color: "var(--text-muted)" }}>{x.days_in_state}일째</span>
              </div>
            )}
            {x.stale && <div style={{ fontSize: 10.5, color: "var(--yellow)", marginTop: 2 }}>⚠ {x.stale}</div>}
          </div>
        ))}
      </div>
      {items.length > 0 && (
        <button onClick={() => setOpen(!open)} style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 8, background: "none", border: "none", padding: 0, cursor: "pointer", color: "var(--accent)", fontSize: 11.5 }}>
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />} 상태별 과거 성과 (이 기준이 실제로 의미가 있었나)
        </button>
      )}
      {open && (
        <div style={{ overflowX: "auto", marginTop: 8 }}>
          <table className="data-table">
            <thead>
              <tr><th>지수</th><th>상태</th><th className="num">날짜 수</th><th className="num">20거래일 뒤 오른 비율</th><th className="num">평균 수익률</th><th className="num">전체 평균(기준)</th></tr>
            </thead>
            <tbody>
              {items.filter((x) => !x.error).flatMap((x) => x.validation.map((v: any) => (
                <tr key={`${x.key}-${v.state}`}>
                  <td>{x.name}</td>
                  <td style={{ color: COLOR[v.state] }}>{v.state}{v.state === x.state ? " ◀ 지금" : ""}</td>
                  <td className="num">{v.n}</td>
                  <td className="num">{v.up_rate == null ? "-" : `${v.up_rate}%`}</td>
                  <td className="num">{v.avg_ret == null ? "-" : sgn(v.avg_ret)}</td>
                  <td className="num" style={{ color: "var(--text-muted)" }}>{v.base_up_rate == null ? "-" : `${v.base_up_rate}%`}</td>
                </tr>
              )))}
            </tbody>
          </table>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
            기간: {items.find((x) => !x.error)?.period?.join(" ~ ")} (Yahoo 일봉 5년). 분산일 = 최근 25거래일 중 0.2% 이상 하락 + 거래량 증가한 날 (IBD 방식).
            과거 경향일 뿐 앞으로도 같다는 보장은 없음.
          </p>
        </div>
      )}
    </section>
  );
}

/** 추천·관심종목 화면 위 경고: 그 시장 지수가 하락 추세/상승 압박이면 */
export function RegimeWarning({ market }: { market: "KR" | "US" }) {
  const { data } = useRegime();
  if (!data) return null;
  const keys = market === "KR" ? ["KOSPI", "KOSDAQ"] : ["SPX", "NASDAQ"];
  const bad = keys.map((k) => data.items?.[k]).filter((x: any) => x && !x.error && x.state !== "상승 추세");
  if (!bad.length) return null;
  const worst = bad.find((x: any) => x.state === "하락 추세") || bad[0];
  const v = worst.validation?.find((r: any) => r.state === worst.state);
  return (
    <p data-testid="regime-warning" style={{
      fontSize: 12, marginBottom: 12, padding: "8px 12px", borderRadius: 8,
      background: `color-mix(in srgb, ${COLOR[worst.state]} 9%, transparent)`, color: "var(--text-secondary)",
    }}>
      <strong style={{ color: COLOR[worst.state] }}>⚠ {bad.map((x: any) => `${x.name} ${x.state}`).join(" · ")}</strong> — {worst.advice}
      {v?.up_rate != null && <span style={{ color: "var(--text-muted)" }}> (과거 이 상태에서 20거래일 뒤 {worst.name} 오른 비율 {v.up_rate}%, 평소 {v.base_up_rate}%)</span>}
    </p>
  );
}
