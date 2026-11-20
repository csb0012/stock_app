import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { watchlistApi, stockApi } from "../api/client";
import { Star, Plus, Trash2, X, Search } from "lucide-react";

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

  const watchlistSymbols = new Set((watchlist as any[]).map((w: any) => w.symbol));

  const addMutation = useMutation({
    mutationFn: (item: any) => watchlistApi.add(item.symbol, item.market, item.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  const removeMutation = useMutation({
    mutationFn: (id: number) => watchlistApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

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
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>관심 있는 종목을 모아보세요</p>
        </div>
        <button className="btn btn-primary" onClick={openModal}>
          <Plus size={14} />
          종목 추가
        </button>
      </div>

      {/* Add Modal */}
      {showAdd && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
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
                        key={item.symbol}
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
                            <span style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, background: item.market === "KR" ? "rgba(79,142,247,0.15)" : "rgba(52,211,153,0.15)", color: item.market === "KR" ? "var(--accent)" : "var(--green)" }}>
                              {item.market}
                            </span>
                            {item.type === "etf" && (
                              <span style={{ fontSize: 10, padding: "2px 5px", borderRadius: 4, background: "rgba(251,191,36,0.15)", color: "var(--yellow)" }}>ETF</span>
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
                            color: inList ? "var(--text-muted)" : "#fff",
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
      ) : (watchlist as any[]).length === 0 ? (
        <div style={{ textAlign: "center", paddingTop: 60 }}>
          <Star size={40} style={{ color: "var(--border)", margin: "0 auto 12px" }} />
          <p style={{ color: "var(--text-muted)" }}>관심종목을 추가해보세요</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {(watchlist as any[]).map((item: any) => (
            <div key={item.id} className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <Star size={16} style={{ color: "var(--yellow)" }} />
                <div>
                  <p style={{ fontWeight: 600, fontSize: 14 }}>{item.name || item.symbol}</p>
                  <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{item.symbol} · {item.market === "KR" ? "국내" : "미국"}</p>
                </div>
              </div>
              <button
                className="btn btn-ghost"
                style={{ padding: "6px 10px", color: "var(--red)" }}
                onClick={() => removeMutation.mutate(item.id)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
