import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { RefreshCw, Info } from "lucide-react";
import { accumApi, errMsg } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import StockQuoteCard from "../components/common/StockQuoteCard";
import WatchButton from "../components/common/WatchButton";
import AccumBadge from "../components/common/AccumBadge";

const PART_HELP: Record<string, string> = {
  "횡보": "최근 60거래일 가격 범위가 좁음 (20% 이하 만점)",
  "변동성 축소": "최근 20일 하루 변동폭이 그 전 40일보다 줄어듦",
  "OBV 매집": "가격은 제자리인데 상승일 거래량이 하락일보다 많이 쌓임 (OBV 증가)",
  "거래량 꿈틀": "최근 5일 거래량이 평소의 1.5배 이상인데 가격은 아직 ±8% 안",
  "저점 상승": "최근 20일 최저가가 그 전 20일 최저가보다 높음",
  "바닥권": "200일 가격 범위의 아래쪽 35% 안",
};

function Verdict({ val }: { val: any[] }) {
  const base = val.find((v) => v.min_score === 0);
  const hi = val.find((v) => v.min_score === 60);
  if (!base?.n || !hi?.n) return <span>검증 표본이 아직 부족합니다.</span>;
  if (hi.n < 100) return <span>점수 60 이상 표본이 {hi.n}건뿐이라 아직 판단하기 이릅니다.</span>;
  if ((hi.lift ?? 0) >= 1.3)
    return <span style={{ color: "var(--green)" }}>점수 60 이상은 전체 평균보다 <strong>{hi.lift}배</strong> 자주 급등했습니다 — 의미 있는 신호로 보입니다 (그래도 대부분은 급등하지 않음).</span>;
  if ((hi.lift ?? 0) >= 1.1)
    return <span style={{ color: "var(--yellow)" }}>점수 60 이상이 평균보다 조금({hi.lift}배) 자주 급등 — 약한 신호, 참고만 하세요.</span>;
  return <span style={{ color: "var(--red)" }}>최근에는 점수가 높아도 평균보다 더 자주 급등하지 않았습니다 ({hi.lift ?? "-"}배) — 이 신호를 믿지 마세요.</span>;
}

