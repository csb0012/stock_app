import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, History, Play, RefreshCw, Trash2, Pause, Info, ChevronDown, ChevronUp } from "lucide-react";
import { paperApi, errMsg, type PaperParams } from "../api/client";
import { fmtPrice } from "../components/common/format";

type Market = "KR" | "US";
const TAB_KEY = "paper-tab";

function readTab(): "live" | "sim" {
  try { return localStorage.getItem(TAB_KEY) === "sim" ? "sim" : "live"; } catch { return "live"; }
}

const pctColor = (v: number | null | undefined) => (v == null ? "var(--text-secondary)" : v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-secondary)");
const pct = (v: number | null | undefined, d = 2) => (v == null ? "-" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);

// ---------------- 자산 곡선 (AI vs 지수) ----------------
function EquityChart({ points, market, bench }: { points: any[]; market: Market; bench: string }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!points || points.length < 2) {
    return <p style={{ fontSize: 12, color: "var(--text-muted)", padding: "16px 0" }}>자산 그래프는 거래일이 2일 이상 쌓이면 표시됩니다</p>;
  }
  const W = 800, H = 220, P = 6;
  const vals = points.flatMap((p) => [p.equity, p.bench].filter((v) => v != null)) as number[];
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const span = hi - lo || 1;
  const x = (i: number) => P + (i / (points.length - 1)) * (W - 2 * P);
  const y = (v: number) => H - P - ((v - lo) / span) * (H - 2 * P);
  const line = (k: string) => points.map((p, i) => (p[k] == null ? "" : `${i === 0 || points[i - 1][k] == null ? "M" : "L"}${x(i).toFixed(1)},${y(p[k]).toFixed(1)}`)).join("");
  const base = points[0].equity;
  const h = hover != null ? points[hover] : points[points.length - 1];
  return (
    <div data-testid="equity-chart">
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12, marginBottom: 6 }}>
        <span style={{ color: "var(--text-muted)" }}>{h.date}</span>
        <span><span style={{ display: "inline-block", width: 10, height: 3, background: "var(--accent)", verticalAlign: "middle", marginRight: 4 }} />
          AI {fmtPrice(h.equity, market)} <span style={{ color: pctColor(h.equity / base - 1) }}>{pct((h.equity / base - 1) * 100)}</span></span>
        {h.bench != null && <span><span style={{ display: "inline-block", width: 10, height: 3, background: "var(--text-muted)", verticalAlign: "middle", marginRight: 4 }} />
          {bench} 같은 금액 {fmtPrice(h.bench, market)} <span style={{ color: pctColor(h.bench / base - 1) }}>{pct((h.bench / base - 1) * 100)}</span></span>}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: 200, display: "block" }}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const i = Math.round(((e.clientX - r.left) / r.width) * (points.length - 1));
          setHover(Math.max(0, Math.min(points.length - 1, i)));
        }}>
        <line x1={P} x2={W - P} y1={y(base)} y2={y(base)} stroke="var(--border)" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
        <path d={line("bench")} fill="none" stroke="var(--text-muted)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        <path d={line("equity")} fill="none" stroke="var(--accent)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={H} stroke="var(--text-muted)" strokeWidth={1} vectorEffect="non-scaling-stroke" />}
      </svg>
    </div>
  );
}

function Stat({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div className="card" style={{ padding: "10px 12px", minWidth: 0 }}>
      <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>{label}</p>
      <p style={{ fontSize: 16, fontWeight: 700, color: color || "var(--text-primary)", fontVariantNumeric: "tabular-nums", wordBreak: "break-all" }}>{value}</p>
      {sub && <p style={{ fontSize: 11, color: "var(--text-muted)" }}>{sub}</p>}
    </div>
  );
}

const statGrid: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 8, marginBottom: 12 };

