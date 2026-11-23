import type React from "react";
import { fmtPrice } from "./format";

/** 장기 보유 분석 (백엔드 services/longterm.py) — 과거 월봉으로 '그때 사서 N년 보유했다면' 통계 */

const HORIZONS: [string, string][] = [["12", "1년"], ["36", "3년"], ["60", "5년"], ["120", "10년"]];

export function yrs(months?: number | null): string {
  if (!months) return "-";
  return months % 12 === 0 ? `${months / 12}년` : `${(months / 12).toFixed(1)}년`;
}

function pct(v?: number | null, sign = true): string {
  if (v === null || v === undefined) return "-";
  return `${sign && v > 0 ? "+" : ""}${v.toFixed(v >= 100 || v <= -100 ? 0 : 1)}%`;
}

function tone(v?: number | null): string {
  return v === null || v === undefined ? "var(--text-muted)" : v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-secondary)";
}

function winColor(w: number): string {
  return w >= 90 ? "var(--green)" : w >= 70 ? "var(--yellow)" : "var(--red)";
}

/** 보유 기간별 표 — 수익률과 지금 가격 기준 예상 가격 */
export function HorizonTable({ stats, price, market }: { stats: any; price?: number | null; market: string }) {
  const rows = HORIZONS.filter(([k]) => stats.horizons?.[k]);
  if (rows.length === 0) return <p style={{ fontSize: 12, color: "var(--text-muted)" }}>{stats.advice}</p>;
  const proj = (p?: number | null) => (price && p !== null && p !== undefined ? fmtPrice(price * (1 + p / 100), market) : "");
  const cell: React.CSSProperties = { padding: "5px 6px", textAlign: "right", whiteSpace: "nowrap" };
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ color: "var(--text-muted)", fontSize: 10.5 }}>
            <th style={{ ...cell, textAlign: "left" }}>보유</th>
            <th style={cell} title="과거 모든 달에 사서 그 기간 보유했을 때 이익이 난 비율">이익 확률</th>
            <th style={cell} title="하위 10% — 열 번 중 한 번은 이보다 나빴음">나쁜 경우</th>
            <th style={cell} title="중간값 — 절반은 이보다 좋았고 절반은 나빴음">보통</th>
            <th style={cell} title="상위 10% — 열 번 중 한 번은 이보다 좋았음">좋은 경우</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([k, label]) => {
            const h = stats.horizons[k];
            return (
              <tr key={k} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ ...cell, textAlign: "left", fontWeight: 600 }} title={`과거 ${h.windows}개 구간`}>{label}</td>
                <td style={{ ...cell, fontWeight: 700, color: winColor(h.win) }}>{h.win}%</td>
                {[h.p10, h.p50, h.p90].map((p: number, i: number) => (
                  <td key={i} style={cell}>
                    <div style={{ color: tone(p), fontWeight: i === 1 ? 700 : 500 }}>{pct(p)}</div>
                    {price ? <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{proj(p)}</div> : null}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** 종목 카드 안의 장기 분석 */
export function LongTermDetail({ stats, price, market }: { stats: any; price?: number | null; market: string }) {
  if (!stats) return null;
  if (!stats.enough) return <p style={{ fontSize: 12, color: "var(--text-muted)" }}>장기 분석 불가 — {stats.reason}</p>;
  const h5 = stats.horizons?.["60"] || stats.horizons?.["36"];
  const h5label = stats.horizons?.["60"] ? "5년" : "3년";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <p style={{ fontSize: 11.5, color: "var(--text-muted)", display: "flex", gap: 10, flexWrap: "wrap" }}>
        <span>과거 {stats.years}년 ({stats.start}~{stats.end})</span>
        <span>연평균 <strong style={{ color: tone(stats.cagr) }}>{pct(stats.cagr)}</strong></span>
        {stats.volatility != null && <span>연 변동성 {stats.volatility}%</span>}
        <span>지금 고점 대비 <strong style={{ color: tone(stats.from_high) }}>{pct(stats.from_high)}</strong></span>
      </p>

      <HorizonTable stats={stats} price={price} market={market} />

      {stats.advice && (
        <p style={{ fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.6,
          background: "color-mix(in srgb, var(--accent) 6%, transparent)", borderRadius: 7, padding: "8px 10px" }}>
          💡 {stats.advice}
        </p>
      )}

      {h5?.beat != null && (
        <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          {h5label} 보유 시 <strong>{stats.bench_name}</strong>보다 나았던 비율{" "}
          <strong style={{ color: h5.beat >= 50 ? "var(--green)" : "var(--red)" }}>{h5.beat}%</strong>
          <span style={{ color: "var(--text-muted)" }}> (같은 기간 지수: 이익 확률 {h5.bench_win}% · 보통 {pct(h5.bench_p50)})</span>
        </p>
      )}
    </div>
  );
}

/** 비교 지수 카드 (코스피·나스닥·S&P 500) */
export function BenchmarkCard({ b }: { b: any }) {
  if (!b) return null;
  return (
    <div className="card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>{b.name} <span style={{ color: "var(--text-muted)", fontSize: 11, fontWeight: 400 }}>{b.ticker}</span></span>
        {b.enough && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{b.start}~{b.end} · 연평균 {pct(b.cagr)}</span>}
      </div>
      {b.enough ? (
        <>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {HORIZONS.filter(([k]) => b.horizons?.[k]).map(([k, label]) => (
              <span key={k} className="badge badge-neutral" title={`보통 ${pct(b.horizons[k].p50)} · 최악 ${pct(b.horizons[k].worst)}`}>
                {label} 보유 이익 <strong style={{ color: winColor(b.horizons[k].win), marginLeft: 3 }}>{b.horizons[k].win}%</strong>
              </span>
            ))}
          </div>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.5 }}>{b.advice}</p>
        </>
      ) : (
        <p style={{ fontSize: 12, color: "var(--yellow)" }}>⚠ {b.reason}</p>
      )}
    </div>
  );
}
