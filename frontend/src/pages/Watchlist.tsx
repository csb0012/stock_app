import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { watchlistApi } from "../api/client";
import { Star, Plus, Trash2, X } from "lucide-react";

export default function Watchlist() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ symbol: "", market: "KR", name: "" });

  const { data = [], isLoading } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list().then((r) => r.data),
  });

  const addMutation = useMutation({
    mutationFn: () => watchlistApi.add(form.symbol.toUpperCase(), form.market, form.name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      setShowAdd(false);
      setForm({ symbol: "", market: "KR", name: "" });
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: number) => watchlistApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>관심종목</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>관심 있는 종목을 모아보세요</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
          <Plus size={14} />
          종목 추가
        </button>
      </div>

      {/* Add Modal */}
      {showAdd && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex",
          alignItems: "center", justifyContent: "center", zIndex: 100,
        }}>
          <div className="card" style={{ width: 360, position: "relative" }}>
            <button onClick={() => setShowAdd(false)} style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
              <X size={18} />
            </button>
            <h3 style={{ fontWeight: 700, marginBottom: 16 }}>관심종목 추가</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <input
                placeholder="종목코드 (예: 005930 / AAPL)"
                value={form.symbol}
                onChange={(e) => setForm({ ...form, symbol: e.target.value })}
                style={{ padding: "9px 12px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none" }}
              />
              <input
                placeholder="종목명 (예: 삼성전자)"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                style={{ padding: "9px 12px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none" }}
              />
              <select
                value={form.market}
                onChange={(e) => setForm({ ...form, market: e.target.value })}
                style={{ padding: "9px 12px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none" }}
              >
                <option value="KR">국내 (KR)</option>
                <option value="US">미국 (US)</option>
              </select>
              <button className="btn btn-primary"
                style={{ justifyContent: "center" }}
                disabled={!form.symbol}
                onClick={() => addMutation.mutate()}>
                추가
              </button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : data.length === 0 ? (
        <div style={{ textAlign: "center", paddingTop: 60 }}>
          <Star size={40} style={{ color: "var(--border)", margin: "0 auto 12px" }} />
          <p style={{ color: "var(--text-muted)" }}>관심종목을 추가해보세요</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {data.map((item: any) => (
            <div key={item.id} className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <Star size={16} style={{ color: "var(--yellow)" }} />
                <div>
                  <p style={{ fontWeight: 600, fontSize: 14 }}>{item.name || item.symbol}</p>
                  <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{item.symbol} · {item.market === "KR" ? "국내" : "미국"}</p>
                </div>
              </div>
              <button className="btn btn-ghost" style={{ padding: "6px 10px", color: "var(--red)" }}
                onClick={() => removeMutation.mutate(item.id)}>
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