export default function Accumulation() {
  const [minScore, setMinScore] = useState(60);
  const [exchange, setExchange] = useState<"ALL" | "KOSPI" | "KOSDAQ">("ALL");
  const [picked, setPicked] = useState<any>(null);

  const q = useQuery({
    queryKey: ["accumulation"],
    queryFn: () => accumApi.result(50).then((r) => r.data),
    refetchInterval: (qq) => (qq.state.data?.status?.running ? 3000 : 5 * 60_000),
  });
  const scan = useMutation({ mutationFn: () => accumApi.scan(), onSuccess: () => setTimeout(() => q.refetch(), 1000) });

  const st = q.data?.status;
  const meta = q.data?.result;
  const val: any[] = q.data?.validation || [];
  const rows: any[] = (q.data?.candidates || []).filter(
    (c: any) => c.score >= minScore && (exchange === "ALL" || c.exchange === exchange));
  const rules = meta?.rules || { hit_up_pct: 20, horizon_days: 20 };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>매집·바닥 다지기 탐지</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            몇 주~몇 달 좁게 횡보하면서 거래량이 조용히 쌓이는, 급등 전에 흔히 보이는 패턴을 국내 전 종목에서 점수로 찾습니다 (하루 1번, 장 마감 후)
          </p>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            {meta ? <>{meta.base_date} 종가 기준 · {meta.scanned?.toLocaleString()}/{meta.universe?.toLocaleString()}종목 계산{meta.errors ? ` · 조회 실패 ${meta.errors}건` : ""}</> : "아직 계산 결과 없음"}
            {st?.stale && !st?.running && meta && " · 최신 거래일 결과 아님 (장 마감 후 자동 계산)"}
          </p>
          {st?.running && (
            <p style={{ fontSize: 12, color: "var(--accent)", marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
              <RefreshCw size={12} className="spin" /> 전 종목 계산 중 {st.done.toLocaleString()}/{st.total.toLocaleString()} (실서버 7~10분 · 화면 조회가 먼저 처리돼서 다른 화면은 느려지지 않음)
            </p>
          )}
          {st?.message && !st.running && <p style={{ fontSize: 11, color: st.message.startsWith("실패") ? "var(--red)" : "var(--text-muted)", marginTop: 2 }}>마지막 실행: {st.message}</p>}
        </div>
        <button className="btn btn-ghost" style={{ fontSize: 12 }} disabled={scan.isPending || st?.running} onClick={() => scan.mutate()}>
          <RefreshCw size={13} /> 지금 다시 계산
        </button>
      </div>

      {q.error && !q.data && <p style={{ color: "var(--red)", marginBottom: 12 }}>조회 실패: {errMsg(q.error)}</p>}
      {scan.error && <p style={{ color: "var(--red)", marginBottom: 12, fontSize: 12 }}>실행 실패: {errMsg(scan.error)}</p>}

      {/* 검증: 이 점수가 실제로 급등을 앞섰나 */}
      {val.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <p style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>이 점수, 실제로 맞았나? (최근 몇 달 검증)</p>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 10 }}>
            과거 각 날짜에 그날까지의 데이터로만 점수를 매기고, 그 뒤 {rules.horizon_days}거래일 안에 +{rules.hit_up_pct}% 이상 오른 적이 있으면 적중.
            "기준 대비"가 1보다 확실히 커야 의미가 있습니다.
          </p>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)", fontSize: 11 }}>
                {["점수", "표본(종목×날짜)", `${rules.horizon_days}일 안 +${rules.hit_up_pct}% 도달`, `평균 ${rules.horizon_days}일 수익률`, "기준 대비"].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {val.map((v) => (
                <tr key={v.min_score} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "6px 8px" }}>{v.min_score === 0 ? "전체 (기준)" : `${v.min_score}점 이상`}</td>
                  <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums" }}>{v.n.toLocaleString()}</td>
                  <td style={{ padding: "6px 8px", fontWeight: 600 }}>{v.hit_rate != null ? `${v.hit_rate}%` : "-"}</td>
                  <td style={{ padding: "6px 8px" }}>{v.avg_ret20 != null ? `${v.avg_ret20 >= 0 ? "+" : ""}${v.avg_ret20}%` : "-"}</td>
                  <td style={{ padding: "6px 8px", fontWeight: 600, color: (v.lift ?? 0) >= 1.3 ? "var(--green)" : (v.lift ?? 0) >= 1.1 ? "var(--yellow)" : "var(--text-secondary)" }}>
                    {v.lift != null ? `${v.lift}배` : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 12, marginTop: 10, display: "flex", gap: 6 }}><Info size={13} style={{ flexShrink: 0, marginTop: 2 }} /><Verdict val={val} /></p>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            현재 상장된 종목만 계산하므로(상장폐지 종목 빠짐) 실제보다 조금 좋게 나올 수 있습니다. 뉴스·공시 같은 급등 재료는 반영하지 않습니다.
          </p>
        </div>
      )}

      {/* 필터 */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>점수</span>
        {[50, 60, 70, 80].map((s) => (
          <button key={s} className={`btn ${minScore === s ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => setMinScore(s)}>{s}점 이상</button>
        ))}
        <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 10 }}>시장</span>
        {(["ALL", "KOSPI", "KOSDAQ"] as const).map((x) => (
          <button key={x} className={`btn ${exchange === x ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => setExchange(x)}>{x === "ALL" ? "전체" : x === "KOSPI" ? "코스피" : "코스닥"}</button>
        ))}
        <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: "auto" }}>{rows.length}종목</span>
      </div>

      {picked && <StockQuoteCard item={picked} onClose={() => setPicked(null)} actions={<WatchButton item={picked} />} />}

      {q.isLoading ? <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p> : rows.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 32, color: "var(--text-muted)", fontSize: 13 }}>
          {meta ? "조건에 맞는 종목이 없습니다 — 점수 기준을 낮춰 보세요" : st?.running ? "계산이 끝나면 여기에 표시됩니다" : "아직 계산 결과가 없습니다 — 장 마감 후 자동으로 계산하거나 '지금 다시 계산'을 누르세요"}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {rows.map((c) => (
            <div key={c.symbol} className="card" style={{ padding: "12px 16px", cursor: "pointer" }}
                 onClick={() => setPicked({ market: "KR", symbol: c.symbol, name: c.name })}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <AccumBadge score={c.score} />
                <div style={{ minWidth: 160 }}>
                  <p style={{ fontWeight: 700, fontSize: 14 }}>{c.name} <span style={{ fontWeight: 400, fontSize: 11, color: "var(--text-muted)" }}>{c.symbol} · {c.exchange === "KOSPI" ? "코스피" : "코스닥"}</span></p>
                  {c.themes?.length > 0 && <p style={{ fontSize: 11, color: "var(--text-muted)" }}>테마: {c.themes.join(", ")}</p>}
                </div>
                <span style={{ fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>₩{c.price.toLocaleString()}</span>
                <ChangeTag value={c.change_rate} />
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  20일 {c.ret20 >= 0 ? "+" : ""}{c.ret20}% · 60일 {c.ret60 >= 0 ? "+" : ""}{c.ret60}% · 거래대금 {c.tv20_eok}억/일
                </span>
                <span style={{ marginLeft: "auto" }}><WatchButton item={{ symbol: c.symbol, market: "KR", name: c.name }} /></span>
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                {c.parts.map((p: any) => {
                  const r = p.score / p.max;
                  const color = r >= 0.99 ? "var(--green)" : r > 0 ? "var(--yellow)" : "var(--text-muted)";
                  return (
                    <span key={p.name} title={`${PART_HELP[p.name] || ""}\n${p.detail}`} style={{
                      fontSize: 11, padding: "3px 8px", borderRadius: 6, color,
                      background: `color-mix(in srgb, ${color} 10%, transparent)`,
                    }}>
                      {p.name} {p.score}/{p.max} · {p.detail}
                    </span>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
