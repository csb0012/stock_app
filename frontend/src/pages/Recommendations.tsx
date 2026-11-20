import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { stockApi } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import { TrendingUp, Zap, AlertTriangle } from "lucide-react";

function ProbabilityBar({ value }: { value: number }) {
  const color = value >= 65 ? "var(--green)" : value >= 45 ? "var(--yellow)" : "var(--red)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "var(--bg-secondary)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${value}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.6s" }} />
      </div>
      <span style={{ fontSize: 13, fontWeight: 700, color, minWidth: 36 }}>{value}%</span>
    </div>
  );
}

function StockCard({ item, type }: { item: any; type: "long" | "short" }) {
  const pred = item.prediction || {};
  const isKR = item.market === "KR";

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
            <span style={{ fontWeight: 700, fontSize: 15 }}>{item.name || item.symbol}</span>
            <span className="badge badge-neutral">{item.symbol}</span>
            <span className="badge badge-neutral">{isKR ? "국내" : "미국"}</span>
          </div>
          <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
            {isKR ? `₩${(item.price || 0).toLocaleString()}` : `$${(item.price || 0).toFixed(2)}`}
          </span>
        </div>
        {item.change_rate !== undefined && <ChangeTag value={item.change_rate} />}
      </div>

      {/* 내일 상승 확률 */}
      <div>
        <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>내일 상승 확률</p>
        <ProbabilityBar value={pred.probability || 50} />
        {pred.signal && (
          <span style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4, display: "block" }}>
            {pred.signal} · 신뢰도 {pred.confidence}
          </span>
        )}
      </div>

      {/* 목표가 / 손절가 */}
      {pred.target_price && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div style={{ background: "rgba(52, 211, 153, 0.07)", borderRadius: 7, padding: "8px 12px" }}>
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>목표가 (익절)</p>
            <p style={{ fontWeight: 700, color: "var(--green)", fontSize: 14 }}>
              {isKR ? `₩${pred.target_price.toLocaleString()}` : `$${pred.target_price.toFixed(2)}`}
            </p>
          </div>
          <div style={{ background: "rgba(248, 113, 113, 0.07)", borderRadius: 7, padding: "8px 12px" }}>
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>손절가</p>
            <p style={{ fontWeight: 700, color: "var(--red)", fontSize: 14 }}>
              {isKR ? `₩${pred.stop_loss?.toLocaleString()}` : `$${pred.stop_loss?.toFixed(2)}`}
            </p>
          </div>
        </div>
      )}

      {/* 근거 */}
      {pred.reasons && pred.reasons.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>분석 근거</p>
          <ul style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {pred.reasons.map((r: string, i: number) => (
              <li key={i} style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", gap: 6 }}>
                <span style={{ color: "var(--accent)", flexShrink: 0 }}>•</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 장기 점수 */}
      {type === "long" && item.long_term_score > 0 && (
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-muted)" }}>
          <span>장기 적합도 {item.long_term_score}/100</span>
          {item.per > 0 && <span>PER {item.per.toFixed(1)} | PBR {item.pbr?.toFixed(1)}</span>}
          {item.trend_6m !== undefined && (
            <span style={{ color: item.trend_6m >= 0 ? "var(--green)" : "var(--red)" }}>
              6개월 {item.trend_6m >= 0 ? "+" : ""}{item.trend_6m?.toFixed(1)}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default function Recommendations() {
  const [tab, setTab] = useState<"long" | "short">("long");

  const longQuery = useQuery({
    queryKey: ["longterm"],
    queryFn: () => stockApi.longterm().then((r) => r.data),
    enabled: tab === "long",
    staleTime: 5 * 60 * 1000,
  });

  const shortQuery = useQuery({
    queryKey: ["shortterm"],
    queryFn: () => stockApi.shortterm().then((r) => r.data),
    enabled: tab === "short",
    staleTime: 60 * 1000,
  });

  const query = tab === "long" ? longQuery : shortQuery;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>AI 주식 추천</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>기술적 분석 기반 추천 · 투자 손실에 대한 책임은 본인에게 있습니다</p>
      </div>

      {/* Disclaimer */}
      <div className="card" style={{ display: "flex", gap: 10, alignItems: "flex-start", marginBottom: 20, borderColor: "rgba(251,191,36,0.3)", background: "rgba(251,191,36,0.04)" }}>
        <AlertTriangle size={15} style={{ color: "var(--yellow)", flexShrink: 0, marginTop: 1 }} />
        <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          이 추천은 RSI·MACD·볼린저밴드 등 기술적 지표를 기반으로 하며, 미래 수익을 보장하지 않습니다.
          소액 분산 투자를 권장하며, 최종 투자 판단은 본인이 하세요.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        <button className={`btn ${tab === "long" ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab("long")}>
          <TrendingUp size={14} />
          장기투자 추천
        </button>
        <button className={`btn ${tab === "short" ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab("short")}>
          <Zap size={14} />
          단기/스윙 추천
        </button>
      </div>

      {query.isLoading && (
        <div style={{ color: "var(--text-muted)", textAlign: "center", paddingTop: 60 }}>분석 중...</div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: 16 }}>
        {(query.data || []).map((item: any) => (
          <StockCard key={`${item.market}-${item.symbol}`} item={item} type={tab} />
        ))}
      </div>
    </div>
  );
}
