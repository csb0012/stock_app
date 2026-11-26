import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { guruApi, errMsg } from "../api/client";
import FetchStatus from "../components/common/FetchStatus";
import WatchButton from "../components/common/WatchButton";
import StockQuoteCard from "../components/common/StockQuoteCard";
import { changeLabel, changeColor } from "../components/common/SignalBadges";
import { fmtUsdBig, fmtNum } from "../components/common/format";
import { useNarrow } from "../components/common/useNarrow";

type Tab = "gurus" | "stocks" | "validation";

function quarter(period?: string | null): string {
  if (!period) return "-";
  const [y, m] = period.split("-");
  return `${y}년 ${Math.ceil(Number(m) / 3)}분기`;
}

function Ret({ v }: { v: number | null | undefined }) {
  if (v == null) return <span style={{ color: "var(--text-muted)" }}>-</span>;
  return <span style={{ color: v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : undefined, fontWeight: 700 }}>{v > 0 ? "+" : ""}{v.toFixed(1)}%</span>;
}

function Avatar({ name }: { name: string }) {
  return (
    <div style={{ width: 40, height: 40, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", fontWeight: 700,
      background: "color-mix(in srgb, var(--accent) 14%, transparent)", color: "var(--accent)", fontSize: 15 }}>
      {name.slice(0, 1)}
    </div>
  );
}

