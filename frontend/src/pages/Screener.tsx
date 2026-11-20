import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { stockApi, watchlistApi } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import { TrendingUp, TrendingDown, Star, Check } from "lucide-react";

export default function Screener() {
  const qc = useQueryClient();
  const [added, setAdded] = useState<Set<string>>(new Set());

  const { data, isLoading } = useQuery({
    queryKey: ["volume-surge"],
    queryFn: () => stockApi.volumeSurge().then((r) => r.data),
    refetchInterval: 60_000,
  });

  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list().then((r) => r.data),
  });

  const watchlistSymbols = new Set((watchlist as any[]).map((w: any) => w.symbol));

  const addMutation = useMutation({
    mutationFn: (item: any) => watchlistApi.add(item.symbol, "KR", item.name),
    onSuccess: (_, item) => {
      setAdded((prev) => new Set(prev).add(item.symbol));
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>종목 탐색</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>거래량 급증 · 국내 시장 (1분 갱신)</p>
      </div>

      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : (data || []).length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <p style={{ color: "var(--text-muted)" }}>데이터 없음 — KIS API 연결을 확인하세요</p>
          <p style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 8 }}>
            브라우저 주소창에 <code style={{ color: "var(--accent)" }}>http://localhost:8000/api/stocks/test/kis</code> 입력해서 연결 상태 확인
          </p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["종목명", "현재가", "등락률", "거래량", "거래량 비율", ""].map((h) => (
                  <th key={h} style={{ padding: "12px 16px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data || []).map((item: any, i: number) => {
                const isInWatchlist = watchlistSymbols.has(item.symbol) || added.has(item.symbol);
                return (
                  <tr key={item.symbol} style={{ borderBottom: i < data.length - 1 ? "1px solid var(--border)" : "none" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                    <td style={{ padding: "12px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        {item.change_rate >= 0
                          ? <TrendingUp size={14} style={{ color: "var(--green)" }} />
                          : <TrendingDown size={14} style={{ color: "var(--red)" }} />}
                        <div>
                          <p style={{ fontWeight: 600, fontSize: 13 }}>{item.name}</p>
                          <p style={{ color: "var(--text-muted)", fontSize: 11 }}>{item.symbol}</p>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: "12px 16px", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                      ₩{item.price.toLocaleString()}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <ChangeTag value={item.change_rate} />
                    </td>
                    <td style={{ padding: "12px 16px", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                      {(item.volume / 1000).toFixed(0)}K
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <span style={{ color: item.volume_ratio > 500 ? "var(--red)" : item.volume_ratio > 200 ? "var(--yellow)" : "var(--text-secondary)", fontWeight: 600 }}>
                        {item.volume_ratio.toFixed(0)}%
                      </span>
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <button
                        onClick={() => !isInWatchlist && addMutation.mutate(item)}
                        disabled={isInWatchlist}
                        style={{
                          display: "flex", alignItems: "center", gap: 4,
                          padding: "5px 10px", borderRadius: 6, border: "none", cursor: isInWatchlist ? "default" : "pointer",
                          background: isInWatchlist ? "rgba(52,211,153,0.1)" : "rgba(79,142,247,0.1)",
                          color: isInWatchlist ? "var(--green)" : "var(--accent)",
                          fontSize: 12, fontWeight: 500, transition: "all 0.15s",
                        }}
                      >
                        {isInWatchlist ? <Check size={13} /> : <Star size={13} />}
                        {isInWatchlist ? "추가됨" : "관심"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