// ---------------- 설정 입력 ----------------
function ParamsForm({ cfg, value, onChange }: { cfg: any; value: PaperParams; onChange: (v: PaperParams) => void }) {
  const [open, setOpen] = useState(false);
  if (!cfg) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <button type="button" className="btn btn-ghost" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => setOpen(!open)}>
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />} 매매 규칙 (고급 설정)
      </button>
      {open && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8, marginTop: 8 }}>
          {Object.entries(cfg.params as Record<string, any>).map(([k, p]) => (
            <label key={k} style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              {p.label} <span style={{ color: "var(--text-muted)", fontSize: 10 }}>({p.min}~{p.max})</span>
              <input className="input" type="number" step="any" min={p.min} max={p.max} data-testid={`param-${k}`}
                value={(value as any)[k] ?? p.default}
                onChange={(e) => onChange({ ...value, [k]: e.target.value === "" ? undefined : Number(e.target.value) })}
                style={{ width: "100%", marginTop: 2 }} />
            </label>
          ))}
          <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6, marginTop: 16 }}>
            <input type="checkbox" checked={value.trailing ?? true} onChange={(e) => onChange({ ...value, trailing: e.target.checked })} />
            {cfg.trailing.label} (최고 종가 기준으로 손절가가 따라 올라감)
          </label>
        </div>
      )}
    </div>
  );
}

