import { useState, useEffect, useRef } from "react";
import PriceSource from "../components/common/PriceSource";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { portfolioApi, stockApi, errMsg } from "../api/client";
import FetchStatus from "../components/common/FetchStatus";
import ChangeTag from "../components/common/ChangeTag";
import PredictionReasons from "../components/common/PredictionReasons";
import BuyPrice from "../components/common/BuyPrice";
import DaytimePrice from "../components/common/DaytimePrice";
import { probLabel, sessionLabel } from "../components/common/format";
import { Briefcase, Plus, Trash2, X, Search, Edit2, Check, AlertTriangle } from "lucide-react";

function useDebounce(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

function ProbBadge({ value }: { value: number }) {
  const color = value >= 65 ? "var(--green)" : value >= 45 ? "var(--yellow)" : "var(--red)";
  const label = probLabel(value);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 50, height: 5, background: "var(--bg-secondary)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${value}%`, height: "100%", background: color, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, color }}>{value}%</span>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</span>
    </div>
  );
}

export default function Portfolio() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [query, setQuery] = useState("");
  const [marketFilter, setMarketFilter] = useState("ALL");
  const [selectedStock, setSelectedStock] = useState<any>(null);
  const [quantity, setQuantity] = useState("");
  const [avgPrice, setAvgPrice] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editQ, setEditQ] = useState("");
  const [editP, setEditP] = useState("");
  const debouncedQ = useDebounce(query, 300);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["portfolio"],
    queryFn: () => portfolioApi.list().then((r) => r.data),
  });

  const { data: analysis, isFetching: analyzing, error: analysisError, dataUpdatedAt } = useQuery({
    queryKey: ["portfolio-analysis"],
    queryFn: () => portfolioApi.analysis().then((r) => r.data),
    enabled: (items as any[]).length > 0,
    staleTime: 60_000,  // 저장된 이전 값은 바로 보여주고, 1분 지났으면 뒤에서 최신 값을 받아 바꿈
  });

  const { data: searchResults = [], isFetching: searching } = useQuery({
    queryKey: ["stock-search", debouncedQ, marketFilter],
    queryFn: () => stockApi.search(debouncedQ, marketFilter).then((r) => r.data),
    enabled: debouncedQ.length >= 1 && !selectedStock,
  });

  const addMutation = useMutation({
    mutationFn: (item: any) =>
      portfolioApi.add(item.symbol, item.market, item.name, parseFloat(item.qty), parseFloat(item.price)),
    meta: { inlineError: true },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      qc.invalidateQueries({ queryKey: ["portfolio-analysis"] });
      closeModal();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, q, p }: { id: number; q: number; p: number }) =>
      portfolioApi.update(id, q, p),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      qc.invalidateQueries({ queryKey: ["portfolio-analysis"] });
      setEditId(null);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: number) => portfolioApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      qc.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  useEffect(() => {
    if (!showAdd) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeModal(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showAdd]);

  function openModal() {
    setShowAdd(true);
    setQuery("");
    setSelectedStock(null);
    setQuantity("");
    setAvgPrice("");
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function closeModal() {
    setShowAdd(false);
    setQuery("");
    setSelectedStock(null);
    setQuantity("");
    setAvgPrice("");
  }

  function handleSelectStock(item: any) {
    setSelectedStock(item);
    setQuery(item.name);
  }

  function handleAdd() {
    if (!selectedStock || !(parseFloat(quantity) > 0)) return;
    addMutation.mutate({ ...selectedStock, qty: quantity, price: avgPrice || "0" });
  }

  // Merge base list with analysis data (id 기준)
  const portfolioSymbols = new Set((items as any[]).map((i: any) => i.symbol));
  const analysisMap = new Map(((analysis?.items || []) as any[]).map((a: any) => [a.id, a]));

  const enriched = (items as any[]).map((item: any) => ({
    ...item,
    ...(analysisMap.get(item.id) || {}),
  }));

  const totals = analysis?.totals;
  const combined = analysis?.combined_krw;
  const hasKR = enriched.some((i) => i.market === "KR");
  const hasUS = enriched.some((i) => i.market === "US");

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>투자종목</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>보유 종목별 수익/손실 · 다음 거래일 전망</p>
          {(items as any[]).length > 0 && (
            <FetchStatus updatedAt={analysis?.updated_at || dataUpdatedAt} fetching={analyzing}
                         error={analysis && analysisError ? errMsg(analysisError) : null} />
          )}
        </div>
        <button className="btn btn-primary" onClick={openModal}>
          <Plus size={14} />
          종목 추가
        </button>
      </div>

      {/* 종합 수익 카드: 국내(원) / 미국(달러) / 총합(원화 환산) */}
      {enriched.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginBottom: 24 }}>
          {hasKR && <SummaryCard title="🇰🇷 국내 (원)" t={totals?.KRW} cur="KRW" loading={analyzing && !totals} />}
          {hasUS && <SummaryCard title="🇺🇸 미국 (달러)" t={totals?.USD} cur="USD" loading={analyzing && !totals} />}
          <div className="card" style={{ borderColor: "color-mix(in srgb, var(--accent) 40%, transparent)" }}>
            <p style={{ fontWeight: 700, fontSize: 13, marginBottom: 10 }}>
              총합 (원화 환산)
              {analysis?.usdkrw && (
                <span style={{ fontWeight: 400, fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>
                  환율 $1 = ₩{analysis.usdkrw.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </span>
              )}
            </p>
            {analysis?.fx_error ? (
              <p style={{ color: "var(--red)", fontSize: 12 }}>환율 조회 실패 — 원화 환산 불가: {analysis.fx_error}</p>
            ) : combined ? (
              <SummaryRows invested={combined.invested} value={combined.value} pnl={combined.pnl} pnlPct={combined.pnl_pct} day={combined.day_pnl} cur="KRW" />
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{analyzing ? "계산 중..." : "-"}</p>
            )}
          </div>
        </div>
      )}
      {analysisError && (
        <p style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }}>시세 조회 실패{analysis ? " (이전 값 표시 중)" : ""}: {errMsg(analysisError)}</p>
      )}

      {/* Add Modal */}
      {showAdd && (
        <div
          style={{ position: "fixed", inset: 0, background: "var(--overlay)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
          onClick={(e) => e.target === e.currentTarget && closeModal()}
        >
          <div className="card" style={{ width: 460, maxHeight: "85vh", display: "flex", flexDirection: "column", position: "relative" }}>
            <button onClick={closeModal} style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
              <X size={18} />
            </button>
            <h3 style={{ fontWeight: 700, marginBottom: 16 }}>투자종목 추가</h3>

            {/* 종목 검색 */}
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <div style={{ flex: 1, position: "relative" }}>
                <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)", pointerEvents: "none" }} />
                <input
                  ref={inputRef}
                  placeholder="종목명 또는 코드 검색"
                  value={query}
                  onChange={(e) => { setQuery(e.target.value); setSelectedStock(null); }}
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

            {/* 검색 결과 */}
            {!selectedStock && (
              <div style={{ flex: 1, overflowY: "auto", minHeight: 0, maxHeight: 200, marginBottom: 12 }}>
                {debouncedQ.length === 0 ? (
                  <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: "16px 0" }}>종목명 또는 코드를 입력하세요</p>
                ) : searching ? (
                  <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: "16px 0" }}>검색 중...</p>
                ) : (searchResults as any[]).length === 0 ? (
                  <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: "16px 0" }}>검색 결과 없음</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    {(searchResults as any[]).filter((s) => !portfolioSymbols.has(s.symbol)).map((item: any) => (
                      <div
                        key={`${item.market}-${item.symbol}`}
                        onClick={() => handleSelectStock(item)}
                        style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", borderRadius: 7, background: "var(--bg-secondary)", cursor: "pointer" }}
                        onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--bg-hover)")}
                        onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--bg-secondary)")}
                      >
                        <div style={{ flex: 1 }}>
                          <span style={{ fontWeight: 600, fontSize: 14 }}>{item.name}</span>
                          <span style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, background: item.market === "KR" ? "color-mix(in srgb, var(--accent) 15%, transparent)" : "color-mix(in srgb, var(--green) 15%, transparent)", color: item.market === "KR" ? "var(--accent)" : "var(--green)", marginLeft: 8 }}>{item.market}</span>
                        </div>
                        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{item.symbol}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 선택된 종목 + 수량/단가 입력 */}
            {selectedStock && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: 8, background: "color-mix(in srgb, var(--accent) 10%, transparent)", marginBottom: 14 }}>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontWeight: 600 }}>{selectedStock.name}</span>
                    <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 8 }}>{selectedStock.symbol} · {selectedStock.market}</span>
                  </div>
                  <button onClick={() => setSelectedStock(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
                    <X size={14} />
                  </button>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <div>
                    <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>보유 수량</label>
                    <input
                      type="number"
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                      placeholder="0"
                      style={{ width: "100%", padding: "9px 12px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none", boxSizing: "border-box" }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>평균 매수가</label>
                    <input
                      type="number"
                      value={avgPrice}
                      onChange={(e) => setAvgPrice(e.target.value)}
                      placeholder="0"
                      style={{ width: "100%", padding: "9px 12px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none", boxSizing: "border-box" }}
                    />
                  </div>
                </div>
              </div>
            )}

            {addMutation.error && (
              <p style={{ color: "var(--red)", fontSize: 12, marginBottom: 8 }}>{errMsg(addMutation.error)}</p>
            )}
            {selectedStock && (
              <button
                className="btn btn-primary"
                onClick={handleAdd}
                disabled={!(parseFloat(quantity) > 0) || addMutation.isPending}
                style={{ width: "100%" }}
              >
                {addMutation.isPending ? "추가 중..." : "추가하기"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* 목록 */}
      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : enriched.length === 0 ? (
        <div style={{ textAlign: "center", paddingTop: 60 }}>
          <Briefcase size={40} style={{ color: "var(--border)", margin: "0 auto 12px" }} />
          <p style={{ color: "var(--text-muted)" }}>투자 중인 종목을 추가해보세요</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {analyzing && !analysis && (
            <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: "8px 0" }}>
              예측 분석 중...
            </p>
          )}
          {enriched.map((item: any) => {
            const isEditing = editId === item.id;
            const pred = item.prediction || {};
            const isKR = item.market === "KR";
            const pnlColor = (item.pnl_pct || 0) >= 0 ? "var(--green)" : "var(--red)";

            return (
              <div key={item.id} className="card" style={{ padding: "14px 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                  {/* 종목 헤더 */}
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                      <span style={{ fontWeight: 700, fontSize: 15 }}>{item.name || item.symbol}</span>
                      <span className="badge badge-neutral">{item.symbol}</span>
                      <span className="badge badge-neutral">{isKR ? "국내" : "미국"}</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 13, color: "var(--text-secondary)", flexWrap: "wrap" }}>
                      <span>
                        현재가: <strong style={{ color: "var(--text-primary)" }}>
                          {item.current_price > 0
                            ? (isKR ? `₩${item.current_price.toLocaleString()}` : `$${item.current_price.toFixed(2)}`)
                            : "-"}
                        </strong>
                        {" "}<PriceSource src={item.price_source} />
                      </span>
                      {item.change_rate !== undefined && item.change_rate !== 0 && (
                        <ChangeTag value={item.change_rate} />
                      )}
                      <DaytimePrice d={item.daytime} />
                    </div>
                  </div>

                  <button
                    className="btn btn-ghost"
                    style={{ padding: "5px 8px", color: "var(--red)" }}
                    onClick={() => { if (window.confirm(`${item.name || item.symbol} 을(를) 투자종목에서 삭제할까요? (수량·평단가도 지워짐)`)) removeMutation.mutate(item.id); }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                {item.warning && (
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-start", background: "color-mix(in srgb, var(--red) 8%, transparent)", border: "1px solid color-mix(in srgb, var(--red) 30%, transparent)", borderRadius: 7, padding: "8px 10px", marginBottom: 10, fontSize: 12, color: "var(--red)" }}>
                    <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                    {item.warning}
                  </div>
                )}
                {item.error && (
                  <p style={{ color: "var(--red)", fontSize: 12, marginBottom: 10 }}>시세 조회 실패: {item.error}</p>
                )}

                {/* 보유 정보 + 수익 */}
                {/* 넓으면 5칸 한 줄, 휴대폰은 3칸씩 (예전엔 5칸 고정이라 오른쪽이 잘렸음) */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(96px, 1fr))", gap: 8, marginBottom: 12 }}>
                  <div style={{ background: "var(--bg-secondary)", borderRadius: 7, padding: "8px 12px" }}>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>수량</p>
                    {isEditing ? (
                      <input
                        type="number"
                        value={editQ}
                        onChange={(e) => setEditQ(e.target.value)}
                        style={{ width: "100%", padding: "2px 6px", background: "var(--bg-primary)", border: "1px solid var(--accent)", borderRadius: 4, color: "var(--text-primary)", fontSize: 13, outline: "none" }}
                      />
                    ) : (
                      <p style={{ fontWeight: 600, fontSize: 14 }}>{item.quantity}</p>
                    )}
                  </div>
                  <div style={{ background: "var(--bg-secondary)", borderRadius: 7, padding: "8px 12px" }}>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>평단가</p>
                    {isEditing ? (
                      <input
                        type="number"
                        value={editP}
                        onChange={(e) => setEditP(e.target.value)}
                        style={{ width: "100%", padding: "2px 6px", background: "var(--bg-primary)", border: "1px solid var(--accent)", borderRadius: 4, color: "var(--text-primary)", fontSize: 13, outline: "none" }}
                      />
                    ) : (
                      <p style={{ fontWeight: 600, fontSize: 14 }}>
                        {isKR ? `₩${(item.avg_price || 0).toLocaleString()}` : `$${(item.avg_price || 0).toFixed(2)}`}
                      </p>
                    )}
                  </div>
                  <div style={{ background: item.pnl_pct >= 0 ? "color-mix(in srgb, var(--green) 7%, transparent)" : "color-mix(in srgb, var(--red) 7%, transparent)", borderRadius: 7, padding: "8px 12px" }}>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>수익률</p>
                    <p style={{ fontWeight: 700, fontSize: 14, color: pnlColor }}>
                      {(item.pnl_pct || 0) >= 0 ? "+" : ""}{(item.pnl_pct || 0).toFixed(2)}%
                    </p>
                  </div>
                  <div style={{ background: item.pnl_amount >= 0 ? "color-mix(in srgb, var(--green) 7%, transparent)" : "color-mix(in srgb, var(--red) 7%, transparent)", borderRadius: 7, padding: "8px 12px" }}>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>평가손익</p>
                    <p style={{ fontWeight: 700, fontSize: 13, color: pnlColor }}>
                      {(item.pnl_amount || 0) >= 0 ? "+" : ""}
                      {isKR
                        ? `₩${Math.abs(item.pnl_amount || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                        : `$${Math.abs(item.pnl_amount || 0).toFixed(2)}`}
                    </p>
                  </div>
                  <div style={{ background: "var(--bg-secondary)", borderRadius: 7, padding: "8px 12px" }}>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>오늘 손익 · 비중</p>
                    <p style={{ fontWeight: 600, fontSize: 13, color: (item.day_pnl || 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                      {item.day_pnl !== undefined
                        ? `${item.day_pnl >= 0 ? "+" : "-"}${isKR ? "₩" + Math.round(Math.abs(item.day_pnl)).toLocaleString() : "$" + Math.abs(item.day_pnl).toFixed(2)}`
                        : "-"}
                      {item.weight !== undefined && (
                        <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 11, marginLeft: 6 }}>{item.weight}%</span>
                      )}
                    </p>
</div>
                </div>

                {/* 예측 + 수정 버튼 */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 12 }}>
                  <div style={{ flex: 1, maxWidth: 560 }}>
                    {pred.probability ? (
                      <div>
                        <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>{sessionLabel(pred)} 전망</p>
                        <ProbBadge value={pred.probability} />
                        {pred.signal && (
                          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>
                            {pred.signal} · {pred.confidence} 신뢰도
                          </p>
                        )}
                        <BuyPrice pred={pred} market={item.market} compact label="추가 매수 추천가" />
                        <PredictionReasons pred={pred} />
                      </div>
                    ) : (
                      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>분석 데이터 없음</p>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    {isEditing ? (
                      <>
                        <button
                          className="btn btn-primary"
                          style={{ padding: "5px 12px", fontSize: 12 }}
                          disabled={!(parseFloat(editQ) > 0) || !(parseFloat(editP || "0") >= 0) || updateMutation.isPending}
                          title={!(parseFloat(editQ) > 0) ? "수량은 0보다 커야 합니다" : undefined}
                          onClick={() => updateMutation.mutate({ id: item.id, q: parseFloat(editQ), p: parseFloat(editP || "0") })}
                        >
                          <Check size={13} />
                          저장
                        </button>
                        <button className="btn btn-ghost" style={{ padding: "5px 10px" }} onClick={() => setEditId(null)}>
                          <X size={13} />
                        </button>
                      </>
                    ) : (
                      <button
                        className="btn btn-ghost"
                        style={{ padding: "5px 10px", fontSize: 12 }}
                        onClick={() => { setEditId(item.id); setEditQ(String(item.quantity)); setEditP(String(item.avg_price)); }}
                      >
                        <Edit2 size={13} />
                        수정
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function money(v: number, cur: "KRW" | "USD", signed = false): string {
  const sign = signed ? (v >= 0 ? "+" : "-") : v < 0 ? "-" : "";
  const abs = Math.abs(v);
  return cur === "KRW"
    ? `${sign}₩${Math.round(abs).toLocaleString()}`
    : `${sign}$${abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function SummaryRows({ invested, value, pnl, pnlPct, day, cur }: { invested: number; value: number; pnl: number; pnlPct: number; day?: number; cur: "KRW" | "USD" }) {
  const color = pnl >= 0 ? "var(--green)" : "var(--red)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ color: "var(--text-muted)" }}>투자금액</span>
        <span style={{ fontWeight: 600 }}>{money(invested, cur)}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ color: "var(--text-muted)" }}>평가금액</span>
        <span style={{ fontWeight: 600 }}>{money(value, cur)}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ color: "var(--text-muted)" }}>총 수익/손실</span>
        <span style={{ fontWeight: 700, color }}>
          {money(pnl, cur, true)} ({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%)
        </span>
      </div>
      {day !== undefined && day !== null && (
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "var(--text-muted)" }}>오늘 손익</span>
          <span style={{ fontWeight: 600, color: day >= 0 ? "var(--green)" : "var(--red)" }}>{money(day, cur, true)}</span>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ title, t, cur, loading }: { title: string; t: any; cur: "KRW" | "USD"; loading: boolean }) {
  return (
    <div className="card">
      <p style={{ fontWeight: 700, fontSize: 13, marginBottom: 10 }}>{title}</p>
      {t ? (
        <SummaryRows invested={t.invested} value={t.value} pnl={t.pnl} pnlPct={t.pnl_pct} day={t.day_pnl} cur={cur} />
      ) : (
        <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{loading ? "계산 중..." : "-"}</p>
      )}
    </div>
  );
}
