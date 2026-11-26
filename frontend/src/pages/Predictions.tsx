import { useNarrow } from "../components/common/useNarrow";
import { Fragment, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, ClipboardCheck, History, RefreshCw } from "lucide-react";
import { predictionApi, errMsg } from "../api/client";
import { fmtPrice, fmtSigned } from "../components/common/format";

type Filter = "all" | "miss" | "hit" | "pending";
type Kind = "all" | "live" | "backtest";
const PAGE = 50;   // 한 번에 50건 (200건이면 화면이 1만 px 넘게 길어짐) — 아래 "더 보기"

const KIND_LABEL: Record<Kind, string> = { all: "실제 + 백테스트", live: "실제 예측만", backtest: "백테스트만" };

function BacktestPanel({ bt, onDone }: { bt: any; onDone: () => void }) {
  const qc = useQueryClient();
  // 실행 중이면 2초마다 진행 상황 조회
  const { data: live } = useQuery({
    queryKey: ["backtest-status"],
    queryFn: () => predictionApi.backtestStatus().then((r) => r.data),
    initialData: bt,
    refetchInterval: (q) => (q.state.data?.running ? 2000 : false),
  });
  const s = live || bt || {};
  const btDays: number = s.days || 365;
  const [wasRunning, setWasRunning] = useState(false);
  useEffect(() => {
    if (s.running) setWasRunning(true);
    else if (wasRunning) {
      setWasRunning(false);
      onDone();
    }
  }, [s.running]);
  const run = useMutation({
    mutationFn: (force: boolean) => predictionApi.runBacktest(force).then((r) => r.data),
    onSuccess: (d) => qc.setQueryData(["backtest-status"], d),
  });
  const pct = s.total ? Math.round((s.done / s.total) * 100) : 0;
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 260 }}>
          <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 4, display: "flex", alignItems: "center", gap: 6 }}>
            <History size={15} /> 과거 {btDays === 365 ? "1년" : `${btDays}일`} 백테스트
          </p>
          <p style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6 }}>
            최근 {btDays === 365 ? "1년(365일)" : `${btDays}일`}의 거래일마다 <strong>그 전날 종가까지의 일봉만</strong> 보고 다음 날을 예측한 뒤 실제 등락과 비교합니다
            (예: 11/18까지 데이터로 11/19 예측 → 11/19 종가로 채점). 결과는 DB(prediction_backtest)에 저장되고 하루 한 번 새 날짜만 추가됩니다.
            대상: AI 추천 후보 + 관심종목 + 투자종목 · 규칙 점수와 학습 모델(과거 2년 일봉으로 학습, 10거래일마다 그 이전 데이터로만 다시 학습)을 같이 계산해 아래 "예측 방식별 적중률"에서 비교합니다.
            뉴스·거시·애널리스트·공시는 과거 시점 기록이 없어 <strong>가격·거래량·지수 데이터만</strong> 사용.
          </p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn btn-primary" style={{ fontSize: 12, padding: "6px 10px" }} disabled={s.running || run.isPending} onClick={() => run.mutate(false)}>
            <RefreshCw size={12} className={s.running ? "spin" : undefined} /> {s.running ? "계산 중" : "새 날짜 계산"}
          </button>
          <button className="btn btn-ghost" style={{ fontSize: 12, padding: "6px 10px" }} disabled={s.running || run.isPending}
            onClick={() => { if (confirm("기존 백테스트 기록을 지우고 처음부터 다시 계산할까요?")) run.mutate(true); }}>
            전체 다시 계산
          </button>
        </div>
      </div>
      {s.running && (
        <div style={{ marginTop: 10 }}>
          {s.phase && <p style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{s.phase}</p>}
          <div style={{ height: 6, background: "var(--bg-secondary)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent)", transition: "width 0.5s" }} />
          </div>
          <p style={{ fontSize: 12, color: s.retry_wait ? "var(--yellow)" : "var(--text-muted)", marginTop: 4 }}>
            {s.done}/{s.total} 종목 ({pct}%) · {s.current} · 새 기록 {s.added}건
          </p>
        </div>
      )}
      {!s.running && s.finished_at && (
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
          마지막 실행 {s.finished_at.replace("T", " ")} · {s.total}종목 · 새 기록 {s.added}건
        </p>
      )}
      {!s.running && !s.finished_at && (
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>서버 시작 20초 후 자동으로 계산합니다.</p>
      )}
      {run.error && <p style={{ fontSize: 12, color: "var(--red)", marginTop: 6 }}>실행 실패: {errMsg(run.error)}</p>}
      {s.errors?.length > 0 && (
        <details style={{ marginTop: 6, fontSize: 12, color: "var(--red)" }}>
          <summary style={{ cursor: "pointer" }}>실패 {s.errors.length}건 (해당 종목은 빠짐)</summary>
          <ul style={{ marginTop: 4, display: "flex", flexDirection: "column", gap: 2 }}>
            {s.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}

const OUTCOME: Record<string, { label: string; cls: string }> = {
  hit: { label: "적중", cls: "badge-up" },
  miss: { label: "빗나감", cls: "badge-down" },
  neutral: { label: "중립(채점 제외)", cls: "badge-neutral" },
  no_data: { label: "시세 없음", cls: "badge-neutral" },
};

function Acc({ title, a, sub }: { title: string; a: any; sub?: string }) {
  const v = a?.accuracy;
  const color = v == null ? "var(--text-muted)" : v >= 55 ? "var(--green)" : v >= 45 ? "var(--yellow)" : "var(--red)";
  return (
    <div className="card" style={{ padding: "14px 16px" }}>
      <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>{title}</p>
      <p style={{ fontSize: 22, fontWeight: 700, color }}>{v == null ? "-" : `${v}%`}</p>
      <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
        {a ? `맞음 ${a.hit}건 · 틀림 ${a.miss}건${a.hit + a.miss ? ` (틀림 ${(100 - (a.accuracy ?? 0)).toFixed(1)}%)` : ""}` : ""}{sub ? ` · ${sub}` : ""}
      </p>
    </div>
  );
}

export default function Predictions() {
  const [days, setDays] = useState(90);
  const [market, setMarket] = useState("ALL");
  const [kind, setKind] = useState<Kind>("all");
  const [filter, setFilter] = useState<Filter>("all");
  const [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState<string | null>(null);
  const qc = useQueryClient();

  useEffect(() => setLimit(PAGE), [days, market, kind, filter]);

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["prediction-review", days, market, kind, filter, limit],
    queryFn: () => predictionApi.review(days, market, kind, filter, limit).then((r) => r.data),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
    // 채점이 오래 걸려 서버가 기존 기록을 먼저 준 경우(newly_evaluated = null) 5초 뒤 다시 받아 채점 결과 반영
    refetchInterval: (q) => (q.state.data && q.state.data.newly_evaluated === null ? 5000 : false),
  });

  const shown: any[] = data?.items || [];
  const counts = data?.counts || {};

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>예측 검증</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          AI 추천·투자종목·관심종목에서 낸 다음 거래일 예측(실제)과 과거 1년 백테스트를 실제 등락과 비교해 채점합니다 ·
          모든 예측을 상승(확률 50% 초과)·하락(50% 미만) 둘 중 하나로 채점 (정확히 50% 만 제외)
        </p>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {[7, 30, 90, 180, 365].map((d) => (
          <button key={d} className={`btn ${days === d ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "6px 10px" }} onClick={() => setDays(d)}>
            최근 {d}일
          </button>
        ))}
        <span style={{ width: 12 }} />
        {[["ALL", "전체"], ["KR", "국내"], ["US", "미국"]].map(([k, l]) => (
          <button key={k} className={`btn ${market === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "6px 10px" }} onClick={() => setMarket(k)}>
            {l}
          </button>
        ))}
        <span style={{ width: 12 }} />
        {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
          <button key={k} className={`btn ${kind === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "6px 10px" }} onClick={() => setKind(k)}>
            {KIND_LABEL[k]}
          </button>
        ))}
        {(isFetching && !isLoading || data?.newly_evaluated === null) && <span style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>{data?.newly_evaluated === null ? "장 끝난 예측 채점 중… (끝나면 자동 반영)" : "불러오는 중..."}</span>}
      </div>

      {data && <BacktestPanel bt={data.backtest} onDone={() => qc.invalidateQueries({ queryKey: ["prediction-review"] })} />}

      {isLoading && <p style={{ color: "var(--text-muted)" }}>채점 중...</p>}
      {error && <p style={{ color: "var(--red)" }}>예측 검증 조회 실패: {errMsg(error)}</p>}

      {data && (
        <>
          {/* 적중률 요약 */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
            <Acc title="전체 적중률" a={data.overall} />
            <Acc title="상승 예측 적중률" a={data.up_calls} sub="오른다고 한 것 중 실제 상승 (나머지는 하락)" />
            <Acc title="하락 예측 적중률" a={data.down_calls} sub="내린다고 한 것 중 실제 하락 (나머지는 상승)" />
            {kind === "all" && <Acc title="실제 예측 적중률" a={data.by_kind?.live} />}
            {kind === "all" && <Acc title="백테스트 적중률" a={data.by_kind?.backtest} sub="가격·지수 데이터만" />}
            <div className="card" style={{ padding: "14px 16px" }}>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>채점 대기 / 정확히 50%</p>
              <p style={{ fontSize: 22, fontWeight: 700 }}>{data.pending_count} / {data.neutral_count}</p>
              <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>대상일 장이 끝나면 자동 채점 (30분 주기)</p>
            </div>
          </div>

          {/* 예측 방식별 적중률 */}
          <MethodCard methods={data.method_accuracy || []} model={data.model} flows={data.flows} />

          {/* 확률 구간별 실제 상승 비율 */}
          <div className="card" style={{ marginBottom: 20 }}>
            <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>확률 구간별 실제 상승 비율</p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
              예측 확률이 정확하다면 두 막대 길이가 비슷해야 합니다 (예: 60%라고 한 종목은 10번 중 6번 상승)
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {data.calibration.map((b: any) => (
                <div key={b.label} style={{ display: "grid", gridTemplateColumns: "70px 1fr 120px", gap: 12, alignItems: "center", fontSize: 12 }}>
                  <span style={{ color: "var(--text-secondary)" }}>{b.label}</span>
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    <div style={{ height: 6, background: "var(--bg-secondary)", borderRadius: 3 }}>
                      <div style={{ width: `${b.avg_prob ?? 0}%`, height: "100%", background: "var(--accent)", borderRadius: 3 }} />
                    </div>
                    <div style={{ height: 6, background: "var(--bg-secondary)", borderRadius: 3 }}>
                      <div style={{ width: `${b.actual_up_rate ?? 0}%`, height: "100%", background: "var(--green)", borderRadius: 3 }} />
                    </div>
                  </div>
                  <span style={{ color: "var(--text-muted)" }}>
                    {b.count ? `예측 ${b.avg_prob}% · 실제 ${b.actual_up_rate}% (${b.count}건)` : "기록 없음"}
                  </span>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--text-muted)", marginTop: 10 }}>
              <span><span style={{ display: "inline-block", width: 10, height: 6, background: "var(--accent)", borderRadius: 2, marginRight: 4 }} />평균 예측 확률</span>
              <span><span style={{ display: "inline-block", width: 10, height: 6, background: "var(--green)", borderRadius: 2, marginRight: 4 }} />실제 상승 비율</span>
            </div>
          </div>

          {/* 지표별 적중률 */}
          {data.factor_accuracy?.length > 0 && (
            <div className="card" style={{ marginBottom: 20 }}>
              <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>지표별 적중률</p>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                각 지표가 상승/하락 신호를 냈을 때 다음 거래일에 실제로 그렇게 움직인 비율 — 50%보다 낮은 지표는 믿기 어렵다는 뜻
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "100px 1fr 1fr", gap: "8px 16px", fontSize: 12, alignItems: "center" }}>
                <span style={{ color: "var(--text-muted)" }}>지표</span>
                <span style={{ color: "var(--text-muted)" }}>상승 신호 → 실제 상승</span>
                <span style={{ color: "var(--text-muted)" }}>하락 신호 → 실제 하락</span>
                {data.factor_accuracy.map((f: any) => (
                  <FactorRow key={f.name} f={f} />
                ))}
              </div>
            </div>
          )}

          {/* 지표 비중 자동 조정 (factor_weights) */}
          <WeightCard fw={data.factor_weights} />

          {/* 종목별 적중률 */}
          {data.by_symbol?.length > 0 && (
            <div className="card" style={{ marginBottom: 20 }}>
              <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>종목별 적중률</p>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>채점 5건 이상 종목 · 예측이 잘 맞는 종목과 안 맞는 종목</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "6px 24px", fontSize: 12 }}>
                {data.by_symbol.map((s: any) => (
                  <div key={`${s.market}-${s.symbol}`} style={{ display: "grid", gridTemplateColumns: "1fr 150px", gap: 8, alignItems: "center" }}>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {s.name || s.symbol} <span style={{ color: "var(--text-muted)" }}>{s.symbol}</span>
                    </span>
                    <RateBar rate={s.accuracy} n={s.hit + s.miss} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 기록 목록 */}
          <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
            {([["all", "전체"], ["miss", "틀린 것"], ["hit", "맞은 것"], ["pending", "채점 대기"]] as [Filter, string][]).map(([k, l]) => (
              <button key={k} className={`btn ${filter === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "6px 10px" }} onClick={() => setFilter(k)}>
                {l} ({counts[k] ?? 0})
              </button>
            ))}
          </div>

          {shown.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: 40 }}>
              <ClipboardCheck size={32} style={{ color: "var(--border)", margin: "0 auto 10px" }} />
              <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                기록이 없습니다. AI 추천·투자종목·관심종목 화면을 열면 예측이 기록되고, 다음 거래일 장 마감 후 채점됩니다.
                과거 기록은 위의 백테스트가 끝나면 채워집니다.
              </p>
            </div>
          ) : (
            <div className="card" style={{ padding: 0, overflow: "hidden" }}>
              {shown.map((r, i) => {
                const isOpen = open === r.id;
                const dirTxt = r.direction === "up" ? "상승 예측" : r.direction === "down" ? "하락 예측" : "중립";
                const o = r.evaluated ? OUTCOME[r.outcome] : { label: "채점 대기", cls: "badge-neutral" };
                return (
                  <div key={r.id} style={{ borderBottom: i < shown.length - 1 ? "1px solid var(--border)" : "none" }}>
                    <div
                      onClick={() => setOpen(isOpen ? null : r.id)}
                      style={{ display: "grid", gridTemplateColumns: "90px 1.6fr 1fr 1fr 110px 20px", gap: 10, alignItems: "center", padding: "11px 16px", cursor: "pointer", fontSize: 13 }}
                    >
                      <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{r.target_date.slice(5)}</span>
                      <span>
                        <strong>{r.name || r.symbol}</strong>
                        {r.kind === "backtest" && <span className="badge badge-neutral" style={{ marginLeft: 6, fontSize: 10 }}>백테스트</span>}
                        <span style={{ color: "var(--text-muted)", fontSize: 11, marginLeft: 6 }}>{r.symbol} · {r.market === "KR" ? "국내" : "미국"}</span>
                      </span>
                      <span>
                        상승 {r.probability}%
                        <span style={{ color: "var(--text-muted)", fontSize: 11, marginLeft: 6 }}>{dirTxt}</span>
                      </span>
                      <span style={{ fontWeight: 600, color: r.actual_change == null ? "var(--text-muted)" : r.actual_change >= 0 ? "var(--green)" : "var(--red)" }}>
                        {r.actual_change == null ? "-" : `실제 ${fmtSigned(r.actual_change)}%`}
                      </span>
                      <span className={`badge ${o.cls}`} style={{ justifySelf: "start" }}>{o.label}</span>
                      {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                    {isOpen && (
                      <div style={{ padding: "0 16px 14px 116px", fontSize: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                        <div style={{ color: "var(--text-secondary)" }}>
                          <span style={{ color: "var(--text-muted)" }}>예측 당시 ({r.base_date}, {fmtPrice(r.base_price, r.market)}): </span>
                          {r.summary}
                          <span style={{ color: "var(--text-muted)" }}> · 출처: {r.sources}{r.kind === "backtest" ? " (가격·지수 데이터만, 대상일 전날 종가까지의 데이터)" : ""}</span>
                        </div>
                        {r.evaluated && r.review?.length > 0 && (
                          <div>
                            <p style={{ color: "var(--text-muted)", marginBottom: 4 }}>{r.outcome === "miss" ? "틀린 이유 (추정)" : "결과 분석"}</p>
                            <ul style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                              {r.review.map((t: string, k: number) => (
                                <li key={k} style={{ display: "flex", gap: 6, color: "var(--text-secondary)" }}>
                                  <span style={{ color: r.outcome === "miss" ? "var(--red)" : "var(--accent)" }}>•</span>{t}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {r.evaluated && r.actual_close != null && (
                          <div style={{ color: "var(--text-muted)", display: "flex", gap: 14, flexWrap: "wrap" }}>
                            <span>종가 {fmtPrice(r.actual_close, r.market)}</span>
                            {r.gap_pct != null && <span>시가 갭 {fmtSigned(r.gap_pct)}%</span>}
                            {r.volume_ratio != null && <span>거래량 {r.volume_ratio}배</span>}
                            {r.index_change != null && <span>{r.index_name} {fmtSigned(r.index_change)}%</span>}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
              {data.items_total > shown.length && (
                <div style={{ padding: 12, textAlign: "center", borderTop: "1px solid var(--border)" }}>
                  <button className="btn btn-ghost" style={{ fontSize: 12 }} disabled={isFetching} onClick={() => setLimit(limit + PAGE)}>
                    더 보기 ({shown.length} / {data.items_total})
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

const VARIANT_LABEL: Record<string, string> = {
  US: "미국",
  KRF: "국내 · 장 시작 전 + 외국인·기관 수급",
  KR: "국내 · 장 시작 전 (간밤 미국장 반영)",
  KRF_base: "국내 · 장중/장 마감 후 + 외국인·기관 수급",
  KR_base: "국내 · 장중/장 마감 후",
};

function MethodCard({ methods, model, flows }: { methods: any[]; model: any; flows?: any }) {
  const pct = (v: any) => (v == null ? "-" : `${v}%`);
  const color = (v: any) => (v == null ? "var(--text-muted)" : v >= 55 ? "var(--green)" : v >= 50 ? "var(--yellow)" : "var(--red)");
  const narrow = useNarrow();
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>예측 방식별 적중률</p>
      <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12, lineHeight: 1.6 }}>
        같은 기록을 방식별로 채점한 결과 · 전체 방향 적중률 = 50% 기준으로 전부 상승/하락 채점 (위 카드와 같은 기준) ·
        확신 예측 = 55% 이상·45% 이하로 강하게 말한 것만 · 확신 예측 비율 = 전체 중 그 비율
      </p>
      {narrow ? (   // 휴대폰: 방식 하나 = 한 칸 (6칸 표는 제목이 한 글자씩 세로로 쪼개졌음)
        <div data-testid="method-cards" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {methods.map((m) => (
            <div key={m.key} style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "9px 12px", fontSize: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{m.label}<span style={{ color: "var(--text-muted)", fontWeight: 400 }}> ({m.n}건)</span></div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px" }}>
                <span style={{ color: "var(--text-muted)" }}>확신 예측 적중 <strong style={{ color: color(m.accuracy) }}>{pct(m.accuracy)}</strong> ({m.hit}/{m.calls})</span>
                <span style={{ color: "var(--text-muted)" }}>전체 방향 <strong style={{ color: color(m.dir_accuracy) }}>{pct(m.dir_accuracy)}</strong></span>
                <span style={{ color: "var(--text-muted)" }}>확신 상승 <strong style={{ color: color(m.up_accuracy) }}>{pct(m.up_accuracy)}</strong></span>
                <span style={{ color: "var(--text-muted)" }}>확신 하락 <strong style={{ color: color(m.down_accuracy) }}>{pct(m.down_accuracy)}</strong></span>
                <span style={{ color: "var(--text-muted)" }}>확신 예측 비율 {pct(m.coverage)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
      <div style={{ display: "grid", gridTemplateColumns: "minmax(200px, 2fr) repeat(5, 1fr)", gap: "8px 12px", fontSize: 12, alignItems: "center" }}>
        {["방식", "확신 예측 적중률", "확신 상승", "확신 하락", "전체 방향 적중률", "확신 예측 비율"].map((h) => (
          <span key={h} style={{ color: "var(--text-muted)" }}>{h}</span>
        ))}
        {methods.map((m) => (
          <Fragment key={m.key}>
            <span style={{ fontWeight: 600 }}>{m.label}<span style={{ color: "var(--text-muted)", fontWeight: 400 }}> ({m.n}건)</span></span>
            <span style={{ fontWeight: 700, color: color(m.accuracy) }}>{pct(m.accuracy)} <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>({m.hit}/{m.calls})</span></span>
            <span style={{ color: color(m.up_accuracy) }}>{pct(m.up_accuracy)}</span>
            <span style={{ color: color(m.down_accuracy) }}>{pct(m.down_accuracy)}</span>
            <span style={{ color: color(m.dir_accuracy) }}>{pct(m.dir_accuracy)}</span>
            <span style={{ color: "var(--text-muted)" }}>{pct(m.coverage)}</span>
          </Fragment>
        ))}
      </div>
      )}
      {model && (
        <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 10, display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
          <p style={{ color: "var(--text-muted)" }}>실시간 화면에 쓰는 방식 — ① 결합(모델+규칙을 백테스트 성적만큼 섞고 보정: 방향 50% 초과 + 판정이 50%·규칙보다 좋을 때) → ② 모델 단독(우연 수준을 넘을 때) → ③ 규칙 점수</p>
          {Object.keys(VARIANT_LABEL).map((v) => {
            const m = model[v];
            const mode = !m ? "학습 전" : m.stack_usable ? "결합 사용 중" : m.adopted ? "모델 사용 중" : "미사용 (규칙 점수)";
            return (
              <div key={v} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <span className={`badge ${m && (m.stack_usable || m.adopted) ? "badge-up" : "badge-neutral"}`} style={{ flexShrink: 0, minWidth: 96, justifyContent: "center" }}>
                  {mode}
                </span>
                <div>
                  <strong>{VARIANT_LABEL[v]}</strong>
                  {m ? (
                    <div style={{ color: "var(--text-muted)", lineHeight: 1.6 }}>
                      <div>모델 단독: {m.adopt_reason}</div>
                      <div>모델+규칙 결합: {m.stack_reason || "-"}</div>
                      <div>학습 {m.n?.toLocaleString()}건 (~{m.trained_until})</div>
                    </div>
                  ) : (
                    <span style={{ color: "var(--text-muted)", marginLeft: 6 }}>
                      {v.startsWith("KRF")
                        ? `수급 데이터가 쌓이면 학습 (KIS 는 최근 30일만 줘서 매일 저녁 쌓는 중 · 현재 ${flows?.rows?.toLocaleString() ?? 0}건, 학습에 약 800건 이상 + 검증 기간 필요 → 약 2~3개월)`
                        : "백테스트가 끝나면 학습됩니다"}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
          {model.index_data?.error && <p style={{ color: "var(--red)" }}>지수 데이터 조회 실패: {model.index_data.error}</p>}
        </div>
      )}
    </div>
  );
}

function RateBar({ rate, n }: { rate: number | null; n: number }) {
  if (rate === null) return <span style={{ color: "var(--text-muted)" }}>신호 없음</span>;
  const color = rate >= 55 ? "var(--green)" : rate >= 45 ? "var(--yellow)" : "var(--red)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "var(--bg-secondary)", borderRadius: 3, position: "relative" }}>
        <div style={{ width: `${rate}%`, height: "100%", background: color, borderRadius: 3 }} />
        <div style={{ position: "absolute", left: "50%", top: -2, width: 1, height: 10, background: "var(--text-muted)" }} />
      </div>
      <span style={{ color, fontWeight: 600, minWidth: 90 }}>{rate}% <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>({n}건)</span></span>
    </div>
  );
}

function FactorRow({ f }: { f: any }) {
  return (
    <>
      <span style={{ fontWeight: 600 }}>{f.name}</span>
      <RateBar rate={f.up_rate} n={f.up_n} />
      <RateBar rate={f.down_rate} n={f.down_n} />
    </>
  );
}

const MKT: Record<string, string> = { KR: "국내", US: "미국" };

/** 예측 검증 결과로 지표 비중 조정 — 덜 맞은 지표 비중 축소, 날짜별 검증(walk-forward)에서 나아질 때만 실시간에 씀 */
function WeightCard({ fw }: { fw: any }) {
  const markets = Object.entries(fw?.markets || {}) as [string, any][];
  return (
    <div className="card" data-testid="factor-weights" style={{ marginBottom: 20 }}>
      <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>지표 비중 자동 조정</p>
      <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12, lineHeight: 1.6 }}>
        과거 1년 백테스트에서 덜 맞은 지표(상승·하락 신호 적중률 평균 51% 미만)의 비중을 줄입니다 (최저 0.3배, 늘리지는 않음).
        날짜마다 그 전날까지의 결과로만 비중을 정해 다시 맞혀 본 결과가 원래보다 나을 때만 실시간 예측에 씁니다. 학습 모델을 쓰는 종목은 모델 확률이 먼저입니다.
      </p>
      {!markets.length && <p style={{ fontSize: 12, color: "var(--text-muted)" }}>아직 계산 전 — 과거 1년 백테스트가 끝나면 (하루 1번) 계산합니다</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
        {markets.map(([m, d]) => (
          <div key={m} data-testid={`fw-${m}`} style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <strong style={{ fontSize: 13 }}>{MKT[m] || m}</strong>
              <span className={`badge ${d.adopted ? "badge-up" : "badge-neutral"}`} style={{ fontSize: 10.5 }}>{d.adopted ? "실시간 예측에 사용 중" : "원래 비중 사용"}</span>
            </div>
            <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{d.reason}</span>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
                <th style={{ padding: "4px 6px", fontWeight: 500 }}>지표</th><th style={{ padding: "4px 6px", fontWeight: 500 }}>적중률</th>
                <th style={{ padding: "4px 6px", fontWeight: 500 }}>신호</th><th style={{ padding: "4px 6px", fontWeight: 500 }}>비중</th>
              </tr></thead>
              <tbody>
                {d.factors.map((f: any) => (
                  <tr key={f.name} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "4px 6px" }}>{f.name}</td>
                    <td style={{ padding: "4px 6px", color: f.accuracy != null && f.accuracy < 50 ? "var(--red)" : undefined }}>{f.accuracy != null ? `${f.accuracy}%` : "-"}</td>
                    <td style={{ padding: "4px 6px", color: "var(--text-muted)" }}>{f.n.toLocaleString()}건</td>
                    <td style={{ padding: "4px 6px", fontWeight: f.weight < 1 ? 700 : undefined, color: f.weight < 1 ? "var(--yellow)" : undefined }}>×{f.weight}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {d.walk_forward?.n > 0 && (
              <span style={{ fontSize: 11.5 }}>
                날짜별 검증 {d.walk_forward.n.toLocaleString()}건: 방향 적중률 원래 <strong>{d.walk_forward.base_accuracy}%</strong> → 조정 <strong>{d.walk_forward.weighted_accuracy}%</strong>
                {d.walk_forward.base_conf_accuracy != null && <> · 확신 예측(55%↑·45%↓) {d.walk_forward.base_conf_accuracy}% → {d.walk_forward.weighted_conf_accuracy}%</>}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