function MarketPick({ market, setMarket }: { market: Market; setMarket: (m: Market) => void }) {
  return (
    <div style={{ display: "flex", gap: 6 }}>
      {(["KR", "US"] as const).map((m) => (
        <button key={m} type="button" className={`btn ${market === m ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "6px 12px" }}
          onClick={() => setMarket(m)}>{m === "KR" ? "국내" : "미국"}</button>
      ))}
    </div>
  );
}

function HowItWorks({ cfg }: { cfg: any }) {
  const [open, setOpen] = useState(false);
  const w = cfg?.weights || { prob: 0.45, quant: 0.35, accum: 0.2 };
  return (
    <div className="card" style={{ marginBottom: 16, padding: "12px 16px" }}>
      <button type="button" onClick={() => setOpen(!open)} data-testid="how-toggle"
        style={{ background: "none", border: "none", color: "var(--text-primary)", fontWeight: 600, fontSize: 13, display: "flex", alignItems: "center", gap: 6, cursor: "pointer", padding: 0 }}>
        <Info size={14} /> AI 는 어떻게 사고파나요? {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.8, marginTop: 8 }} data-testid="how-body">
          <p><strong>AI 점수(0~100, 50 = 중립)</strong> = AI 추천 상승확률 {Math.round(w.prob * 100)}% + 퀀트 점수 {Math.round(w.quant * 100)}% + 매집 탐지 {Math.round(w.accum * 100)}% (매집 40점 넘는 만큼 가산)</p>
          <p><strong>경제 캘린더·시장 상태</strong>: 지수가 상승 추세면 주식 100%, 상승 압박 60%, 하락 추세 30% 까지만 · 다음 거래일에 FOMC·CPI·고용·GDP·PCE 발표나 옵션 만기일이 걸리면 새 매수 금액 절반</p>
          <p><strong>매수</strong>: AI 점수 ≥ 매수 기준 + 상승확률 ≥ {cfg?.min_prob ?? 55}% 인 종목을 점수 높은 순으로, 총자산 ÷ 최대 보유 종목 수 만큼</p>
          <p><strong>매도</strong>: 손절가·목표가는 장중에 닿으면 바로 · AI 점수 &lt; 매도 기준, 상승확률 ≤ 40%, 최대 보유일 도달은 다음 날 시가</p>
          <p><strong>다음 날 데이터를 모르는 상태</strong>: 판단은 장 마감 종가까지의 데이터로만 하고, 주문은 다음 거래일 시가에 체결됩니다 (그날 종가로 사지 않음). 퀀트 요인 비중도 그날 이미 결과가 나온 과거로만 정합니다.</p>
          <p><strong>비용</strong>: 국내 수수료 0.015%·거래세 0.20%(팔 때), 미국 수수료 0.25%, 슬리피지 0.05% 를 빼고 계산</p>
          <p style={{ color: "var(--text-muted)" }}>과거 시뮬레이션 대상 = AI 추천 후보 종목(고정 목록). 지금 점수가 높은 종목을 고르면 미래를 보고 고른 셈이라 넣지 않습니다. 뉴스·공시는 과거 기록이 없어 과거 시뮬레이션에서 빠집니다.
            실시간 모의투자는 여기에 학습 모델 포함 AI 추천 확률, 국내 전 종목 퀀트·매집 상위 종목, 내 관심·투자종목을 더합니다.</p>
        </div>
      )}
    </div>
  );
}

function TradesTable({ trades, market, testid }: { trades: any[]; market: Market; testid: string }) {
  const [n, setN] = useState(30);
  if (!trades?.length) return <p style={{ fontSize: 12, color: "var(--text-muted)" }}>아직 거래가 없습니다</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 640 }} data-testid={testid}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)", fontSize: 11 }}>
            {["날짜", "종목", "구분", "수량", "가격", "손익", "사유"].map((h) => <th key={h} style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {trades.slice(0, n).map((t, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
              <td style={{ padding: "6px 8px", whiteSpace: "nowrap", color: "var(--text-muted)" }}>{String(t.date || t.ts).slice(0, 16).replace("T", " ")}</td>
              <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>{t.name} <span style={{ color: "var(--text-muted)", fontSize: 10 }}>{t.symbol}</span></td>
              <td style={{ padding: "6px 8px", fontWeight: 600, color: t.side === "buy" ? "var(--accent)" : "var(--text-primary)" }}>{t.side === "buy" ? "매수" : "매도"}</td>
              <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums" }}>{t.qty.toLocaleString()}</td>
              <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{fmtPrice(t.price, market)}</td>
              <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", color: pctColor(t.pnl) }}>
                {t.pnl == null ? "-" : `${fmtPrice(t.pnl, market)} (${pct(t.pnl_pct, 1)})`}</td>
              <td style={{ padding: "6px 8px", color: "var(--text-secondary)", minWidth: 220 }}>{t.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {trades.length > n && <button className="btn btn-ghost" style={{ fontSize: 12, marginTop: 6 }} onClick={() => setN(n + 50)}>더 보기 ({trades.length - n}건 남음)</button>}
    </div>
  );
}

function PositionsTable({ positions, market, testid }: { positions: any[]; market: Market; testid: string }) {
  if (!positions?.length) return <p style={{ fontSize: 12, color: "var(--text-muted)" }}>보유 종목 없음 (전부 현금)</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 640 }} data-testid={testid}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)", fontSize: 11 }}>
            {["종목", "수량", "매입가", "현재가", "수익률", "손절가", "목표가", "보유일"].map((h) => <th key={h} style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.symbol} style={{ borderBottom: "1px solid var(--border)" }} title={p.reason || ""}>
              <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>{p.name} <span style={{ color: "var(--text-muted)", fontSize: 10 }}>{p.symbol}</span></td>
              <td style={{ padding: "6px 8px" }}>{p.qty.toLocaleString()}</td>
              <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>{fmtPrice(p.avg_price, market)}</td>
              <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>{fmtPrice(p.last, market)}</td>
              <td style={{ padding: "6px 8px", fontWeight: 600, color: pctColor(p.ret_pct) }}>{pct(p.ret_pct)}</td>
              <td style={{ padding: "6px 8px", whiteSpace: "nowrap", color: "var(--red)" }}>{fmtPrice(p.stop, market)}</td>
              <td style={{ padding: "6px 8px", whiteSpace: "nowrap", color: "var(--green)" }}>{fmtPrice(p.target, market)}</td>
              <td style={{ padding: "6px 8px" }}>{p.hold_days}일</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------- 과거 시뮬레이션 ----------------
function SimDetail({ id }: { id: number }) {
  const q = useQuery({
    queryKey: ["paper-sim", id],
    queryFn: () => paperApi.sim(id).then((r) => r.data),
    refetchInterval: (qq) => (qq.state.data?.status === "running" ? 2000 : false),
  });
  const [onlyActions, setOnlyActions] = useState(true);
  const [logN, setLogN] = useState(30);
  const d = q.data;
  if (q.error && !d) return <p style={{ color: "var(--red)" }}>조회 실패: {errMsg(q.error)}</p>;
  if (!d) return <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>;
  if (d.status === "running") return <SimProgress sim={d} />;
  if (d.status === "failed") return <p style={{ color: "var(--red)" }} data-testid="sim-error">시뮬레이션 실패: {d.error}</p>;
  const r = d.result, s = r.summary, m = d.market as Market;
  const log = (r.log as any[]).filter((x) => !onlyActions || x.actions.length).slice().reverse();
  return (
    <div data-testid="sim-detail">
      <div style={statGrid}>
        <Stat label="최종 자산" value={fmtPrice(s.final_equity, m)} sub={`시작 ${fmtPrice(s.capital, m)}`} />
        <Stat label="AI 수익률" value={pct(s.return_pct)} color={pctColor(s.return_pct)} sub={`${s.start} ~ ${s.end}`} />
        <Stat label={`${r.benchmark} (같은 기간)`} value={pct(s.bench_return_pct)} color={pctColor(s.bench_return_pct)} />
        <Stat label="지수 대비" value={s.excess_pct == null ? "-" : `${s.excess_pct > 0 ? "+" : ""}${s.excess_pct.toFixed(2)}%p`} color={pctColor(s.excess_pct)} />
        <Stat label="최대 낙폭 (MDD)" value={pct(s.mdd_pct)} color="var(--red)" />
        <Stat label="승률" value={s.win_rate == null ? "-" : `${s.win_rate}%`} sub={`매도 ${s.trades}건 · 평균 ${pct(s.avg_win_pct, 1)} / ${pct(s.avg_loss_pct, 1)}`} />
        <Stat label="손익비 (이익 합 ÷ 손실 합)" value={s.profit_factor == null ? "-" : String(s.profit_factor)} />
        <Stat label="평균 주식 비중" value={`${s.avg_exposure_pct}%`} sub={`수수료·세금 ${fmtPrice(s.fees, m)}`} />
      </div>
      <div className="card" style={{ marginBottom: 12 }}>
        <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>자산 변화 — AI vs {r.benchmark}에 같은 금액을 그냥 넣어 둔 경우</p>
        <EquityChart points={r.equity} market={m} bench={r.benchmark} />
      </div>
      {r.notes?.length > 0 && (
        <div style={{ fontSize: 12, color: "var(--yellow)", marginBottom: 12 }} data-testid="sim-notes">
          {r.notes.map((n: string, i: number) => <p key={i}>⚠ {n}</p>)}
        </div>
      )}
      <div className="card" style={{ marginBottom: 12 }}>
        <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>마지막 날 보유 종목</p>
        <PositionsTable positions={r.positions} market={m} testid="sim-positions" />
      </div>
      <div className="card" style={{ marginBottom: 12 }}>
        <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>거래 내역 ({r.trades.length}건)</p>
        <TradesTable trades={(r.trades as any[]).slice().reverse()} market={m} testid="sim-trades" />
      </div>
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
          <p style={{ fontWeight: 600, fontSize: 13 }}>날짜별 AI 판단 기록</p>
          <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", gap: 4, alignItems: "center" }}>
            <input type="checkbox" checked={onlyActions} onChange={(e) => setOnlyActions(e.target.checked)} /> 거래·주문 있는 날만
          </label>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }} data-testid="sim-log">
          {log.slice(0, logN).map((x) => (
            <div key={x.date} style={{ borderTop: "1px solid var(--border)", paddingTop: 6, fontSize: 12 }}>
              <p style={{ color: "var(--text-muted)" }}>{x.date} · 시장 {x.regime || "-"} · 자산 {fmtPrice(x.equity, m)}
                {x.top?.length > 0 && <> · 상위: {x.top.map((t: any) => `${t.name} ${t.score}`).join(", ")}</>}</p>
              {x.actions.map((a: string, i: number) => <p key={i} style={{ color: "var(--text-primary)" }}>• {a}</p>)}
              {x.notes.map((a: string, i: number) => <p key={`n${i}`} style={{ color: "var(--text-muted)" }}>· {a}</p>)}
            </div>
          ))}
          {log.length > logN && <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => setLogN(logN + 60)}>더 보기</button>}
        </div>
      </div>
    </div>
  );
}

function SimProgress({ sim }: { sim: any }) {
  const p = sim.progress;
  const ratio = p?.total ? Math.round((p.done / p.total) * 100) : 0;
  return (
    <div className="card" data-testid="sim-progress">
      <p style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}><RefreshCw size={13} className="spin" /> {p?.phase || "계산 중"} {p?.total > 1 ? `${p.done}/${p.total}` : ""}</p>
      <div style={{ height: 6, background: "var(--bg-secondary)", borderRadius: 3, marginTop: 8 }}>
        <div style={{ width: `${ratio}%`, height: "100%", background: "var(--accent)", borderRadius: 3 }} />
      </div>
      <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>1년 기준 1~3분 (종목마다 날짜별로 그날까지의 데이터로 다시 계산)</p>
    </div>
  );
}

function SimTab({ cfg }: { cfg: any }) {
  const qc = useQueryClient();
  const [market, setMarket] = useState<Market>("KR");
  const [capital, setCapital] = useState<string>("");
  const [months, setMonths] = useState(12);
  const [params, setParams] = useState<PaperParams>({});
  const [picked, setPicked] = useState<number | null>(null);
  const list = useQuery({
    queryKey: ["paper-sims"],
    queryFn: () => paperApi.sims().then((r) => r.data),
    refetchInterval: (qq) => (qq.state.data?.items?.some((s: any) => s.status === "running") ? 2000 : false),
  });
  const items: any[] = list.data?.items || [];
  useEffect(() => { if (picked == null && items.length) setPicked(items[0].id); }, [items.length]);
  const mc = cfg?.markets?.[market];
  const start = useMutation({
    mutationFn: () => paperApi.startSim(market, capital ? Number(capital) : mc?.capital, months, params).then((r) => r.data),
    onSuccess: (d) => { setPicked(d.id); qc.invalidateQueries({ queryKey: ["paper-sims"] }); },
    meta: { inlineError: true },
  });
  const remove = useMutation({
    mutationFn: (id: number) => paperApi.removeSim(id),
    onSuccess: (_r, id) => { if (picked === id) setPicked(null); qc.invalidateQueries({ queryKey: ["paper-sims"] }); },
  });
  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}><History size={15} /> 과거 데이터로 시뮬레이션</p>
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 10 }}>
          선택한 기간의 첫날부터 하루씩, <strong>그날 종가까지의 데이터만 보고</strong> 판단해 다음 날 시가에 사고팝니다.
        </p>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div><p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>시장</p><MarketPick market={market} setMarket={(m) => { setMarket(m); setCapital(""); }} /></div>
          <label style={{ fontSize: 11, color: "var(--text-muted)" }}>시작 자금 ({market === "KR" ? "원" : "달러"})
            <input className="input" type="number" data-testid="sim-capital" placeholder={mc ? String(mc.capital) : ""} value={capital}
              onChange={(e) => setCapital(e.target.value)} style={{ display: "block", width: 160, marginTop: 4 }} />
          </label>
          <div>
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>기간</p>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {(cfg?.months || [1, 3, 6, 12, 24]).map((mo: number) => (
                <button key={mo} type="button" className={`btn ${months === mo ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "6px 10px" }}
                  onClick={() => setMonths(mo)}>{mo >= 12 ? `${mo / 12}년` : `${mo}개월`}</button>
              ))}
            </div>
          </div>
          <button className="btn btn-primary" data-testid="sim-start" disabled={start.isPending || list.data?.busy} onClick={() => start.mutate()}>
            <Play size={13} /> {list.data?.busy ? "다른 시뮬레이션 계산 중" : "시뮬레이션 시작"}
          </button>
        </div>
        <ParamsForm cfg={cfg} value={params} onChange={setParams} />
        {start.error && <p style={{ color: "var(--red)", fontSize: 12, marginTop: 8 }} data-testid="sim-start-error">{errMsg(start.error)}</p>}
      </div>

      {list.error && !list.data && <p style={{ color: "var(--red)" }}>목록 조회 실패: {errMsg(list.error)}</p>}
      {items.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }} data-testid="sim-list">
          {items.map((s) => (
            <div key={s.id} className="card" onClick={() => setPicked(s.id)}
              style={{ padding: "8px 12px", cursor: "pointer", borderColor: picked === s.id ? "var(--accent)" : undefined, fontSize: 12, display: "flex", gap: 8, alignItems: "center" }}>
              <span>{s.market === "KR" ? "국내" : "미국"} · {s.months >= 12 ? `${s.months / 12}년` : `${s.months}개월`} · {fmtPrice(s.capital, s.market)}</span>
              {s.status === "running" ? <span style={{ color: "var(--accent)" }}>계산 중</span>
                : s.status === "failed" ? <span style={{ color: "var(--red)" }}>실패</span>
                : <span style={{ fontWeight: 700, color: pctColor(s.summary?.return_pct) }}>{pct(s.summary?.return_pct)}
                    <span style={{ fontWeight: 400, color: "var(--text-muted)" }}> (지수 {pct(s.summary?.bench_return_pct)})</span></span>}
              {s.status !== "running" && (
                <button className="btn btn-ghost" title="삭제" style={{ padding: "2px 4px" }}
                  onClick={(e) => { e.stopPropagation(); if (confirm("이 시뮬레이션 결과를 지울까요?")) remove.mutate(s.id); }}><Trash2 size={12} /></button>
              )}
            </div>
          ))}
        </div>
      )}
      {picked != null && items.some((s) => s.id === picked) ? <SimDetail id={picked} /> : !list.isLoading && items.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: 28, color: "var(--text-muted)", fontSize: 13 }}>아직 시뮬레이션이 없습니다 — 위에서 시작하세요</div>
      )}
    </div>
  );
}

