import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useNarrow } from "../components/common/useNarrow";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Landmark, OctagonX, Play, RefreshCw, ShieldCheck, Wallet, ListChecks, History, Settings2, ScrollText, AlertTriangle, Bot, Radar } from "lucide-react";
import { kisApi, errMsg } from "../api/client";
import { th, td, when, codeInput } from "../components/common/AdminPanels";
import { toast } from "../components/common/Toast";
import { inputStyle } from "../components/common/AuthForm";

const won = (v?: number | null) => (v == null ? "-" : `${Math.round(v).toLocaleString()}원`);
const SIDE: Record<string, [string, string]> = { buy: ["매수", "badge-up"], sell: ["매도", "badge-down"] };
const STATUS_CLS: Record<string, string> = {
  proposed: "badge-accent", approved: "badge-accent", submitting: "badge-neutral", submitted: "badge-neutral", filled: "badge-up",
  partial: "badge-up", unfilled: "badge-neutral", unknown: "badge-down", rejected: "badge-neutral", expired: "badge-neutral",
  cancelled: "badge-neutral", blocked: "badge-down", failed: "badge-down",
};
const WINDOW: Record<string, string> = { open: "장중 — 실시간 감시 중", closing: "마감 직전 — 새 주문 안 보냄", closed: "장 닫힘 — 승인하면 다음 장중에 조건이 맞을 때 주문" };
const SOURCE: Record<string, [string, string]> = { stop: ["자동 손절", "var(--red)"], exit: ["장중 목표가", "var(--yellow)"] };
const PARAM_KEYS = ["max_positions", "buy_score", "sell_score", "stop_pct", "take_pct", "max_hold"] as const;
const PARAM_LABEL: Record<string, string> = {
  max_positions: "최대 보유 종목 수", buy_score: "매수 기준 AI 점수", sell_score: "매도 기준 AI 점수", stop_pct: "손절 %", take_pct: "익절(목표) %", max_hold: "최대 보유 거래일",
};
const ACTION: Record<string, string> = {
  propose: "제안", propose_exit: "목표가 매도 제안", auto_stop: "자동 손절", auto_cancel: "급변 자동 취소", wait: "조건 기다림", propose_fail: "제안 실패", approve: "승인", reject: "거절", submit: "주문 보냄", submitted: "주문 접수",
  submit_fail: "KIS 거부·연결 실패", submit_unknown: "응답 못 받음 — 결과 모름", blocked: "안전장치로 막음", filled: "체결", partial: "일부 체결", unfilled: "안 체결", cancelled: "취소됨", cancel: "주문 취소",
  cancel_fail: "취소 실패", fill_unknown: "체결 확인 안 됨", halt: "정지", resume: "다시 시작", baseline: "기준 맞추기", config: "설정 변경",
  expire: "기한 지남", interrupted: "서버 재시작 — 결과 모름", account_ok: "계좌 확인됨",
};

function Card({ icon: Icon, title, desc, children, testid, right }: { icon: any; title: string; desc?: string; children: React.ReactNode; testid?: string; right?: React.ReactNode }) {
  return (
    <section className="card" data-testid={testid} style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ fontSize: 14, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}><Icon size={16} style={{ color: "var(--accent)" }} />{title}</h2>
          {desc && <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{desc}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

const sideBadge = (s: string) => { const [l, c] = SIDE[s] || [s, "badge-neutral"]; return <span className={`badge ${c}`} style={{ fontSize: 10.5 }}>{l}</span>; };
const statusBadge = (o: any) => <span className={`badge ${STATUS_CLS[o.status] || "badge-neutral"}`} style={{ fontSize: 10.5 }}>{o.status_label || o.status}</span>;
const amount = (o: any) => (o.side === "sell" ? `${o.qty?.toLocaleString() ?? "-"}주` : o.qty ? `${o.qty.toLocaleString()}주` : `${won(o.budget)}어치`)
  + (o.limit_price ? ` · 지정가 ${won(o.limit_price)}` : o.submitted_at && o.side === "sell" ? " · 시장가" : "");
const srcTag = (o: any) => { const t = SOURCE[o.source]; return t ? <span style={{ fontSize: 10.5, color: t[1], fontWeight: 600 }}> {t[0]}</span> : null; };
const mCard: React.CSSProperties = { border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 5, minWidth: 0 };
const mRow: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, minWidth: 0 };
const mSub: React.CSSProperties = { fontSize: 11.5, color: "var(--text-muted)" };
const pct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;

function Rules({ s }: { s: any }) {
  const l = s.limits, w = s.watch || {};
  return (
    <div data-testid="kis-rules" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 8, fontSize: 12, lineHeight: 1.6 }}>
      <div><strong>승인한 매수</strong> — 개장 {w.buy_after_open ?? 5}분 뒤부터, 제안가 +{l.max_gap_pct}% 이하 · 지수 −{l.index_drop_pct}% 이내 · VI 아님일 때
        <strong> 지정가</strong>(현재가 +{l.limit_slip_pct}%)로 주문. 안 맞으면 기다림 (15:20 까지)</div>
      <div><strong>급변 → 매수 자동 취소</strong> — 제안가보다 −{(l.max_gap_pct * 2).toFixed(1).replace(/\.0$/, "")}% 넘게 하락 · 10분 안에 −{l.fast_drop_pct}% 넘게 급락.
        승인 대기·조건 대기·접수된 매수 모두 (승인 없이)</div>
      <div><strong>손절가 도달 → 자동 매도</strong> — 승인 없이 바로 시장가 매도 (긴급 정지 중엔 안 함, 하루 손실 한도 정지 중엔 함).
        <strong> 목표가</strong>는 매도 제안만 (승인해야 팔림)</div>
    </div>
  );
}

