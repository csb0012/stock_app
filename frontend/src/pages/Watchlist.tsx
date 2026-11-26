import { useState, useEffect, useRef } from "react";
import { useLivePrices, withLive } from "../components/common/useLivePrices";
import LiveBadge from "../components/common/LiveBadge";
import PriceSource from "../components/common/PriceSource";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { watchlistApi, stockApi, errMsg } from "../api/client";
import { Star, Plus, Trash2, X, Search, Edit2, Check, Target, RefreshCw, LayoutGrid, List } from "lucide-react";
import FetchStatus from "../components/common/FetchStatus";
import ChangeTag from "../components/common/ChangeTag";
import PredictionReasons from "../components/common/PredictionReasons";
import PriceLevels from "../components/common/PriceLevels";
import DaytimePrice, { extPrice, SessionTag } from "../components/common/DaytimePrice";
import QuantBadge, { TrackBadge } from "../components/common/QuantBadge";
import { RegimeWarning } from "../components/common/MarketRegime";
import { fmtPrice, fmtSigned, probColor, probLabel, sessionLabel } from "../components/common/format";

type Sort = "added" | "change" | "prob" | "buy" | "target";
type Market = "KR" | "US";
type View = "card" | "table";

const SORTS: [Sort, string][] = [
  ["added", "추가순"], ["change", "등락률순"], ["prob", "상승확률순"], ["buy", "매입가 근접순"], ["target", "목표 매수가 근접순"],
];
const REFRESH_SEC = 60;

function useDebounce(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/** 화면 설정(탭·보기 방식)을 브라우저에 기억 — 저장소를 못 쓰면 기본값 */
function useStored<T extends string>(key: string, initial: T, allowed: readonly T[]): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const s = localStorage.getItem(key) as T | null;
      return s && allowed.includes(s) ? s : initial;
    } catch { return initial; }
  });
  const set = (x: T) => {
    setV(x);
    try { localStorage.setItem(key, x); } catch { /* 저장 못 해도 동작엔 영향 없음 */ }
  };
  return [v, set];
}