// ---------------- 실시간 모의투자 ----------------
function AccountDetail({ id, onDeleted }: { id: number; onDeleted: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["paper-account", id],
    queryFn: () => paperApi.account(id).then((r) => r.data),
    refetchInterval: (qq) => (!qq.state.data?.log?.length ? 3000 : 30_000),
  });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["paper-account", id] }); qc.invalidateQueries({ queryKey: ["paper-accounts"] }); };
  const run = useMutation({ mutationFn: () => paperApi.run(id), onSuccess: () => setTimeout(refresh, 3000) });
  const active = useMutation({ mutationFn: (a: boolean) => paperApi.setActive(id, a), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => paperApi.removeAccount(id), onSuccess: () => { onDeleted(); qc.invalidateQueries({ queryKey: ["paper-accounts"] }); } });
  const d = q.data;
  if (q.error && !d) return <p style={{ color: "var(--red)" }}>조회 실패: {errMsg(q.error)}</p>;
  if (!d) return <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>;
  const m = d.market as Market;
  return (
    <div data-testid="account-detail">
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        <button className="btn btn-primary" style={{ fontSize: 12 }} disabled={run.isPending} onClick={() => run.mutate()} data-testid="account-run">
          <Bot size={13} /> 지금 AI 판단 실행
        </button>
        <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => active.mutate(!d.active)}>
          {d.active ? <><Pause size={13} /> 자동 매매 멈춤</> : <><Play size={13} /> 자동 매매 다시 켜기</>}
        </button>
        <button className="btn btn-ghost" style={{ fontSize: 12, color: "var(--red)" }} onClick={() => { if (confirm("이 모의투자 계좌와 거래 기록을 모두 지울까요?")) remove.mutate(); }}>
          <Trash2 size={13} /> 계좌 삭제
        </button>
      </div>
      {run.isSuccess && <p style={{ fontSize: 12, color: "var(--accent)", marginBottom: 8 }}>{(run.data as any)?.data?.message}</p>}
      {d.last_error && <p style={{ fontSize: 12, color: "var(--red)", marginBottom: 8 }} data-testid="account-error">⚠ {d.last_error}</p>}
      {d.price_error && <p style={{ fontSize: 12, color: "var(--yellow)", marginBottom: 8 }}>⚠ {d.price_error}</p>}
      {!d.active && <p style={{ fontSize: 12, color: "var(--yellow)", marginBottom: 8 }}>자동 매매가 멈춰 있습니다 — 장 마감 후 판단·개장 체결·손절을 하지 않습니다</p>}

      <div style={statGrid}>
        <Stat label="총자산 (현재가)" value={fmtPrice(d.equity, m)} sub={`시작 ${fmtPrice(d.capital, m)}`} />
        <Stat label="수익률" value={pct(d.return_pct)} color={pctColor(d.return_pct)} />
        <Stat label={`${d.benchmark} (시작 후)`} value={pct(d.bench_return_pct)} color={pctColor(d.bench_return_pct)} />
        <Stat label="현금" value={fmtPrice(d.cash, m)} sub={`주식 ${d.positions.length}종목`} />
        <Stat label="실현 손익" value={fmtPrice(d.stats?.realized, m)} color={pctColor(d.stats?.realized)} sub={`매도 ${d.stats?.trades ?? 0}건 · 승률 ${d.stats?.win_rate ?? "-"}%`} />
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>보유 종목 <span style={{ fontWeight: 400, fontSize: 11, color: "var(--text-muted)" }}>(행에 마우스를 올리면 매수 이유)</span></p>
        <PositionsTable positions={d.positions} market={m} testid="account-positions" />
      </div>
      {d.pending?.length > 0 && (
        <div className="card" style={{ marginBottom: 12 }} data-testid="account-pending">
          <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>대기 주문 — {d.market_open ? "곧 현재가로 체결" : "다음 개장 1분 뒤 현재가로 체결"}</p>
          {d.pending.map((o: any, i: number) => (
            <p key={i} style={{ fontSize: 12, padding: "3px 0" }}>
              <strong style={{ color: o.side === "buy" ? "var(--accent)" : "var(--text-primary)" }}>{o.side === "buy" ? "매수" : "매도"}</strong> {o.name}
              {o.side === "buy" ? ` ${fmtPrice(o.budget, m)}어치` : ` ${o.qty}주`} <span style={{ color: "var(--text-muted)" }}>— {o.reason}</span>
            </p>
          ))}
        </div>
      )}
      <div className="card" style={{ marginBottom: 12 }}>
        <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>자산 변화 (거래일 종가 기준)</p>
        <EquityChart points={d.equity_curve} market={m} bench={d.benchmark} />
      </div>
      <div className="card" style={{ marginBottom: 12 }}>
        <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>거래 내역</p>
        <TradesTable trades={d.trades} market={m} testid="account-trades" />
      </div>
      <div className="card">
        <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>AI 판단 기록</p>
        {!d.log?.length ? <p style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", gap: 6, alignItems: "center" }}><RefreshCw size={12} className="spin" /> 첫 판단을 계산하는 중 (1~2분)</p> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }} data-testid="account-log">
            {d.log.map((x: any, i: number) => (
              <div key={i} style={{ borderTop: i ? "1px solid var(--border)" : undefined, paddingTop: i ? 6 : 0, fontSize: 12 }}>
                <p style={{ color: "var(--text-muted)" }}>{String(x.ts).slice(0, 16).replace("T", " ")}
                  {x.base_date && <> · {x.base_date} 종가 기준 판단{x.manual ? " (수동)" : ""} · 시장 {x.regime || "-"} · {x.universe}종목 검토</>}
                  {x.fills && " · 체결"}</p>
                {(x.fills || []).map((a: string, j: number) => <p key={`f${j}`}>• {a}</p>)}
                {(x.orders || []).map((a: string, j: number) => <p key={`o${j}`}>• 주문: {a}</p>)}
                {x.base_date && !(x.orders || []).length && <p style={{ color: "var(--text-secondary)" }}>• 주문 없음 (그대로 보유)</p>}
                {(x.events || []).length > 0 && <p style={{ color: "var(--yellow)" }}>⚠ 다음 거래일: {x.events.join(", ")}</p>}
                {(x.notes || []).map((a: string, j: number) => <p key={`n${j}`} style={{ color: "var(--text-muted)" }}>· {a}</p>)}
                {x.top?.length > 0 && <p style={{ color: "var(--text-muted)" }}>점수 상위: {x.top.map((t: any) => `${t.name} ${t.score}(확률 ${t.prob}%)`).join(", ")}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LiveTab({ cfg }: { cfg: any }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["paper-accounts"], queryFn: () => paperApi.accounts().then((r) => r.data), refetchInterval: 60_000 });
  const items: any[] = list.data?.items || [];
  const [picked, setPicked] = useState<number | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [market, setMarket] = useState<Market>("KR");
  const [capital, setCapital] = useState("");
  const [name, setName] = useState("");
  const [params, setParams] = useState<PaperParams>({});
  useEffect(() => { if ((picked == null || !items.some((a) => a.id === picked)) && items.length) setPicked(items[0].id); }, [items.map((a) => a.id).join(",")]);
  const mc = cfg?.markets?.[market];
  const create = useMutation({
    mutationFn: () => paperApi.createAccount(market, capital ? Number(capital) : mc?.capital, name, params).then((r) => r.data),
    onSuccess: (d) => { setPicked(d.id); setShowNew(false); setName(""); setCapital(""); qc.invalidateQueries({ queryKey: ["paper-accounts"] }); },
    meta: { inlineError: true },
  });
  const form = (
    <div className="card" style={{ marginBottom: 16 }} data-testid="account-form">
      <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}><Bot size={15} /> 새 모의투자 계좌</p>
      <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 10 }}>
        만들면 AI 가 최근 종가로 바로 판단합니다 (장중이면 그 자리에서 현재가로 체결). 그 뒤로는 매 거래일 장 마감 15분 뒤 판단 → 다음 개장 직후 체결, 장중 5분마다 손절·목표가 확인.
        서버가 켜져 있어야 자동으로 매매합니다.
      </p>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div><p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>시장</p><MarketPick market={market} setMarket={(m) => { setMarket(m); setCapital(""); }} /></div>
        <label style={{ fontSize: 11, color: "var(--text-muted)" }}>시작 자금 ({market === "KR" ? "원" : "달러"})
          <input className="input" type="number" data-testid="account-capital" placeholder={mc ? String(mc.capital) : ""} value={capital}
            onChange={(e) => setCapital(e.target.value)} style={{ display: "block", width: 160, marginTop: 4 }} />
        </label>
        <label style={{ fontSize: 11, color: "var(--text-muted)" }}>이름 (선택)
          <input className="input" maxLength={30} value={name} onChange={(e) => setName(e.target.value)} style={{ display: "block", width: 160, marginTop: 4 }} />
        </label>
        <button className="btn btn-primary" data-testid="account-create" disabled={create.isPending} onClick={() => create.mutate()}>
          <Play size={13} /> 모의투자 시작
        </button>
      </div>
      <ParamsForm cfg={cfg} value={params} onChange={setParams} />
      {create.error && <p style={{ color: "var(--red)", fontSize: 12, marginTop: 8 }} data-testid="account-create-error">{errMsg(create.error)}</p>}
    </div>
  );
  if (list.isLoading) return <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>;
  return (
    <div>
      {list.error && !list.data && <p style={{ color: "var(--red)", marginBottom: 12 }}>계좌 조회 실패: {errMsg(list.error)}</p>}
      {(items.length === 0 || showNew) && form}
      {items.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }} data-testid="account-list">
          {items.map((a) => (
            <div key={a.id} className="card" onClick={() => setPicked(a.id)}
              style={{ padding: "8px 12px", cursor: "pointer", borderColor: picked === a.id ? "var(--accent)" : undefined, fontSize: 12 }}>
              <p style={{ fontWeight: 600 }}>{a.name || `${a.market === "KR" ? "국내" : "미국"} 계좌 #${a.id}`} {!a.active && <span style={{ color: "var(--yellow)" }}>(멈춤)</span>}</p>
              <p><span style={{ fontVariantNumeric: "tabular-nums" }}>{fmtPrice(a.equity, a.market)}</span>{" "}
                <strong style={{ color: pctColor(a.return_pct) }}>{pct(a.return_pct)}</strong>
                <span style={{ color: "var(--text-muted)" }}> · 지수 {pct(a.bench_return_pct)}</span></p>
            </div>
          ))}
          {!showNew && items.length < (cfg?.max_accounts ?? 5) && (
            <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => setShowNew(true)} data-testid="account-new">+ 새 계좌</button>
          )}
        </div>
      )}
      {picked != null && items.some((a) => a.id === picked) && <AccountDetail id={picked} onDeleted={() => setPicked(null)} />}
    </div>
  );
}