function GuruDetail({ k, onPick, onClose }: { k: string; onPick: (x: any) => void; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({ queryKey: ["guru", k], queryFn: () => guruApi.detail(k).then((r) => r.data), staleTime: 30 * 60 * 1000 });
  const g = data?.guru;
  const narrow = useNarrow();
  return (
    <section className="card" style={{ marginBottom: 16 }} data-testid="guru-detail">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 10 }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700 }}>{g?.name ?? k} <span style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>{g?.firm}</span></h2>
          {g && (
            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
              {g.style} · {quarter(g.period)} 말 기준 (공시 {g.filed}) · {g.n_holdings?.toLocaleString()}종목 · {fmtUsdBig(g.total_value)}
              {g.prev_period && ` · 변화는 ${quarter(g.prev_period)} 대비`}
            </p>
          )}
        </div>
        <button className="btn btn-ghost" style={{ fontSize: 12, alignSelf: "flex-start" }} onClick={onClose}>닫기</button>
      </div>
      {isLoading && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>불러오는 중...</p>}
      {error && <p style={{ color: "var(--red)", fontSize: 13 }}>{errMsg(error)}</p>}
      {data && (
        <div style={{ overflowX: "auto" }}>
          <table className="data-table">
            <thead><tr><th>종목</th><th className="num">비중</th><th>직전 분기 대비</th>{!narrow && <th className="num">1년 등락</th>}{!narrow && <th className="num">보유 대가</th>}</tr></thead>
            <tbody>
              {data.holdings.slice(0, 60).map((h: any) => (
                <tr key={h.cusip} style={{ cursor: h.ticker ? "pointer" : undefined }}
                  onClick={() => h.ticker && onPick({ market: "US", symbol: h.ticker, name: h.name || h.issuer })}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{h.name || h.issuer}</div>
                    <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{h.ticker || "티커 변환 전"} · {h.cls}</div>
                  </td>
                  <td className="num">{h.weight.toFixed(1)}%</td>
                  <td style={{ color: changeColor(h.change), fontWeight: 600 }}>{changeLabel(h.change, h.share_change_pct)}</td>
                  {!narrow && <td className="num"><Ret v={h.change_52w} /></td>}
                  {!narrow && <td className="num">{h.n_holders ?? "-"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
          {data.holdings.length > 60 && <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>비중 큰 60종목만 표시 (전체 {data.holdings.length}종목)</p>}
          {data.sold?.length > 0 && (
            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 10, lineHeight: 1.7 }}>
              <strong style={{ color: "var(--red)" }}>전량 매도:</strong>{" "}
              {data.sold.slice(0, 15).map((s: any) => `${s.ticker || s.issuer}(${s.prev_weight}%)`).join(", ")}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

export default function Gurus() {
  const [tab, setTab] = useState<Tab>("gurus");
  const [sort, setSort] = useState("holders");
  const [sel, setSel] = useState<string | null>(null);
  const [picked, setPicked] = useState<any>(null);
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["gurus"], queryFn: () => guruApi.list().then((r) => r.data), staleTime: 10 * 60 * 1000,
    refetchInterval: (q) => (q.state.data?.status?.running ? 5000 : false) });
  const stocks = useQuery({ queryKey: ["guru-stocks", sort], queryFn: () => guruApi.stocks(sort).then((r) => r.data),
    staleTime: 10 * 60 * 1000, enabled: tab === "stocks" });
  const refresh = useMutation({ mutationFn: () => guruApi.refresh(), onSuccess: () => qc.invalidateQueries({ queryKey: ["gurus"] }) });
  const d = list.data;
  const st = d?.status;
  const v = d?.validation;
  const va = d?.validation_ai;

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>투자 대가의 포트폴리오</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13, lineHeight: 1.6 }}>
          미국 SEC 13F 공시(운용자산 1억 달러↑ 기관이 분기마다 내는 미국 주식 보유 목록)로 본 대가들의 보유 종목과 변화.
          분기 말 기준이고 <strong>최대 45일 늦게</strong> 공개돼서 지금은 이미 팔았을 수 있어요. 대가가 산 종목은 AI 추천의 근거로 붙고,
          '따라 사기 검증'이 시장보다 나았을 때만 AI 장기 점수에 더해집니다.
        </p>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {([["gurus", "투자 대가"], ["stocks", "대가들이 산 종목"], ["validation", "따라 사기 검증"]] as [Tab, string][]).map(([t, label]) => (
            <button key={t} className={`btn ${tab === t ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "5px 10px" }}
              onClick={() => setTab(t)}>{label}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 11.5, color: "var(--text-muted)", flexWrap: "wrap" }}>
          {st?.running && <span style={{ color: "var(--accent)" }}>받는 중: {st.step} {st.step?.startsWith("SEC") ? `${st.done}/${st.total}` : st.cusip_pending ? `(남은 ${st.cusip_pending})` : ""}</span>}
          {d?.updated_at && <span>{d.updated_at.replace("T", " ").slice(0, 16)} 갱신</span>}
          <FetchStatus updatedAt={list.dataUpdatedAt} fetching={list.isFetching} />
          <button className="btn btn-ghost" style={{ fontSize: 11.5, padding: "4px 8px" }} disabled={st?.running || refresh.isPending}
            onClick={() => refresh.mutate()}>다시 받기</button>
        </div>
      </div>

      {list.isLoading && <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>}
      {list.error && <p style={{ color: "var(--red)" }}>{errMsg(list.error)}</p>}
      {d && d.gurus.length === 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 13, color: (st?.message || "").startsWith("실패") ? "var(--red)" : "var(--text-secondary)" }}>
            {(st?.message || "").startsWith("실패") ? st.message
              : "아직 대가 포트폴리오가 없습니다 — 서버 시작 3분 뒤 SEC 에서 받습니다 (처음 한 번은 티커 변환 때문에 5~10분)."}
          </p>
        </div>
      )}
      {d?.errors?.length > 0 && (
        <p style={{ fontSize: 11.5, color: "var(--yellow)", marginBottom: 10 }} title={d.errors.join("\n")}>
          ⚠ 일부 못 받음 {d.errors.length}건: {d.errors[0]}
        </p>
      )}

      {picked && <StockQuoteCard item={picked} onClose={() => setPicked(null)} actions={<WatchButton item={picked} />} />}
      {sel && tab === "gurus" && <GuruDetail k={sel} onPick={setPicked} onClose={() => setSel(null)} />}

      {tab === "gurus" && d && d.gurus.length > 0 && (
        <div className="card" style={{ padding: "6px 0" }} data-testid="guru-list">
          <p style={{ fontSize: 11.5, color: "var(--text-muted)", padding: "6px 16px" }}>
            최근 1년 추정 수익률 · 높은 순 — 지금 보유 종목들의 최근 1년 주가 수익률을 비중대로 평균 낸 값 (실제 펀드 수익률 아님)
          </p>
          {d.gurus.map((g: any) => (
            <button key={g.key} onClick={() => setSel(g.key === sel ? null : g.key)} data-testid="guru-row"
              style={{ display: "flex", width: "100%", alignItems: "center", gap: 12, padding: "12px 16px", textAlign: "left",
                background: sel === g.key ? "var(--bg-hover)" : "transparent", border: "none", borderTop: "1px solid var(--border)",
                color: "inherit", cursor: "pointer" }}>
              <Avatar name={g.name} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{g.name} <span style={{ fontSize: 11.5, color: "var(--text-muted)", fontWeight: 500 }}>{g.firm}</span></div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>{g.style}</div>
                <div style={{ fontSize: 11, color: g.stale ? "var(--yellow)" : "var(--text-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {quarter(g.period)}{g.stale ? " (최근 공시 없음)" : ""} · {g.n_holdings}종목
                  {g.n_new > 0 && <span style={{ color: "var(--green)" }}> · 신규 {g.n_new}</span>}
                  {g.n_sold > 0 && <span style={{ color: "var(--red)" }}> · 전량 매도 {g.n_sold}</span>}
                  {" · "}{g.top.slice(0, 3).map((t: any) => `${t.ticker || t.issuer} ${t.weight.toFixed(0)}%`).join(", ")}
                </div>
              </div>
              <div style={{ fontSize: 17, textAlign: "right" }} title={`보유 비중 ${g.est_coverage}% 의 종목으로 계산`}><Ret v={g.est_return_1y} /></div>
            </button>
          ))}
        </div>
      )}

      {tab === "stocks" && (
        <>
          <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
            {([["holders", "많이 보유"], ["buyers", "이번 분기 많이 산"], ["sellers", "이번 분기 많이 판"]] as [string, string][]).map(([s, label]) => (
              <button key={s} className={`btn ${sort === s ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "4px 9px" }} onClick={() => setSort(s)}>{label}</button>
            ))}
          </div>
          {stocks.error && <p style={{ color: "var(--red)" }}>{errMsg(stocks.error)}</p>}
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="data-table" data-testid="guru-stocks">
              <thead><tr><th>종목</th><th className="num">보유 대가</th><th>이번 분기 산 대가</th><th>판 대가</th><th className="num">1년 등락</th><th className="num">PER</th><th></th></tr></thead>
              <tbody>
                {(stocks.data?.items || []).map((s: any) => (
                  <tr key={s.ticker} style={{ cursor: "pointer" }} onClick={() => setPicked({ market: "US", symbol: s.ticker, name: s.name })}>
                    <td><div style={{ fontWeight: 600 }}>{s.name}</div><div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{s.ticker}</div></td>
                    <td className="num" title={s.holders.map((h: any) => `${h.name} ${h.weight}%`).join("\n")}>{s.n_holders}</td>
                    <td style={{ color: "var(--green)", maxWidth: 220 }}>{s.buyers.map((h: any) => h.name).join(", ") || "-"}</td>
                    <td style={{ color: "var(--red)", maxWidth: 180 }}>{s.sellers.map((h: any) => h.name).join(", ") || "-"}</td>
                    <td className="num"><Ret v={s.change_52w} /></td>
                    <td className="num">{fmtNum(s.per)}</td>
                    <td onClick={(e) => e.stopPropagation()}><WatchButton item={{ market: "US", symbol: s.ticker, name: s.name }} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {stocks.data && stocks.data.items.length === 0 && <p style={{ padding: 20, color: "var(--text-muted)", textAlign: "center" }}>해당 종목이 없습니다</p>}
          </div>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>보유 = 포트폴리오 비중 0.2% 이상. 산 대가 = 신규 매수 또는 주식 수 25% 이상 늘림. 최근 공시가 없는 대가는 합계에서 뺌.</p>
        </>
      )}

      {tab === "validation" && (
        <section className="card" data-testid="guru-validation">
          <h2 style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>대가를 따라 샀다면? (과거 공시로 검증)</h2>
          {!v ? <p style={{ fontSize: 12, color: "var(--text-muted)" }}>검증 결과가 아직 없습니다.</p> : (
            <>
              <p style={{ fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.7, marginBottom: 10 }}>
                지난 공시마다 대가가 <strong>의미 있게 산 종목</strong>(신규 또는 25%↑ 추가, 비중 1%↑)을 공시가 나온 <strong>다음 거래일 종가</strong>에 사서
                {v.horizon_days}거래일(약 3개월) 들고 있었다면 — S&P500(SPY) 대비 평균{" "}
                <strong style={{ color: (v.avg_excess ?? 0) > 0 ? "var(--green)" : "var(--red)" }}>{v.avg_excess == null ? "-" : `${v.avg_excess > 0 ? "+" : ""}${v.avg_excess}%p`}</strong>,
                {" "}시장을 이긴 비율 <strong>{v.beat_rate ?? "-"}%</strong> ({v.n}건{v.pending ? `, 아직 기간이 안 끝난 ${v.pending}건 제외` : ""}).
                {" "}대가 2명 이상이 같은 분기에 산 종목은 평균 {v.multi?.avg_excess == null ? "-" : `${v.multi.avg_excess > 0 ? "+" : ""}${v.multi.avg_excess}%p`} ({v.multi?.n ?? 0}건).
              </p>
              <p style={{ fontSize: 12.5, marginBottom: 12, fontWeight: 600, color: v.validated ? "var(--green)" : "var(--yellow)" }}>
                {v.validated ? "✓ 시장보다 나았음 → 대가가 산 미국 종목은 AI 장기 점수에 최대 +10점"
                  : "시장보다 낫다고 볼 근거가 부족 (표본 30↑·평균 초과수익 > 0·이긴 비율 50%↑ 필요) → AI 추천엔 근거로만 표시하고 점수엔 안 넣음"}
              </p>
              {va && (
                <div data-testid="guru-validation-ai" style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px", marginBottom: 12, fontSize: 12.5, lineHeight: 1.7 }}>
                  <strong>대가가 산 종목 + AI 가 다시 분석해서 좋은 것만 샀다면</strong> ({va.rule}, 공시일 종가까지의 데이터로 판단)
                  <div>
                    {va.signals}건 중 AI 통과 <strong>{va.passed}</strong>건 → S&P500 대비 평균{" "}
                    <strong style={{ color: (va.avg_excess ?? 0) > 0 ? "var(--green)" : "var(--red)" }}>{va.avg_excess == null ? "-" : `${va.avg_excess > 0 ? "+" : ""}${va.avg_excess}%p`}</strong>,
                    {" "}이긴 비율 <strong>{va.beat_rate ?? "-"}%</strong> ({va.n}건 기간 끝남)
                  </div>
                  <div style={{ fontWeight: 600, color: va.validated ? "var(--green)" : "var(--yellow)" }}>
                    {va.validated ? "✓ 통과 → 대가가 이번 분기에 산 종목을 AI 모의투자·KIS 미국 주문의 판단 후보에 넣습니다 (사고팔지는 AI 점수가 정함)"
                      : "미달 → 대가 종목을 판단 후보에 넣지 않습니다 (대가를 무조건 따라가지 않음). 이미 후보인 종목엔 '대가 매수' 이유만 붙음"}
                  </div>
                </div>
              )}
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead><tr><th>대가</th><th className="num">건수</th><th className="num">평균 수익률</th><th className="num">S&P500 대비</th><th className="num">이긴 비율</th></tr></thead>
                  <tbody>
                    {Object.entries(v.by_guru || {}).sort((a: any, b: any) => b[1].n - a[1].n).map(([k, x]: any) => (
                      <tr key={k}>
                        <td>{d?.gurus.find((g: any) => g.key === k)?.name ?? k}</td>
                        <td className="num">{x.n}</td>
                        <td className="num"><Ret v={x.avg_return} /></td>
                        <td className="num"><Ret v={x.avg_excess} /></td>
                        <td className="num">{x.beat_rate}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8, lineHeight: 1.6 }}>
                최근 2년 공시(대가당 최대 8분기)만 써서 표본이 작아요. 수수료·세금 제외, 주가는 배당 포함 수정주가(Yahoo). 상장폐지·티커 변환 실패 종목은 빠짐({v.missing}건).
              </p>
            </>
          )}
        </section>
      )}
    </div>
  );
}