const pct = (v: number | null | undefined) => (v == null ? "-" : `${fmtSigned(v)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "var(--text-muted)" : v > 0 ? "var(--green)" : "var(--red)");

export default function Watchlist() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [query, setQuery] = useState("");
  const [marketFilter, setMarketFilter] = useState("ALL");
  const debouncedQ = useDebounce(query, 300);
  const inputRef = useRef<HTMLInputElement>(null);
  const [market, setMarket] = useStored<Market>("watchlist-market", "KR", ["KR", "US"]);
  const [view, setView] = useStored<View>("watchlist-view", "card", ["card", "table"]);
  const [sort, setSort] = useStored<Sort>("watchlist-sort", "added", ["added", "change", "prob", "buy", "target"]);
  const [editId, setEditId] = useState<number | null>(null);

  const { data: watchlist = [], isLoading } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list().then((r) => r.data),
  });

  const { data: searchResults = [], isFetching: searching } = useQuery({
    queryKey: ["stock-search", debouncedQ, marketFilter],
    queryFn: () => stockApi.search(debouncedQ, marketFilter).then((r) => r.data),
    enabled: debouncedQ.length >= 1,
  });

  const { data: analysis = [], isFetching: analyzing, error: analysisError, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["watchlist-analysis"],
    queryFn: () => watchlistApi.analysis().then((r) => r.data),
    enabled: (watchlist as any[]).length > 0,
    staleTime: 30_000,
    refetchInterval: REFRESH_SEC * 1000,   // 현재가·전망·주간거래 가격 1분마다
    refetchIntervalInBackground: false,
  });

  const watchlistSymbols = new Set((watchlist as any[]).map((w: any) => w.symbol));

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["watchlist"] });
    qc.invalidateQueries({ queryKey: ["watchlist-analysis"] });
  };

  const addMutation = useMutation({
    mutationFn: (item: any) => watchlistApi.add(item.symbol, item.market, item.name),
    meta: { inlineError: true },
    onSuccess: (_, item: any) => { refresh(); if (item.market === "KR" || item.market === "US") setMarket(item.market); },
  });

  const removeMutation = useMutation({
    mutationFn: (id: number) => watchlistApi.remove(id),
    onSuccess: refresh,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, memo, target }: { id: number; memo: string; target: string }) =>
      watchlistApi.update(id, { memo, target_price: target ? parseFloat(target) : 0 }),
    meta: { inlineError: true },
    onSuccess: () => { setEditId(null); refresh(); },
  });

  const analysisMap = new Map((analysis as any[]).map((a: any) => [a.id, a]));
  // 국내 종목 현재가는 KIS 실시간(웹소켓) 값으로 2초마다 덮어씀 — 전망·확률은 1분 갱신 그대로
  const live = useLivePrices((watchlist as any[]).filter((w: any) => w.market === "KR").map((w: any) => w.symbol));
  const allRows = (watchlist as any[]).map((w: any) => {
    const r = { ...w, ...(analysisMap.get(w.id) || {}) };
    return r.current_price !== undefined ? withLive(r, live) : r;
  });
  const counts = { KR: allRows.filter((r) => r.market === "KR").length, US: allRows.filter((r) => r.market === "US").length };
  // 고른 시장에 종목이 없고 다른 시장엔 있으면 그쪽을 보여줌 (처음 들어왔을 때 빈 화면 방지)
  const shownMarket: Market = counts[market] === 0 && counts[market === "KR" ? "US" : "KR"] > 0 ? (market === "KR" ? "US" : "KR") : market;
  const rows = allRows.filter((r) => r.market === shownMarket);

  const prob = (x: any) => x.prediction?.probability ?? -1;
  const buyGap = (x: any) => (x.prediction?.buy_gap_pct == null ? 999 : Math.abs(x.prediction.buy_gap_pct));
  const sorted = [...rows].sort((a, b) =>
    sort === "change" ? (b.change_rate ?? -999) - (a.change_rate ?? -999)
    : sort === "prob" ? prob(b) - prob(a)
    : sort === "buy" ? buyGap(a) - buyGap(b)
    : sort === "target" ? (a.target_gap_pct ?? 999) - (b.target_gap_pct ?? 999)
    : a.id - b.id
  );

  // 요약: 상승·하락 종목 수, 평균 등락률, 상승 확률 55% 이상, 목표 매수가 도달
  const priced = rows.filter((r) => typeof r.change_rate === "number");
  const summary = {
    up: priced.filter((r) => r.change_rate > 0).length,
    down: priced.filter((r) => r.change_rate < 0).length,
    avg: priced.length ? priced.reduce((s, r) => s + r.change_rate, 0) / priced.length : null,
    bullish: rows.filter((r) => prob(r) >= 55).length,
    reached: rows.filter((r) => r.target_reached).length,
  };

  // 메모·목표 매수가도 같이 지워지므로 한 번 확인
  const confirmRemove = (item: any) => {
    if (item && window.confirm(`${item.name || item.symbol} 을(를) 관심종목에서 삭제할까요? (메모·목표 매수가도 지워짐)`)) removeMutation.mutate(item.id);
  };

  useEffect(() => {
    if (!showAdd) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeModal(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showAdd]);

  function openModal() {
    setShowAdd(true);
    setQuery("");
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function closeModal() {
    setShowAdd(false);
    setQuery("");
  }

  const editor = (item: any) => (
    <MemoEditor
      item={item}
      saving={updateMutation.isPending}
      error={updateMutation.error ? errMsg(updateMutation.error) : null}
      onSave={(memo, target) => updateMutation.mutate({ id: item.id, memo, target })}
      onCancel={() => setEditId(null)}
    />
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>관심종목</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            현재가 · 다음 거래일 전망 · 추천 매입가/목표가/손절가 · 메모 · 목표 매수가 알림 ({REFRESH_SEC}초마다 갱신)
          </p>
        </div>
        <button className="btn btn-primary" onClick={openModal} style={{ flexShrink: 0 }}>
          <Plus size={14} />
          종목 추가
        </button>
      </div>

      {/* Add Modal */}
      {showAdd && (
        <div
          style={{ position: "fixed", inset: 0, background: "var(--overlay)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16 }}
          onClick={(e) => e.target === e.currentTarget && closeModal()}
          onKeyDown={(e) => e.key === "Escape" && closeModal()}
        >
          <div className="card" role="dialog" aria-label="관심종목 추가" style={{ width: 440, maxWidth: "100%", maxHeight: "80vh", display: "flex", flexDirection: "column", position: "relative" }}>
            <button onClick={closeModal} aria-label="닫기" style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
              <X size={18} />
            </button>

            <h3 style={{ fontWeight: 700, marginBottom: 16 }}>관심종목 추가</h3>

            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <div style={{ flex: 1, position: "relative" }}>
                <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)", pointerEvents: "none" }} />
                <input
                  ref={inputRef}
                  placeholder="종목명 또는 코드 검색 (예: 삼성, SOXL, 005930)"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  style={{ width: "100%", padding: "9px 12px 9px 32px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none", boxSizing: "border-box" }}
                />
              </div>
              <select
                value={marketFilter}
                onChange={(e) => setMarketFilter(e.target.value)}
                style={{ padding: "9px 10px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 13, outline: "none", cursor: "pointer" }}
              >
                <option value="ALL">전체</option>
                <option value="KR">국내</option>
                <option value="US">미국</option>
              </select>
            </div>

            {addMutation.error && (
              <p style={{ color: "var(--red)", fontSize: 12, marginBottom: 8 }}>추가 실패: {errMsg(addMutation.error)}</p>
            )}

            <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
              {debouncedQ.length === 0 ? (
                <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: "24px 0" }}>종목명 또는 코드를 입력하세요</p>
              ) : searching ? (
                <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: "24px 0" }}>검색 중...</p>
              ) : (searchResults as any[]).length === 0 ? (
                <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: "24px 0" }}>검색 결과 없음</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  {(searchResults as any[]).map((item: any) => {
                    const inList = watchlistSymbols.has(item.symbol);
                    return (
                      <div
                        key={`${item.market}-${item.symbol}`}
                        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderRadius: 8, background: "var(--bg-secondary)", opacity: inList ? 0.5 : 1 }}
                      >
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ fontWeight: 600, fontSize: 14 }}>{item.name}</span>
                            <span className={`badge ${item.market === "KR" ? "badge-accent" : "badge-up"}`}>{item.market}</span>
                            {item.type === "etf" && <span className="badge" style={{ background: "color-mix(in srgb, var(--yellow) 15%, transparent)", color: "var(--yellow)" }}>ETF</span>}
                          </div>
                          <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{item.symbol}</span>
                        </div>
                        <button
                          className={`btn ${inList ? "btn-ghost" : "btn-primary"}`}
                          onClick={() => !inList && addMutation.mutate(item)}
                          disabled={inList || addMutation.isPending}
                          style={{ padding: "5px 14px", fontSize: 12, fontWeight: 600, flexShrink: 0 }}
                        >
                          {inList ? "추가됨" : "추가"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : allRows.length === 0 ? (
        <div style={{ textAlign: "center", paddingTop: 60 }}>
          <Star size={40} style={{ color: "var(--border)", margin: "0 auto 12px" }} />
          <p style={{ color: "var(--text-muted)" }}>관심종목을 추가해보세요</p>
        </div>
      ) : (
        <>
          {/* 국내 / 미국 탭 + 보기 방식 */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <div style={{ display: "flex", gap: 6 }} role="tablist">
              {(["KR", "US"] as Market[]).map((m) => (
                <button key={m} role="tab" aria-selected={shownMarket === m} data-testid={`tab-${m}`}
                  className={`btn ${shownMarket === m ? "btn-primary" : "btn-ghost"}`} style={{ minWidth: 96 }} onClick={() => setMarket(m)}>
                  {m === "KR" ? "🇰🇷 국내" : "🇺🇸 미국"} <span style={{ opacity: 0.75 }}>{counts[m]}</span>
                </button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              <button className={`btn ${view === "card" ? "btn-primary" : "btn-ghost"}`} style={{ padding: "6px 10px", fontSize: 12 }}
                onClick={() => setView("card")} aria-pressed={view === "card"} title="카드로 보기">
                <LayoutGrid size={13} />카드
              </button>
              <button className={`btn ${view === "table" ? "btn-primary" : "btn-ghost"}`} style={{ padding: "6px 10px", fontSize: 12 }}
                onClick={() => setView("table")} aria-pressed={view === "table"} title="표로 보기 — 한 화면에 많이">
                <List size={13} />표
              </button>
            </div>
          </div>

          {/* 정렬 + 새로고침 */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, gap: 8, flexWrap: "wrap" }}>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {SORTS.map(([k, label]) => (
                <button key={k} className={`btn ${sort === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => setSort(k)}>
                  {label}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <FetchStatus updatedAt={dataUpdatedAt} fetching={analyzing} />
              <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => refetch()} disabled={analyzing}>
                <RefreshCw size={13} />
                {analyzing ? "분석 중..." : "새로고침"}
              </button>
            </div>
          </div>

          <RegimeWarning market={shownMarket} />

          {/* 요약 */}
          {rows.length > 0 && (
            <div data-testid="watch-summary" style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
              <span>{rows.length}종목</span>
              <span>상승 <strong style={{ color: "var(--green)" }}>{summary.up}</strong> · 하락 <strong style={{ color: "var(--red)" }}>{summary.down}</strong></span>
              {summary.avg != null && <span>평균 등락 <strong style={{ color: tone(summary.avg) }}>{pct(summary.avg)}</strong></span>}
              <span>상승 확률 55% 이상 <strong>{summary.bullish}</strong></span>
              {summary.reached > 0 && (
                <span className="badge badge-up"><Target size={11} style={{ marginRight: 4 }} />목표 매수가 도달 {summary.reached}</span>
              )}
            </div>
          )}

          {analysisError && (
            <p style={{ color: "var(--red)", fontSize: 13, marginBottom: 10 }}>시세 조회 실패{(analysis as any[]).length ? " (이전 값 표시 중)" : ""}: {errMsg(analysisError)}</p>
          )}

          {rows.length === 0 ? (
            <p style={{ color: "var(--text-muted)", textAlign: "center", paddingTop: 40 }}>
              {shownMarket === "KR" ? "국내" : "미국"} 관심종목이 없습니다 — '종목 추가'로 넣어 보세요
            </p>
          ) : view === "table" ? (
            <WatchTable rows={sorted} analyzing={analyzing} editId={editId} setEditId={setEditId} editor={editor}
              onRemove={(id) => confirmRemove(allRows.find((r) => r.id === id))} />
          ) : (
            <div className="card-grid" data-testid="watch-grid">
              {sorted.map((item: any) => (
                <WatchCard key={item.id} item={item} analyzing={analyzing} editing={editId === item.id}
                  onEdit={() => setEditId(item.id)} editor={editor} onRemove={() => confirmRemove(item)} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** 메모·목표 매수가 수정 칸 */
function MemoEditor({ item, saving, error, onSave, onCancel }: {
  item: any; saving: boolean; error: string | null; onSave: (memo: string, target: string) => void; onCancel: () => void;
}) {
  const [memo, setMemo] = useState(item.memo || "");
  const [target, setTarget] = useState(item.target_price ? String(item.target_price) : "");
  const input: React.CSSProperties = {
    padding: "6px 10px", background: "var(--bg-secondary)", border: "1px solid var(--accent)", borderRadius: 6,
    color: "var(--text-primary)", fontSize: 13, outline: "none", minWidth: 0,
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <input autoFocus value={memo} onChange={(e) => setMemo(e.target.value)} placeholder="메모 (관심 이유, 매수 조건 등)" style={input}
        onKeyDown={(e) => e.key === "Enter" && onSave(memo, target)} />
      <div style={{ display: "flex", gap: 6 }}>
        <input type="number" value={target} onChange={(e) => setTarget(e.target.value)} placeholder={`목표 매수가 (${item.market === "KR" ? "원" : "$"}, 비우면 삭제)`}
          style={{ ...input, flex: 1 }} onKeyDown={(e) => e.key === "Enter" && onSave(memo, target)} />
        <button className="btn btn-primary" style={{ padding: "5px 12px", fontSize: 12 }} disabled={saving} onClick={() => onSave(memo, target)}>
          <Check size={13} />저장
        </button>
        <button className="btn btn-ghost" style={{ padding: "5px 10px" }} onClick={onCancel} aria-label="취소"><X size={13} /></button>
      </div>
      {error && <p style={{ color: "var(--red)", fontSize: 12 }}>저장 실패: {error}</p>}
    </div>
  );
}

function MemoLine({ item }: { item: any }) {
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", fontSize: 12, color: "var(--text-secondary)", minWidth: 0 }}>
      <span className="clamp-2" title={item.memo || undefined}>{item.memo ? `📝 ${item.memo}` : <span style={{ color: "var(--text-muted)" }}>메모 없음</span>}</span>
      {item.target_price ? (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <Target size={12} />
          목표 매수가 {fmtPrice(item.target_price, item.market)}
          {item.target_gap_pct != null && !item.target_reached && (
            <span style={{ color: "var(--text-muted)" }}> (현재가가 {fmtSigned(item.target_gap_pct)}% 위)</span>
          )}
        </span>
      ) : null}
    </div>
  );
}

function ProbBar({ p }: { p: number }) {
  return (
    <div style={{ height: 5, background: "var(--bg-secondary)", borderRadius: 3, overflow: "hidden" }} aria-hidden>
      <div style={{ width: `${p}%`, height: "100%", background: probColor(p), borderRadius: 3 }} />
    </div>
  );
}

function RangeBar({ item }: { item: any }) {
  const range = item.high_period && item.low_period ? item.high_period - item.low_period : 0;
  if (!(range > 0)) return null;
  const pos = Math.min(100, Math.max(0, ((item.current_price - item.low_period) / range) * 100));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10.5, color: "var(--text-muted)" }}
      title={`최근 ${item.period_days}거래일 저가~고가 중 현재 위치 ${pos.toFixed(0)}%`}>
      <span>저 {fmtPrice(item.low_period, item.market)}</span>
      <div style={{ flex: 1, minWidth: 40, height: 4, background: "var(--bg-secondary)", borderRadius: 2, position: "relative" }}>
        <div style={{ position: "absolute", left: `calc(${pos}% - 3px)`, top: -2, width: 6, height: 8, borderRadius: 2, background: "var(--accent)" }} />
      </div>
      <span>고 {fmtPrice(item.high_period, item.market)}</span>
    </div>
  );
}

/** 관심종목 카드 (3열 격자용으로 세로로 짧게) */
function WatchCard({ item, analyzing, editing, onEdit, editor, onRemove }: {
  item: any; analyzing: boolean; editing: boolean; onEdit: () => void; editor: (item: any) => React.ReactNode; onRemove: () => void;
}) {
  const pred = item.prediction;
  const ext = extPrice(item.daytime);   // 미국 프리·애프터마켓이면 현재가 자리에 그 가격
  return (
    <div className="card" data-testid="watch-card" style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 9, minWidth: 0,
      borderColor: item.target_reached ? "color-mix(in srgb, var(--green) 50%, transparent)" : undefined }}>
      {/* 머리: 종목 + 버튼 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, fontSize: 14.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "100%" }} title={item.name}>
            {item.name || item.symbol}
          </span>
          <span className="badge badge-neutral">{item.symbol}</span>
          {item.target_reached && <span className="badge badge-up">목표가 도달</span>}
        </div>
        <div style={{ display: "flex", gap: 2, flexShrink: 0 }}>
          <button className="btn btn-ghost" style={{ padding: "4px 7px", border: "none" }} onClick={onEdit} title="메모·목표 매수가" aria-label="메모·목표 매수가 수정">
            <Edit2 size={13} />
          </button>
          <button className="btn btn-ghost" style={{ padding: "4px 7px", border: "none", color: "var(--red)" }} onClick={onRemove} title="관심종목에서 삭제" aria-label="삭제">
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* 시세 */}
      {item.error ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <p style={{ color: "var(--red)", fontSize: 12 }}>시세 조회 실패: {item.error}</p>
          <DaytimePrice d={item.daytime} size={11.5} />
        </div>
      ) : item.current_price !== undefined ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            {ext && <SessionTag d={ext} close={item.current_price} closeRate={item.change_rate} />}
            <strong data-testid="main-price" style={{ fontSize: 17, fontVariantNumeric: "tabular-nums" }}>{fmtPrice(ext ? ext.price : item.current_price, item.market)}</strong>
            <ChangeTag value={ext ? ext.change_rate : item.change_rate} />
            <LiveBadge t={item.live_time} />
            {!ext && <PriceSource src={item.price_source} />}
            {!ext && <DaytimePrice d={item.daytime} size={11.5} />}
          </div>
          <div style={{ display: "flex", gap: 10, fontSize: 11.5, color: "var(--text-secondary)", flexWrap: "wrap" }}>
            <span>5일 <span style={{ color: tone(item.change_5d) }}>{pct(item.change_5d)}</span></span>
            <span>20일 <span style={{ color: tone(item.change_20d) }}>{pct(item.change_20d)}</span></span>
            {item.rsi != null && <span>RSI {Number(item.rsi).toFixed(0)}</span>}
          </div>
          {(item.quant || item.track) && (
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <QuantBadge q={item.quant} size={11} /><TrackBadge t={item.track} />
            </div>
          )}
          <RangeBar item={item} />
        </div>
      ) : (
        <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{analyzing ? "시세 불러오는 중..." : "-"}</p>
      )}

      {/* 전망 + 가격대 */}
      {pred && (
        <div style={{ display: "flex", flexDirection: "column", gap: 7, borderTop: "1px solid var(--border)", paddingTop: 9 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6 }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{sessionLabel(pred)} 전망</span>
            <span style={{ fontWeight: 700, fontSize: 12.5, color: probColor(pred.probability) }}>
              상승 {pred.probability}% · {probLabel(pred.probability)}
            </span>
          </div>
          <ProbBar p={pred.probability} />
          <PriceLevels pred={pred} market={item.market} dense />
          <PredictionReasons pred={pred} compact />
        </div>
      )}

      {/* 메모 */}
      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 8, marginTop: "auto" }}>
        {editing ? editor(item) : <MemoLine item={item} />}
      </div>
    </div>
  );
}