export default function PaperTrading() {
  const [tab, setTab] = useState<"live" | "sim">(readTab);
  const cfgQ = useQuery({ queryKey: ["paper-config"], queryFn: () => paperApi.config().then((r) => r.data), staleTime: 3600_000 });
  const cfg = cfgQ.data;
  const pick = (t: "live" | "sim") => { setTab(t); try { localStorage.setItem(TAB_KEY, t); } catch { /* 저장 안 돼도 됨 */ } };
  const tabs = useMemo(() => [["live", "실시간 모의투자"], ["sim", "과거 시뮬레이션"]] as const, []);
  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>AI 모의투자</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          매집 탐지 · 퀀트 점수 · AI 추천 · 경제 캘린더(시장 상태·발표 일정)를 합친 AI 점수로 가상 자금을 굴립니다. 실제 주문은 나가지 않습니다.
        </p>
      </div>
      {cfgQ.error && <p style={{ color: "var(--red)", marginBottom: 8, fontSize: 12 }}>설정 조회 실패: {errMsg(cfgQ.error)}</p>}
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {tabs.map(([k, label]) => (
          <button key={k} className={`btn ${tab === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 13 }} onClick={() => pick(k)} data-testid={`tab-${k}`}>{label}</button>
        ))}
      </div>
      <HowItWorks cfg={cfg} />
      {tab === "live" ? <LiveTab cfg={cfg} /> : <SimTab cfg={cfg} />}
    </div>
  );
}
