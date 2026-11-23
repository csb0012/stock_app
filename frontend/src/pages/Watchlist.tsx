import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { watchlistApi, stockApi, errMsg } from "../api/client";
import { Star, Plus, Trash2, X, Search, Edit2, Check, Target, RefreshCw } from "lucide-react";
import FetchStatus from "../components/common/FetchStatus";
import ChangeTag from "../components/common/ChangeTag";
import PredictionReasons from "../components/common/PredictionReasons";
import BuyPrice from "../components/common/BuyPrice";
import { fmtPrice, fmtSigned, probColor, probLabel, sessionLabel } from "../components/common/format";

type Sort = "added" | "change" | "prob" | "target";

function useDebounce(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export default function Watchlist() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [query, setQuery] = useState("");
  const [marketFilter, setMarketFilter] = useState("ALL");
  const debouncedQ = useDebounce(query, 300);
  const inputRef = useRef<HTMLInputElement>(null);

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
    staleTime: 60_000,
  });

  const [sort, setSort] = useState<Sort>("added");
  const [editId, setEditId] = useState<number | null>(null);
  const [editMemo, setEditMemo] = useState("");
  const [editTarget, setEditTarget] = useState("");

  const watchlistSymbols = new Set((watchlist as any[]).map((w: any) => w.symbol));

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["watchlist"] });
    qc.invalidateQueries({ queryKey: ["watchlist-analysis"] });
  };

  const addMutation = useMutation({
    mutationFn: (item: any) => watchlistApi.add(item.symbol, item.market, item.name),
    onSuccess: refresh,
  });

  const removeMutation = useMutation({
    mutationFn: (id: number) => watchlistApi.remove(id),
    onSuccess: refresh,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, memo, target }: { id: number; memo: string; target: string }) =>
      watchlistApi.update(id, { memo, target_price: target ? parseFloat(target) : 0 }),
    onSuccess: () => { setEditId(null); refresh(); },
  });

  const analysisMap = new Map((analysis as any[]).map((a: any) => [a.id, a]));
  const rows = (watchlist as any[]).map((w: any) => ({ ...w, ...(analysisMap.get(w.id) || {}) }));
  const prob = (x: any) => x.prediction?.probability ?? -1;
  const sorted = [...rows].sort((a, b) =>
    sort === "change" ? (b.change_rate ?? -999) - (a.change_rate ?? -999)
    : sort === "prob" ? prob(b) - prob(a)
    : sort === "target" ? (a.target_gap_pct ?? 999) - (b.target_gap_pct ?? 999)
    : a.id - b.id
  );
  const reachedCount = rows.filter((r) => r.target_reached).length;

  function openModal() {
    setShowAdd(true);
    setQuery("");
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function closeModal() {
    setShowAdd(false);
    setQuery("");
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>관심종목</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>현재가 · 다음 거래일 전망 · 메모 · 목표 매수가 알림</p>
        </div>
        <button className="btn btn-primary" onClick={openModal}>
          <Plus size={14} />
          종목 추가
        </button>
      </div>

      {/* Add Modal */}
      {showAdd && (
        <div
          style={{ position: "fixed", inset: 0, background: "var(--overlay)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
          onClick={(e) => e.target === e.currentTarget && closeModal()}
        >
          <div className="card" style={{ width: 440, maxHeight: "80vh", display: "flex", flexDirection: "column", position: "relative" }}>
            <button onClick={closeModal} style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
              <X size={18} />
            </button>

            <h3 style={{ fontWeight: 700, marginBottom: 16 }}>관심종목 추가</h3>

            {/* 검색 인풋 */}
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

            {/* 검색 결과 */}
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
                        style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "10px 12px", borderRadius: 8,
                          background: "var(--bg-secondary)",
                          opacity: inList ? 0.5 : 1,
                        }}
                      >
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ fontWeight: 600, fontSize: 14 }}>{item.name}</span>
                            <span style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, background: item.market === "KR" ? "color-mix(in srgb, var(--accent) 15%, transparent)" : "color-mix(in srgb, var(--green) 15%, transparent)", color: item.market === "KR" ? "var(--accent)" : "var(--green)" }}>
                              {item.market}
                            </span>
                            {item.type === "etf" && (
                              <span style={{ fontSize: 10, padding: "2px 5px", borderRadius: 4, background: "color-mix(in srgb, var(--yellow) 15%, transparent)", color: "var(--yellow)" }}>ETF</span>
                            )}
                          </div>
                          <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{item.symbol}</span>
                        </div>
                        <button
                          onClick={() => !inList && addMutation.mutate(item)}
                          disabled={inList}
                          style={{
                            padding: "5px 14px", borderRadius: 6, border: "none", cursor: inList ? "default" : "pointer",
                            background: inList ? "rgba(100,100,100,0.1)" : "var(--accent)",
                            color: inList ? "var(--text-muted)" : "var(--on-accent)",
                            fontSize: 12, fontWeight: 600, flexShrink: 0,
                          }}
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

      {/* 관심종목 목록 */}
      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : rows.length === 0 ? (
        <div style={{ textAlign: "center", paddingTop: 60 }}>
          <Star size={40} style={{ color: "var(--border)", margin: "0 auto 12px" }} />
          <p style={{ color: "var(--text-muted)" }}>관심종목을 추가해보세요</p>
        </div>
      ) : (
        <>
          {/* 정렬 + 새로고침 */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, gap: 8, flexWrap: "wrap" }}>
            <div style={{ display: "flex", gap: 6 }}>
              {([["added", "추가순"], ["change", "등락률순"], ["prob", "상승확률순"], ["target", "목표가 근접순"]] as [Sort, string][]).map(([k, label]) => (
                <button key={k} className={`btn ${sort === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "6px 10px" }} onClick={() => setSort(k)}>
                  {label}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {reachedCount > 0 && (
                <span className="badge badge-up"><Target size={11} style={{ marginRight: 4 }} />목표가 도달 {reachedCount}종목</span>
              )}
              <FetchStatus updatedAt={dataUpdatedAt} fetching={analyzing} />
              <button className="btn btn-ghost" style={{ fontSize: 12, padding: "6px 10px" }} onClick={() => refetch()} disabled={analyzing}>
                <RefreshCw size={13} />
                {analyzing ? "분석 중..." : "새로고침"}
              </button>
            </div>
          </div>
          {analysisError && (
            <p style={{ color: "var(--red)", fontSize: 13, marginBottom: 10 }}>시세 조회 실패{(analysis as any[]).length ? " (이전 값 표시 중)" : ""}: {errMsg(analysisError)}</p>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {sorted.map((item: any) => {
              const pred = item.prediction;
              const isEditing = editId === item.id;
              const range = item.high_period && item.low_period ? item.high_period - item.low_period : 0;
              const pos = range > 0 ? ((item.current_price - item.low_period) / range) * 100 : null;
              return (
                <div key={item.id} className="card" style={{ padding: "14px 16px", borderColor: item.target_reached ? "color-mix(in srgb, var(--green) 50%, transparent)" : undefined }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                    {/* 종목 + 시세 */}
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        <Star size={14} style={{ color: "var(--yellow)" }} />
                        <span style={{ fontWeight: 700, fontSize: 15 }}>{item.name || item.symbol}</span>
                        <span className="badge badge-neutral">{item.symbol}</span>
                        <span className="badge badge-neutral">{item.market === "KR" ? "국내" : "미국"}</span>
                        {item.target_reached && <span className="badge badge-up">목표가 도달</span>}
                      </div>
                      {item.error ? (
                        <p style={{ color: "var(--red)", fontSize: 12 }}>시세 조회 실패: {item.error}</p>
                      ) : item.current_price !== undefined ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", fontSize: 12, color: "var(--text-secondary)" }}>
                          <strong style={{ fontSize: 16, color: "var(--text-primary)" }}>{fmtPrice(item.current_price, item.market)}</strong>
                          <ChangeTag value={item.change_rate} />
                          {item.change_5d != null && <span>5일 {fmtSigned(item.change_5d)}%</span>}
                          {item.change_20d != null && <span>20일 {fmtSigned(item.change_20d)}%</span>}
                          {item.rsi != null && <span>RSI {item.rsi}</span>}
                        </div>
                      ) : (
                        <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{analyzing ? "시세 불러오는 중..." : "-"}</p>
                      )}
                      {pos !== null && (
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: 11, color: "var(--text-muted)" }}>
                          <span>{item.period_days}일 저가 {fmtPrice(item.low_period, item.market)}</span>
                          <div style={{ width: 90, height: 4, background: "var(--bg-secondary)", borderRadius: 2, position: "relative" }}>
                            <div style={{ position: "absolute", left: `calc(${pos}% - 3px)`, top: -2, width: 6, height: 8, borderRadius: 2, background: "var(--accent)" }} />
                          </div>
                          <span>고가 {fmtPrice(item.high_period, item.market)}</span>
                        </div>
                      )}
                    </div>

                    {/* 내일 전망 */}
                    <div style={{ minWidth: 220, maxWidth: 360 }}>
                      {pred && (
                        <>
                          <p style={{ fontSize: 11, color: "var(--text-muted)" }}>{sessionLabel(pred)} 전망</p>
                          <p style={{ fontWeight: 700, fontSize: 13, color: probColor(pred.probability) }}>
                            상승 확률 {pred.probability}% · {probLabel(pred.probability)}
                          </p>
                          <BuyPrice pred={pred} market={item.market} compact label="AI 추천 매입가" />
                          <PredictionReasons pred={pred} />
                        </>
                      )}
                    </div>
                  </div>

                  {/* 메모 / 목표가 */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
                    {isEditing ? (
                      <div style={{ display: "flex", gap: 8, flex: 1, flexWrap: "wrap" }}>
                        <input
                          value={editMemo}
                          onChange={(e) => setEditMemo(e.target.value)}
                          placeholder="메모 (관심 이유, 매수 조건 등)"
                          style={{ flex: 2, minWidth: 180, padding: "6px 10px", background: "var(--bg-secondary)", border: "1px solid var(--accent)", borderRadius: 6, color: "var(--text-primary)", fontSize: 13, outline: "none" }}
                        />
                        <input
                          type="number"
                          value={editTarget}
                          onChange={(e) => setEditTarget(e.target.value)}
                          placeholder={`목표 매수가 (${item.market === "KR" ? "원" : "$"})`}
                          style={{ flex: 1, minWidth: 120, padding: "6px 10px", background: "var(--bg-secondary)", border: "1px solid var(--accent)", borderRadius: 6, color: "var(--text-primary)", fontSize: 13, outline: "none" }}
                        />
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: 14, flex: 1, fontSize: 12, color: "var(--text-secondary)", flexWrap: "wrap" }}>
                        <span>{item.memo ? `📝 ${item.memo}` : <span style={{ color: "var(--text-muted)" }}>메모 없음</span>}</span>
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
                    )}
                    <div style={{ display: "flex", gap: 6 }}>
                      {isEditing ? (
                        <>
                          <button className="btn btn-primary" style={{ padding: "5px 12px", fontSize: 12 }}
                            onClick={() => updateMutation.mutate({ id: item.id, memo: editMemo, target: editTarget })}>
                            <Check size={13} />저장
                          </button>
                          <button className="btn btn-ghost" style={{ padding: "5px 10px" }} onClick={() => setEditId(null)}>
                            <X size={13} />
                          </button>
                        </>
                      ) : (
                        <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12 }}
                          onClick={() => { setEditId(item.id); setEditMemo(item.memo || ""); setEditTarget(item.target_price ? String(item.target_price) : ""); }}>
                          <Edit2 size={13} />메모·목표가
                        </button>
                      )}
                      <button className="btn btn-ghost" style={{ padding: "5px 10px", color: "var(--red)" }} onClick={() => removeMutation.mutate(item.id)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