/** 표 보기 — 한 화면에 많은 종목 */
function WatchTable({ rows, analyzing, editId, setEditId, editor, onRemove }: {
  rows: any[]; analyzing: boolean; editId: number | null; setEditId: (id: number | null) => void;
  editor: (item: any) => React.ReactNode; onRemove: (id: number) => void;
}) {
  const heads = ["종목", "현재가", "등락", "5일", "20일", "전망", "퀀트·적중", "추천 매입가", "목표가", "손절가", "목표 매수가", "메모", ""];
  const numCols = new Set([1, 2, 3, 4, 7, 8, 9, 10]);
  return (
    <div className="card" style={{ padding: 0, overflowX: "auto" }}>
      <table className="data-table" data-testid="watch-table">
        <thead>
          <tr>{heads.map((h, i) => <th key={i} className={numCols.has(i) ? "num" : undefined}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const p = r.prediction;
            const m = r.market;
            if (editId === r.id) {
              return (
                <tr key={r.id}>
                  <td style={{ fontWeight: 600 }}>{r.name}</td>
                  <td colSpan={heads.length - 1} style={{ whiteSpace: "normal" }}>{editor(r)}</td>
                </tr>
              );
            }
            return (
              <tr key={r.id} style={r.target_reached ? { background: "color-mix(in srgb, var(--green) 6%, transparent)" } : undefined}>
                <td>
                  <div style={{ fontWeight: 600 }}>{r.name || r.symbol}</div>
                  <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{r.symbol}</div>
                </td>
                {r.error ? (
                  <td colSpan={9} style={{ color: "var(--red)", whiteSpace: "normal" }}>시세 조회 실패: {r.error}</td>
                ) : r.current_price === undefined ? (
                  <td colSpan={9} style={{ color: "var(--text-muted)" }}>{analyzing ? "불러오는 중..." : "-"}</td>
                ) : (
                  <>
                    <td className="num">
                      {extPrice(r.daytime) ? (
                        <div style={{ fontWeight: 600 }}><SessionTag d={r.daytime} close={r.current_price} closeRate={r.change_rate} size={10} /> {fmtPrice(r.daytime.price, m)}</div>
                      ) : (
                        <div style={{ fontWeight: 600 }}>{fmtPrice(r.current_price, m)} <LiveBadge t={r.live_time} /> <PriceSource src={r.price_source} /></div>
                      )}
                      {r.daytime && !r.daytime.error && !extPrice(r.daytime) && (
                        <div data-testid="daytime-short" style={{ fontSize: 10.5, color: "var(--accent)" }} title={`${r.daytime.label || "주간거래"} ${r.daytime.time}`}>
                          주간 {fmtPrice(r.daytime.price, m)} ({fmtSigned(r.daytime.change_rate)}%)
                        </div>
                      )}
                    </td>
                    <td className="num" style={{ color: tone(extPrice(r.daytime)?.change_rate ?? r.change_rate) }}>{pct(extPrice(r.daytime)?.change_rate ?? r.change_rate)}</td>
                    <td className="num" style={{ color: tone(r.change_5d) }}>{pct(r.change_5d)}</td>
                    <td className="num" style={{ color: tone(r.change_20d) }}>{pct(r.change_20d)}</td>
                    <td>
                      {p ? <span style={{ color: probColor(p.probability), fontWeight: 600 }} title={p.summary}>{p.probability}% {probLabel(p.probability)}</span> : "-"}
                    </td>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        {r.quant ? <QuantBadge q={r.quant} size={10.5} /> : null}
                        <TrackBadge t={r.track} size={10.5} />
                        {!r.quant && !r.track?.n && <span style={{ color: "var(--text-muted)" }}>-</span>}
                      </div>
                    </td>
                    <td className="num" style={{ color: "var(--accent)" }} title={p?.buy_comment}>
                      {fmtPrice(p?.buy_price, m)}
                      {p?.buy_gap_pct != null && <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{p.buy_gap_pct.toFixed(1)}%</div>}
                    </td>
                    <td className="num" style={{ color: "var(--green)" }}>{fmtPrice(p?.target_price, m)}</td>
                    <td className="num" style={{ color: "var(--red)" }}>{fmtPrice(p?.stop_loss, m)}</td>
                  </>
                )}
                <td className="num">
                  {r.target_price ? fmtPrice(r.target_price, m) : <span style={{ color: "var(--text-muted)" }}>-</span>}
                  {r.target_reached && <div><span className="badge badge-up">도달</span></div>}
                </td>
                <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", color: "var(--text-secondary)" }} title={r.memo || undefined}>{r.memo || "-"}</td>
                <td>
                  <div style={{ display: "flex", gap: 2 }}>
                    <button className="btn btn-ghost" style={{ padding: "3px 6px", border: "none" }} onClick={() => setEditId(r.id)} aria-label="메모·목표 매수가 수정"><Edit2 size={12} /></button>
                    <button className="btn btn-ghost" style={{ padding: "3px 6px", border: "none", color: "var(--red)" }} onClick={() => onRemove(r.id)} aria-label="삭제"><Trash2 size={12} /></button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