function Setup() {
  return (
    <Card icon={Landmark} title="KIS 모의투자 연결 필요" testid="kis-setup"
      desc="한국투자증권 모의투자 계좌(가상 자금)와 모의투자용 앱키가 있어야 주문할 수 있습니다">
      <ol style={{ fontSize: 12.5, lineHeight: 1.9, paddingLeft: 18 }}>
        <li>한국투자증권 앱·홈페이지에서 <strong>모의투자 신청</strong> → 모의투자 계좌번호 받기</li>
        <li>KIS Developers(apiportal.koreainvestment.com)에서 <strong>모의투자용 앱키</strong> 발급</li>
        <li><code>backend/.env</code> 에 <code>KIS_MOCK_APP_KEY</code> · <code>KIS_MOCK_APP_SECRET</code> · <code>KIS_MOCK_ACCOUNT_NO</code>(예: 50123456-01) 입력</li>
        <li>서버 다시 켜기 → 이 화면에 잔고가 보이면 연결 완료</li>
      </ol>
      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>키는 화면·채팅에 붙여 넣지 말고 .env 파일에만 넣으세요. 이 앱은 모의투자 서버로만 주문합니다 (실거래 주소는 코드에서 막혀 있음).</p>
    </Card>
  );
}

export default function KisTrade() {
  const qc = useQueryClient();
  const st = useQuery({ queryKey: ["kis-status"], queryFn: () => kisApi.status().then((r) => r.data), staleTime: 0, refetchInterval: 30_000 });
  const open = useQuery({ queryKey: ["kis-orders", "open"], queryFn: () => kisApi.orders("open").then((r) => r.data), staleTime: 0, refetchInterval: 30_000,
    enabled: !!st.data?.configured });
  const hist = useQuery({ queryKey: ["kis-orders", "all"], queryFn: () => kisApi.orders("all").then((r) => r.data), staleTime: 0, enabled: !!st.data?.configured });
  const log = useQuery({ queryKey: ["kis-log"], queryFn: () => kisApi.log().then((r) => r.data), staleTime: 0 });
  const refresh = () => { for (const k of ["kis-status", "kis-orders", "kis-log"]) qc.invalidateQueries({ queryKey: [k] }); };

  const [picked, setPicked] = useState<number[]>([]);
  const [code, setCode] = useState("");
  const narrow = useNarrow();
  // 휴대폰 알림을 누르면 /kis?order=번호 — 그 주문으로 스크롤 + 강조
  const focus = Number(useSearchParams()[0].get("order")) || null;
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    if (!focus || scrolled || !open.data || !hist.data) return;
    const el = document.querySelector(`[data-order="${focus}"]`);
    if (el) { el.scrollIntoView({ block: "center" }); setScrolled(true); }
  }, [focus, scrolled, open.data, hist.data]);
  const inOpen = (id: number) => !!open.data?.items?.some((x: any) => x.id === id);   // 진행 중 목록에 있으면 거기만 강조
  const hl = (id: number): React.CSSProperties => (id === focus
    ? { outline: "2px solid var(--accent)", outlineOffset: -2, background: "color-mix(in srgb, var(--accent) 8%, transparent)" } : {});
  const [resumeCode, setResumeCode] = useState("");

  const approve = useMutation({ mutationFn: () => kisApi.approve(picked, code).then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => {
      const r: any[] = d.results || [];
      const n = (s: string) => r.filter((x) => x.status === s).length;
      const bad = r.filter((x) => !["submitted", "approved"].includes(x.status));
      toast(`승인 ${r.length}건 — 주문 접수 ${n("submitted")} · 조건 대기 ${n("approved")}` + (bad.length ? ` · 안 보냄·취소 ${bad.length} (${bad[0].message})` : ""), bad.length ? undefined : "info");
      setPicked([]); setCode(""); refresh();
    } });
  const reject = useMutation({ mutationFn: (ids: number[]) => kisApi.reject(ids).then((r) => r.data), onSuccess: (d) => { toast(d.message, "info"); setPicked([]); refresh(); } });
  const cancel = useMutation({ mutationFn: (id: number) => kisApi.cancel(id).then((r) => r.data), onSuccess: (d) => { toast(d.message, "info"); refresh(); } });
  const propose = useMutation({ mutationFn: () => kisApi.propose().then((r) => r.data),
    onSuccess: (d) => { toast(`제안 ${d.proposed}건 (기준일 ${d.base_date})`, "info"); refresh(); } });
  const ntest = useMutation({ mutationFn: () => kisApi.notifyTest().then((r) => r.data), onSuccess: (d) => toast(d.message, "info") });
  const halt = useMutation({ mutationFn: () => kisApi.halt("").then((r) => r.data), onSuccess: (d) => { toast(d.message, "info"); refresh(); } });
  const resume = useMutation({ mutationFn: () => kisApi.resume(resumeCode).then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => { toast(d.message, "info"); setResumeCode(""); refresh(); } });
  const baseline = useMutation({ mutationFn: () => kisApi.baseline().then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => { toast(d.message, "info"); refresh(); } });

  const s = st.data;
  if (st.error) return <p style={{ color: "var(--red)" }}>{errMsg(st.error)}</p>;
  if (!s) return <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>;
  const orders: any[] = open.data?.items || [];
  const proposed = orders.filter((o) => o.status === "proposed");
  const bal = s.balance;
  const loss = s.day_loss ?? null;
  const toggle = (id: number) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  return (
    <div data-testid="kis-page" style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 1200 }}>
      <div>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <Landmark size={18} style={{ color: "var(--accent)" }} /> KIS 모의투자 주문
          <span className="badge badge-accent" style={{ fontSize: 11 }}>{s.server}</span>
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>AI 가 주문을 제안하고, <strong>내가 2단계 코드로 승인한 매수만</strong> 장중에 조건이 맞을 때 한국투자증권 모의투자 서버로 나갑니다.
          위험을 줄이는 일 — <strong>손절가 도달 매도 · 급변 때 매수 취소</strong> — 는 승인 없이 자동으로 하고 휴대폰으로 알립니다.</p>
      </div>

      {!s.configured && <Setup />}

      {s.configured && (
        <section className="card" data-testid="kis-status" style={{ display: "flex", flexDirection: "column", gap: 10,
          borderColor: s.halted ? "var(--red)" : undefined, background: s.halted ? "color-mix(in srgb, var(--red) 6%, transparent)" : undefined }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", justifyContent: "space-between" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <strong style={{ fontSize: 15, color: s.halted ? "var(--red)" : "var(--green)" }}>{s.halted ? (s.watch?.stops_ok ? "정지됨 — 새 주문 안 함 (손절 자동 매도는 계속)" : "정지됨 — 주문 안 함")
                : "운영 중 — 승인한 매수는 조건 맞으면 주문 · 손절 자동"}</strong>
              {s.halted && <span style={{ fontSize: 12 }}>{s.halted_reason} ({when(s.halted_at)})</span>}
              <span style={{ fontSize: 12, color: "var(--text-muted)" }} data-testid="kis-account">계좌 {s.account}{s.account_source ? ` (.env ${s.account_source})` : ""} · {WINDOW[s.window] || s.window}</span>
              {s.account_source === "KIS_ACCOUNT_NO" && (
                <span style={{ fontSize: 12, color: "var(--yellow)" }}>KIS_MOCK_* 가 비어 있어 시세용 계좌번호를 쓰는 중 — 모의투자 계좌가 아니면 잔고·주문이 안 됩니다</span>
              )}
            </div>
            {!s.halted ? (
              <button className="btn" data-testid="kis-halt" disabled={halt.isPending}
                style={{ background: "var(--red)", color: "#fff", fontWeight: 700, padding: "10px 18px", fontSize: 14 }}
                onClick={() => { if (window.confirm("긴급 정지할까요? 승인 대기·대기 주문은 취소되고, 접수된(안 체결) 주문도 취소를 요청합니다.")) halt.mutate(); }}>
                <OctagonX size={16} /> 긴급 정지
              </button>
            ) : (
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                {codeInput(resumeCode, setResumeCode, "다시 시작 2단계 코드")}
                <button className="btn btn-primary" disabled={!/^\d{6}$/.test(resumeCode) || resume.isPending} onClick={() => resume.mutate()}><Play size={14} /> 다시 시작</button>
              </div>
            )}
          </div>
          {resume.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(resume.error)}</p>}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8, fontSize: 12.5 }}>
            <div>오늘 주문 <strong>{s.orders_today}</strong> / {s.limits.max_orders_day}건</div>
            <div>오늘 손익 <strong style={{ color: loss == null ? undefined : loss > 0 ? "var(--red)" : "var(--green)" }}>{loss == null ? "-" : `${loss > 0 ? "−" : "+"}${Math.abs(Math.round(loss)).toLocaleString()}원`}</strong>
              <span style={{ color: "var(--text-muted)" }}> (손실 한도 {won(s.limits.max_loss_krw)})</span></div>
            <div>1회 매수 한도 <strong>{won(s.limits.max_order_krw)}</strong></div>
            <div>마지막 자동 제안 <strong>{s.last_proposal_day || "-"}</strong></div>
          </div>
          <WatchLine s={s} />
          {s.last_error && (
            <p data-testid="kis-last-error" style={{ color: "var(--red)", fontSize: 12, lineHeight: 1.6 }}>
              마지막 자동 제안 실패 — {s.last_error.replace("T", " ").replace(/\+09:00/, "")}
              <span style={{ display: "block", color: "var(--text-muted)" }}>30분마다 다시 시도합니다. 설정을 고쳤으면 아래 '지금 제안 만들기'로 바로 다시 해 보세요.</span>
            </p>
          )}
          <div data-testid="kis-notify" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
            <Bell size={13} style={{ color: s.notify?.configured ? "var(--green)" : "var(--text-muted)" }} />
            {s.notify?.configured ? (
              <>
                <span>휴대폰 알림(ntfy {s.notify.server}) 켜짐 — 제안·자동 손절·급변 자동 취소·조건 충족 주문·체결·막힘·정지를 보냅니다</span>
                {s.notify.link ? <span data-testid="kis-notify-link" style={{ color: "var(--text-muted)" }}>· 알림을 누르면 {s.notify.link.replace(/^https?:\/\//, "")} (그 주문 위치)</span>
                  : <span data-testid="kis-notify-link" style={{ color: "var(--yellow)" }}>· 알림을 눌러도 열 주소 없음 — backend/.env 에 NTFY_CLICK_URL=https://내주소 를 넣으세요</span>}
                {s.notify.last?.ok === false && <span style={{ color: "var(--red)" }}>마지막 알림 실패: {s.notify.last.error}</span>}
                <button className="btn btn-ghost" style={{ fontSize: 11.5, padding: "2px 8px" }} disabled={ntest.isPending} onClick={() => ntest.mutate()}>알림 시험 보내기</button>
              </>
            ) : (
              <span style={{ color: "var(--text-muted)" }}>휴대폰 알림 꺼짐 — backend/.env 에 <code>NTFY_TOPIC</code> 을 넣으면 ntfy 앱으로 제안·체결 알림을 받습니다</span>
            )}
          </div>
          {s.loop?.last_error && <p style={{ color: "var(--text-muted)", fontSize: 11.5 }}>자동 운영 오류: {s.loop.last_error}</p>}
        </section>
      )}

      {s.configured && (
        <Card icon={Wallet} title="KIS 모의투자 잔고" testid="kis-balance" desc="KIS 서버에서 바로 받은 값 (20초 캐시) · 손절·목표가는 앱이 정한 값"
          right={<button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={refresh}><RefreshCw size={13} /> 새로고침</button>}>
          {s.balance_error && <p data-testid="kis-balance-error" style={{ color: "var(--red)", fontSize: 12, lineHeight: 1.6 }}>잔고를 못 받음: {s.balance_error}</p>}
          {s.mismatches?.length > 0 && (
            <div data-testid="kis-mismatch" style={{ border: "1px solid var(--yellow)", borderRadius: 8, padding: 10, display: "flex", flexDirection: "column", gap: 6,
              background: "color-mix(in srgb, var(--yellow) 8%, transparent)" }}>
              <strong style={{ fontSize: 12.5, display: "flex", gap: 6, alignItems: "center" }}><AlertTriangle size={14} /> KIS 잔고와 앱 기록이 다릅니다 — 다를 때는 매수 주문을 보내지 않습니다</strong>
              <span style={{ fontSize: 12 }}>{s.mismatches.map((m: any) => `${m.name}: 앱 ${m.app}주 / KIS ${m.kis}주${m.pending ? " (체결 중)" : ""}`).join(" · ")}</span>
              {s.mismatches.every((m: any) => m.pending) ? (
                <span data-testid="kis-mismatch-pending" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>앱이 보낸 주문이 아직 체결되는 중입니다 — 체결이 끝나면 1분 안에 저절로 맞춰집니다 (기준 맞추기 필요 없음).</span>
              ) : (
                <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>KIS 앱·HTS 에서 직접 사고팔았다면 아래 버튼으로 지금 KIS 잔고를 기준으로 맞추세요 (주문은 안 나감 · 앱 기록만 바꿈). 모르는 거래라면 먼저 긴급 정지하고 KIS 에서 확인하세요.</span>
              )}
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <button className="btn btn-ghost" disabled={baseline.isPending}
                  onClick={() => window.confirm("지금 KIS 잔고를 앱 기록으로 삼을까요? (주문은 나가지 않습니다)") && baseline.mutate()}>기준 다시 맞추기</button>
              </div>
              {baseline.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(baseline.error)}</p>}
            </div>
          )}
          {bal && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8, fontSize: 12.5 }}>
                <div>총평가 <strong>{won(bal.total)}</strong></div>
                <div>주문 가능(D+2 예수금) <strong>{won(bal.d2_cash)}</strong></div>
                <div>주식 평가 <strong>{won(bal.stock_value)}</strong></div>
                <div>평가손익 <strong className={bal.pnl >= 0 ? "up" : "down"}>{bal.pnl >= 0 ? "+" : ""}{won(bal.pnl)}</strong></div>
              </div>
              {bal.holdings.length === 0 ? <p style={{ fontSize: 12, color: "var(--text-muted)" }}>보유 종목 없음</p> : narrow ? (
                <div data-testid="kis-holdings-cards" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {bal.holdings.map((h: any) => (
                    <div key={h.symbol} style={mCard}>
                      <div style={mRow}>
                        <strong style={{ fontSize: 13.5 }}>{h.name} <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 11.5 }}>{h.symbol}</span></strong>
                        <strong className={h.pnl_pct >= 0 ? "up" : "down"}>{h.pnl_pct >= 0 ? "+" : ""}{h.pnl_pct.toFixed(2)}%</strong>
                      </div>
                      <div style={mSub}>{h.qty.toLocaleString()}주 · 평균 {won(h.avg)} → 현재 {won(h.price)}</div>
                      <div style={mSub}>손절 {won(h.stop)} · 목표 {won(h.target)} · 보유 {h.hold_days ?? "-"}일</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table className="data-table">
                    <thead><tr><th>종목</th><th className="num">수량</th><th className="num">평균가</th><th className="num">현재가</th><th className="num">손익</th><th className="num">손절가</th><th className="num">목표가</th><th className="num">보유일</th></tr></thead>
                    <tbody>
                      {bal.holdings.map((h: any) => (
                        <tr key={h.symbol}>
                          <td>{h.name} <span style={{ color: "var(--text-muted)" }}>{h.symbol}</span></td>
                          <td className="num">{h.qty.toLocaleString()}</td><td className="num">{won(h.avg)}</td><td className="num">{won(h.price)}</td>
                          <td className={`num ${h.pnl_pct >= 0 ? "up" : "down"}`}>{h.pnl_pct >= 0 ? "+" : ""}{h.pnl_pct.toFixed(2)}%</td>
                          <td className="num">{won(h.stop)}</td><td className="num">{won(h.target)}</td><td className="num">{h.hold_days ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </Card>
      )}

      {s.configured && (
        <Card icon={ListChecks} title="AI 주문 제안 · 진행 중 주문" testid="kis-proposals"
          desc="장 마감 15분 뒤 자동으로 제안 (장중엔 목표가에 닿으면 매도 제안). 제안은 다음 거래일 장 마감까지만 유효 · 매도부터 주문. 조건 대기 중인 매수는 이유가 아래에 보입니다"
          right={<button className="btn btn-ghost" style={{ fontSize: 12 }} disabled={propose.isPending || s.halted} onClick={() => propose.mutate()}>
            <Bot size={13} className={propose.isPending ? "spin" : undefined} /> {propose.isPending ? "판단 중 (몇 분)..." : "지금 제안 만들기"}</button>}>
          {narrow ? (
            <details data-testid="kis-rules-fold" style={{ fontSize: 12 }}>
              <summary style={{ cursor: "pointer", color: "var(--text-secondary)" }}>자동 규칙 보기 (언제 사고 · 언제 자동 취소 · 자동 손절)</summary>
              <div style={{ marginTop: 8 }}><Rules s={s} /></div>
            </details>
          ) : <Rules s={s} />}
          {open.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(open.error)}</p>}
          {orders.length === 0 ? <p style={{ fontSize: 12, color: "var(--text-muted)" }}>승인 대기·진행 중인 주문이 없습니다</p> : narrow ? (
            <div data-testid="kis-order-cards" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {orders.map((o) => (
                <div key={o.id} data-order={o.id} data-focused={o.id === focus ? "1" : undefined} style={{ ...mCard, ...hl(o.id) }}>
                  <div style={mRow}>
                    <label style={{ display: "flex", gap: 8, alignItems: "center", minWidth: 0 }}>
                      {o.status === "proposed" && (
                        <input type="checkbox" aria-label={`${o.name} 선택`} checked={picked.includes(o.id)} onChange={() => toggle(o.id)} style={{ width: 18, height: 18 }} />
                      )}
                      {sideBadge(o.side)}
                      <strong style={{ fontSize: 13.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{o.name}</strong>
                    </label>
                    {statusBadge(o)}
                  </div>
                  <div style={mSub}>{amount(o)}{o.ref_price ? ` · 제안가 ${won(o.ref_price)}` : ""}{srcTag(o)}</div>
                  <div style={{ fontSize: 12, lineHeight: 1.5 }}>{o.reason}</div>
                  {o.message && <div style={{ ...mSub, lineHeight: 1.5 }}>{o.message}</div>}
                  <div style={mRow}>
                    <span style={mSub}>기한 {when(o.expires_at)}</span>
                    {o.status === "approved" && <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => reject.mutate([o.id])}>주문 전 취소</button>}
                    {o.status === "submitted" && <button className="btn btn-ghost" style={{ fontSize: 12, color: "var(--red)" }}
                      onClick={() => { if (window.confirm(`${o.name} 주문을 KIS 에서 취소할까요?`)) cancel.mutate(o.id); }}>주문 취소</button>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
                  <th style={th}></th><th style={th}>구분</th><th style={th}>종목</th><th style={th}>수량·금액</th><th style={th}>제안가</th><th style={th}>이유</th><th style={th}>상태</th><th style={th}>기한</th><th style={th}></th>
                </tr></thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.id} data-order={o.id} data-focused={o.id === focus ? "1" : undefined} style={{ borderTop: "1px solid var(--border)", ...hl(o.id) }}>
                      <td style={td}>{o.status === "proposed" && (
                        <input type="checkbox" aria-label={`${o.name} 선택`} checked={picked.includes(o.id)} onChange={() => toggle(o.id)} />
                      )}</td>
                      <td style={td}>{sideBadge(o.side)}{srcTag(o)}</td>
                      <td style={td}>{o.name} <span style={{ color: "var(--text-muted)" }}>{o.symbol}</span></td>
                      <td style={td}>{amount(o)}</td>
                      <td style={td}>{won(o.ref_price)}</td>
                      <td style={{ ...td, whiteSpace: "normal", minWidth: 220 }}>{o.reason}{o.message && <div style={{ color: "var(--text-muted)" }}>{o.message}</div>}</td>
                      <td style={td}>{statusBadge(o)}</td>
                      <td style={td}>{when(o.expires_at)}</td>
                      <td style={td}>
                        {o.status === "approved" && <button className="btn btn-ghost" style={{ fontSize: 11.5, padding: "2px 8px" }} onClick={() => reject.mutate([o.id])}>주문 전 취소</button>}
                        {o.status === "submitted" && <button className="btn btn-ghost" style={{ fontSize: 11.5, padding: "2px 8px", color: "var(--red)" }}
                          onClick={() => { if (window.confirm(`${o.name} 주문을 KIS 에서 취소할까요?`)) cancel.mutate(o.id); }}>주문 취소</button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {proposed.length > 0 && (
            <div data-testid="kis-approve-bar" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", borderTop: "1px solid var(--border)", paddingTop: 10,
              ...(narrow ? { position: "sticky", bottom: 0, zIndex: 5, background: "var(--bg-card)", paddingBottom: 10, boxShadow: "0 -6px 12px -8px rgba(0,0,0,.25)" } : {}) }}>
              <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => setPicked(picked.length === proposed.length ? [] : proposed.map((o) => o.id))}>
                {picked.length === proposed.length ? "선택 해제" : "모두 선택"}</button>
              <ShieldCheck size={14} style={{ color: "var(--accent)" }} />
              {codeInput(code, setCode, "승인 2단계 코드")}
              <button className="btn btn-primary" data-testid="kis-approve" disabled={!picked.length || !/^\d{6}$/.test(code) || approve.isPending || s.halted}
                onClick={() => { if (window.confirm(`선택한 ${picked.length}건을 승인할까요? ${s.window === "open" ? "조건이 맞으면 바로 모의투자 서버로 주문합니다 (매수는 지정가)." : "다음 장중에 조건이 맞을 때 주문합니다."} 급변이 오면 매수는 자동으로 취소됩니다.`)) approve.mutate(); }}>
                선택한 {picked.length}건 승인</button>
              <button className="btn btn-ghost" disabled={!picked.length || reject.isPending} onClick={() => reject.mutate(picked)}>거절</button>
              {!narrow && <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>주문 직전에 한도·손실·가격·VI·잔고 대조를 다시 확인하고, 걸리면 보내지 않거나 기다립니다</span>}
            </div>
          )}
          {approve.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(approve.error)}</p>}
          {s.log?.length > 0 && (
            <details style={{ fontSize: 12 }}>
              <summary style={{ cursor: "pointer", color: "var(--text-secondary)" }}>최근 AI 판단 기록 ({s.log.length})</summary>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {s.log.map((l: any, i: number) => (
                  <div key={i} style={{ borderLeft: "2px solid var(--border)", paddingLeft: 8 }}>
                    <div style={{ color: "var(--text-muted)" }}>{l.ts?.replace("T", " ")} · 기준일 {l.base_date} · 시장 {l.regime || "-"}{l.manual ? " · 손으로 실행" : ""} · 대상 {l.universe}종목</div>
                    {(l.orders?.length ? l.orders : ["제안 없음"]).map((t: string, j: number) => <div key={j}>{t}</div>)}
                    {l.notes?.map((t: string, j: number) => <div key={`n${j}`} style={{ color: "var(--text-muted)" }}>· {t}</div>)}
                  </div>
                ))}
              </div>
            </details>
          )}
        </Card>
      )}

      {s.configured && <ConfigCard s={s} onSaved={refresh} />}

      {s.configured && (
        <Card icon={History} title="주문 기록" testid="kis-history" desc="최근 100건 (제안·승인·거절·체결·막힘 전부)">
          {hist.data?.items?.length ? narrow ? (
            <div data-testid="kis-history-cards" style={{ display: "flex", flexDirection: "column" }}>
              {hist.data.items.map((o: any) => (
                <div key={o.id} data-order={inOpen(o.id) ? undefined : o.id} data-focused={o.id === focus && !inOpen(o.id) ? "1" : undefined}
                  style={{ borderTop: "1px solid var(--border)", padding: "8px 2px", display: "flex", flexDirection: "column", gap: 3, ...hl(o.id) }}>
                  <div style={mRow}>
                    <span style={{ display: "flex", gap: 6, alignItems: "center", minWidth: 0 }}>{sideBadge(o.side)}<strong style={{ fontSize: 13 }}>{o.name}</strong>{srcTag(o)}</span>
                    {statusBadge(o)}
                  </div>
                  <div style={mSub}>제안 {when(o.created_at)}{o.submitted_at ? ` · 주문 ${o.qty?.toLocaleString()}주${o.limit_price ? ` 지정가 ${won(o.limit_price)}` : " 시장가"}` : ""}
                    {o.filled_qty ? ` · 체결 ${o.filled_qty.toLocaleString()}주 ${won(o.filled_price)}` : ""}</div>
                  {o.message && <div style={{ ...mSub, lineHeight: 1.5 }}>{o.message}</div>}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
                  <th style={th}>제안</th><th style={th}>구분</th><th style={th}>종목</th><th style={th}>주문</th><th style={th}>체결</th><th style={th}>상태</th><th style={th}>메모</th>
                </tr></thead>
                <tbody>
                  {hist.data.items.map((o: any) => (
                    <tr key={o.id} data-order={inOpen(o.id) ? undefined : o.id} data-focused={o.id === focus && !inOpen(o.id) ? "1" : undefined}
                      style={{ borderTop: "1px solid var(--border)", ...hl(o.id) }}>
                      <td style={td}>{when(o.created_at)}</td><td style={td}>{sideBadge(o.side)}{srcTag(o)}</td>
                      <td style={td}>{o.name} <span style={{ color: "var(--text-muted)" }}>{o.symbol}</span></td>
                      <td style={td}>{o.submitted_at ? `${when(o.submitted_at)} · ${o.qty?.toLocaleString()}주${o.limit_price ? ` · 지정가 ${won(o.limit_price)}` : " · 시장가"}` : "-"}</td>
                      <td style={td}>{o.filled_qty ? `${o.filled_qty.toLocaleString()}주 · ${won(o.filled_price)}` : "-"}</td>
                      <td style={td}>{statusBadge(o)}</td>
                      <td style={{ ...td, whiteSpace: "normal", minWidth: 200, color: "var(--text-muted)" }}>{o.message || ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p style={{ fontSize: 12, color: "var(--text-muted)" }}>주문 기록 없음</p>}
        </Card>
      )}

      <Card icon={ScrollText} title="감사 로그" testid="kis-audit" desc="누가 언제 무엇을 했는지 — 제안·승인·주문·체결·정지·설정 변경을 모두 남깁니다 (지우지 않음)">
        {log.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(log.error)}</p>}
        {log.data?.items?.length ? narrow ? (
          <div style={{ display: "flex", flexDirection: "column", maxHeight: 420, overflowY: "auto" }}>
            {log.data.items.map((l: any) => (
              <div key={l.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 2px", fontSize: 12, color: l.ok ? undefined : "var(--red)" }}>
                <div style={{ ...mSub, color: l.ok ? "var(--text-muted)" : "var(--red)" }}>{when(l.at)} · {l.by} · <strong>{ACTION[l.action] || l.action}</strong></div>
                <div style={{ lineHeight: 1.5 }}>{l.detail}{l.order_id ? <span style={{ color: "var(--text-muted)" }}> (#{l.order_id})</span> : null}</div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ overflowX: "auto", maxHeight: 360 }}>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}><th style={th}>시각</th><th style={th}>누가</th><th style={th}>일</th><th style={th}>내용</th></tr></thead>
              <tbody>
                {log.data.items.map((l: any) => (
                  <tr key={l.id} style={{ borderTop: "1px solid var(--border)", color: l.ok ? undefined : "var(--red)" }}>
                    <td style={td}>{when(l.at)}</td><td style={td}>{l.by}</td><td style={td}>{ACTION[l.action] || l.action}</td>
                    <td style={{ ...td, whiteSpace: "normal", minWidth: 220 }}>{l.detail}{l.order_id ? <span style={{ color: "var(--text-muted)" }}> (#{l.order_id})</span> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p style={{ fontSize: 12, color: "var(--text-muted)" }}>기록 없음</p>}
      </Card>
    </div>
  );
}

function WatchLine({ s }: { s: any }) {
  const w = s.watch;
  if (!w) return null;
  const t = w.last ? String(w.last).slice(11, 19) : null;
  return (
    <div data-testid="kis-watch" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
      <Radar size={13} style={{ color: s.window === "open" ? "var(--green)" : "var(--text-muted)" }} />
      {s.window === "open" ? (
        <>
          <span>실시간 감시 {w.every}초마다{t ? ` · 마지막 ${t}` : ""} · {w.symbols}종목 (실시간 체결가 {w.realtime} · REST {w.rest}{w.missing ? ` · 가격 못 받음 ${w.missing}` : ""})</span>
          {w.index_change != null && <span>지수 {pct(w.index_change)}</span>}
          {w.index_error && <span style={{ color: "var(--yellow)" }}>지수 못 받음 — 매수 기다림</span>}
          {w.ws && !w.ws.connected && (
            <span data-testid="kis-ws-off" style={{ color: "var(--text-muted)" }}>
              실시간 체결가 연결 안 됨{w.ws.last_error ? ` (${w.ws.last_error})` : ""} — REST 시세(15초)로 감시 중
            </span>
          )}
          {w.error && <span style={{ color: "var(--red)" }}>{w.error}</span>}
        </>
      ) : <span style={{ color: "var(--text-muted)" }}>실시간 감시는 장중(09:01~15:20)에만 — {w.every}초마다 손절·급변·매수 조건 확인</span>}
    </div>
  );
}

// 설정 묶음 — 이름·범위를 두 줄로 나눠 칸 높이를 맞춤 (라벨 길이가 달라 입력칸이 들쭉날쭉하던 것)
const LIMIT_GROUPS: [string, string, string[]][] = [
  ["주문 한도", "넘으면 주문을 안 보내거나 멈춤", ["max_order_krw", "max_orders_day", "max_loss_krw"]],
  ["장중 감시 규칙", "승인한 매수를 언제 보내고, 언제 자동 취소할지", ["max_gap_pct", "fast_drop_pct", "index_drop_pct", "limit_slip_pct"]],
];

function Field({ label, range, value, onChange }: { label: string; range?: string; value: number; onChange: (n: number) => void }) {
  const narrow = useNarrow();
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
      {/* 휴대폰(2열)에선 이름이 두 줄이 될 수 있어 두 줄 높이를 늘 잡아 둠 — 같은 줄 입력칸 위치가 같게 */}
      <span style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.3,
        ...(narrow ? { minHeight: 31 } : { whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }) }} title={label}>{label}</span>
      <span style={{ fontSize: 10.5, color: "var(--text-muted)", minHeight: 14 }}>{range || ""}</span>
      <input type="number" value={Number.isFinite(value) ? value : ""} aria-label={label} onChange={(e) => onChange(Number(e.target.value))}
        style={{ ...inputStyle, width: "100%" }} />
    </label>
  );
}

function Group({ title, desc, children, testid }: { title: string; desc: string; children: React.ReactNode; testid?: string }) {
  return (
    <div data-testid={testid} style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
      <div style={{ fontSize: 12.5 }}><strong>{title}</strong> <span style={{ color: "var(--text-muted)", fontSize: 11.5 }}>— {desc}</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(170px, calc(50% - 5px)), 1fr))", gap: 10 }}>{children}</div>
    </div>
  );
}

function ConfigCard({ s, onSaved }: { s: any; onSaved: () => void }) {
  const [lim, setLim] = useState<Record<string, number>>(s.limits);
  const [par, setPar] = useState<Record<string, any>>(s.params);
  const [code, setCode] = useState("");
  useEffect(() => { setLim(s.limits); setPar(s.params); }, [JSON.stringify(s.limits), JSON.stringify(s.params)]);   // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({ mutationFn: () => kisApi.config(lim, Object.fromEntries(PARAM_KEYS.map((k) => [k, par[k]])), code).then((r) => r.data),
    meta: { inlineError: true }, onSuccess: (d) => { toast(d.message, "info"); setCode(""); onSaved(); } });
  const meta = s.limit_meta as Record<string, any>;
  const grouped = new Set(LIMIT_GROUPS.flatMap((g) => g[2]));
  const groups = LIMIT_GROUPS.map(([t, d, keys], i) => [t, d, [...keys, ...(i === LIMIT_GROUPS.length - 1 ? Object.keys(meta).filter((k) => !grouped.has(k)) : [])]] as const);
  const limitField = (k: string) => meta[k] && (
    <Field key={k} label={meta[k].label} range={`${meta[k].min.toLocaleString()} ~ ${meta[k].max.toLocaleString()}`} value={lim[k]} onChange={(n) => setLim({ ...lim, [k]: n })} />
  );
  const narrow = useNarrow();
  const [show, setShow] = useState(false);
  if (narrow && !show) {   // 휴대폰: 자주 안 바꾸니 접어 둠 (화면이 너무 길어짐)
    return (
      <Card icon={Settings2} title="안전장치 · 매매 규칙" testid="kis-config" desc="바꾸려면 2단계 코드가 필요합니다"
        right={<button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => setShow(true)}>설정 보기·바꾸기</button>}>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>1회 {won(s.limits.max_order_krw)} · 하루 {s.limits.max_orders_day}건 · 손실 한도 {won(s.limits.max_loss_krw)} ·
          손절 {s.params.stop_pct}% · 목표 {s.params.take_pct}%</span>
      </Card>
    );
  }
  return (
    <Card icon={Settings2} title="안전장치 · 매매 규칙" testid="kis-config" desc="바꾸려면 2단계 코드가 필요합니다. 매매 규칙은 AI 모의투자와 같은 항목입니다">
      {groups.map(([t, d, keys]) => <Group key={t} title={t} desc={d} testid="kis-config-group">{keys.map(limitField)}</Group>)}
      <Group title="AI 매매 규칙" desc="무엇을 살지·언제 팔지 (AI 모의투자와 같은 항목)" testid="kis-config-group">
        {PARAM_KEYS.map((k) => <Field key={k} label={PARAM_LABEL[k]} range={s.param_meta?.[k] ? `${s.param_meta[k].min.toLocaleString()} ~ ${s.param_meta[k].max.toLocaleString()}` : undefined} value={par[k]} onChange={(n) => setPar({ ...par, [k]: n })} />)}
      </Group>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        {codeInput(code, setCode, "설정 2단계 코드")}
        <button className="btn btn-primary" disabled={!/^\d{6}$/.test(code) || save.isPending} onClick={() => save.mutate()}>저장</button>
      </div>
      {save.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(save.error)}</p>}
    </Card>
  );
}
