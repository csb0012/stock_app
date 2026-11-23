import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { quantApi, errMsg } from "../api/client";
import FetchStatus from "../components/common/FetchStatus";
import WatchButton from "../components/common/WatchButton";
import StockQuoteCard from "../components/common/StockQuoteCard";
import { FACTOR_NAMES, gradeOf, gradeColor } from "../components/common/QuantBadge";
import { RegimeWarning } from "../components/common/MarketRegime";
import { fmtPrice } from "../components/common/format";

const GRADE_FILTERS: [string, number][] = [["전체", 1], ["8점 이상", 8], ["9점 이상", 9]];

function Grade({ p }: { p: number | null | undefined }) {
  const g = gradeOf(p);
  return <span style={{ color: gradeColor(g), fontWeight: 700 }} title={p == null ? "" : `전 종목 중 백분위 ${p}`}>{g}</span>;
}

export default function Quant() {
  const [min, setMin] = useState(1);
  const [picked, setPicked] = useState<any>(null);
  const { data, isLoading, error, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ["quant"],
    queryFn: () => quantApi.list(150).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
  });
  const q = data?.quant;
  const st = data?.status;
  const rows: any[] = (q?.top || []).filter((t: any) => t.score >= min);
  const v = q?.validation;
  const keys: string[] = (q?.factors || []).map((f: any) => f.key);

  return (
    <div>
      <div style={{ marginBottom: 18 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>퀀트 점수</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13, lineHeight: 1.6 }}>
          국내 전 종목을 같은 날 서로 비교한 요인 등급(A+~F)과 종합 점수(1~10) · 앞으로 약 1개월(20거래일) <strong>시장 대비</strong> 성과를 보는 점수
          (Seeking Alpha 퀀트 등급 · TipRanks 스마트 점수 · IBD 상대강도 방식 참고). 요인 비중은 과거에 실제로 맞았던 정도로 자동 결정.
        </p>
      </div>

      <RegimeWarning market="KR" />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {GRADE_FILTERS.map(([label, m]) => (
            <button key={label} className={`btn ${min === m ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => setMin(m)}>{label}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 11.5, color: "var(--text-muted)" }}>
          {q && <span>{q.date} 종가 기준 · {q.universe?.toLocaleString()}종목 비교</span>}
          {st?.running && <span style={{ color: "var(--accent)" }}>전 종목 계산 중 {st.done}/{st.total}</span>}
          <FetchStatus updatedAt={dataUpdatedAt} fetching={isFetching} />
        </div>
      </div>

      {isLoading && <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>}
      {error && <p style={{ color: "var(--red)" }}>{errMsg(error)}</p>}
      {data && !q && (
        <div className="card" style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 13, color: data.error ? "var(--red)" : "var(--text-secondary)" }}>
            {data.error || "아직 퀀트 점수가 없습니다 — 매집 탐지와 같은 전 종목 스캔이 끝나면 표시됩니다 (서버 시작 2분 뒤 자동, 실서버 약 10분)."}
          </p>
        </div>
      )}

      {picked && <StockQuoteCard item={picked} onClose={() => setPicked(null)} actions={<WatchButton item={picked} />} />}

      {q && (
        <>
          {/* 검증 */}
          <section className="card" style={{ marginBottom: 16 }} data-testid="quant-validation">
            <h2 style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>이 점수가 실제로 맞았나 (처음 보는 기간에서 검증)</h2>
            {v ? (
              <>
                <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8, lineHeight: 1.6 }}>
                  {v.train[0]}~{v.train[1]} 로 요인 비중을 정하고, 그 뒤 {v.test[0]}~{v.test[1]} 에서 점수 구간별로
                  <strong> 20거래일 뒤 수익률이 그날 전 종목 중간값보다 높았던 비율</strong>을 쟀습니다 (기준 50%).
                  상위 구간 − 하위 구간 차이 <strong style={{ color: (v.spread ?? 0) > 0 ? "var(--green)" : "var(--red)" }}>{v.spread == null ? "-" : `${v.spread > 0 ? "+" : ""}${v.spread}%p`}</strong>
                  {" "}· 순위 상관(IC) {v.ic}
                </p>
                <div style={{ overflowX: "auto" }}>
                  <table className="data-table">
                    <thead><tr><th>종합 백분위</th><th className="num">표본(종목×날짜)</th><th className="num">시장 대비 이긴 비율</th><th className="num">평균 초과수익</th></tr></thead>
                    <tbody>
                      {v.buckets.map((b: any) => (
                        <tr key={b.range}>
                          <td>{b.range}{b.lo >= 80 ? " (점수 9~10)" : b.lo === 0 ? " (점수 1~2)" : ""}</td>
                          <td className="num">{b.n.toLocaleString()}</td>
                          <td className="num" style={{ color: b.beat_rate == null ? undefined : b.beat_rate >= 52 ? "var(--green)" : b.beat_rate <= 48 ? "var(--red)" : undefined, fontWeight: 600 }}>
                            {b.beat_rate == null ? "-" : `${b.beat_rate}%`}
                          </td>
                          <td className="num">{b.avg_excess == null ? "-" : `${b.avg_excess > 0 ? "+" : ""}${b.avg_excess}%`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
                  일봉 200개로 계산해서 검증 기간이 약 1~2개월로 짧습니다 — 높은 구간이 꾸준히 50%를 넘는지 며칠에 걸쳐 확인하세요. 상장폐지 종목은 빠져 있어 조금 좋게 나올 수 있음.
                </p>
              </>
            ) : <p style={{ fontSize: 12, color: "var(--text-muted)" }}>검증할 기간이 아직 부족합니다.</p>}
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 10, fontSize: 11.5, color: "var(--text-secondary)" }}>
              <span style={{ color: "var(--text-muted)" }}>요인 비중{q.useful ? "" : " (맞는 요인이 없어 같은 비중)"}:</span>
              {(q.factors || []).map((f: any) => (
                <span key={f.key} title={`${f.about}\n순위 상관(IC) ${q.ic?.[f.key]}`}>
                  {f.name} <strong>{Math.round((q.weights?.[f.key] || 0) * 100)}%</strong>
                </span>
              ))}
            </div>
          </section>

          {/* 목록 */}
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="data-table" data-testid="quant-table">
              <thead>
                <tr>
                  <th>#</th><th>종목</th><th className="num">점수</th>
                  {keys.map((k) => <th key={k} title={(q.factors || []).find((f: any) => f.key === k)?.about}>{FACTOR_NAMES[k] || k}</th>)}
                  <th className="num" title="과거 같은 점수 구간 종목이 20거래일 뒤 전 종목 중간값을 이긴 비율">시장 이김(과거)</th>
                  <th className="num">현재가</th><th>매집</th><th>테마</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t, i) => (
                  <tr key={t.symbol} style={{ cursor: "pointer" }} onClick={() => setPicked({ market: "KR", symbol: t.symbol, name: t.name })}>
                    <td style={{ color: "var(--text-muted)" }}>{i + 1}</td>
                    <td><div style={{ fontWeight: 600 }}>{t.name}</div><div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{t.symbol}</div></td>
                    <td className="num"><span style={{ color: gradeColor(t.grade), fontWeight: 700 }}>{t.score}</span> <span style={{ color: "var(--text-muted)" }}>{t.grade}</span></td>
                    {keys.map((k) => <td key={k}><Grade p={t.factors?.[k]} /></td>)}
                    <td className="num">{t.beat_rate == null ? "-" : `${t.beat_rate}%`}</td>
                    <td className="num">{fmtPrice(t.price, "KR")}</td>
                    <td>{t.accum == null ? "-" : t.accum}</td>
                    <td style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", color: "var(--text-secondary)" }}>{(t.themes || []).map((x: any) => x.name || x).join(", ") || "-"}</td>
                    <td><WatchButton item={{ market: "KR", symbol: t.symbol, name: t.name }} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <p style={{ padding: 20, color: "var(--text-muted)", textAlign: "center" }}>조건에 맞는 종목이 없습니다</p>}
          </div>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
            등급은 같은 날 전 종목 안의 순위(A+ = 상위 10%). 20일 평균 거래대금 1억 원 미만 종목은 제외. 점수는 참고용이며 투자 손실 책임은 본인에게 있습니다.
          </p>
        </>
      )}
    </div>
  );
}
