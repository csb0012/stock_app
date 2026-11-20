import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { stockApi, errMsg } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import PredictionReasons from "../components/common/PredictionReasons";
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

      {/* 목표가 / 손절가 / 진입 추천가 */}
      {pred.target_price && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
          <div style={{ background: "rgba(52, 211, 153, 0.07)", borderRadius: 7, padding: "8px 10px" }}>
            <p style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>목표가 (익절)</p>
            <p style={{ fontWeight: 700, color: "var(--green)", fontSize: 13 }}>
              {isKR ? `₩${Math.round(pred.target_price).toLocaleString()}` : `$${pred.target_price.toFixed(2)}`}
            </p>
          </div>
          <div style={{ background: "rgba(248, 113, 113, 0.07)", borderRadius: 7, padding: "8px 10px" }}>
            <p style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>손절가</p>
            <p style={{ fontWeight: 700, color: "var(--red)", fontSize: 13 }}>
              {isKR ? `₩${Math.round(pred.stop_loss || 0).toLocaleString()}` : `$${(pred.stop_loss || 0).toFixed(2)}`}
            </p>
          </div>
          {pred.entry_price && (
            <div style={{ background: "rgba(79,142,247,0.07)", borderRadius: 7, padding: "8px 10px" }}>
              <p style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>진입 추천가</p>
              <p style={{ fontWeight: 700, color: "var(--accent)", fontSize: 13 }}>
                {isKR ? `₩${Math.round(pred.entry_price).toLocaleString()}` : `$${pred.entry_price.toFixed(2)}`}
              </p>
              {pred.entry_comment && (
                <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>{pred.entry_comment}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* 근거 */}
      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 2 }}>
        <PredictionReasons pred={pred} />
      </div>

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

type Market = "KR" | "US";
type Sort = "default" | "prob_desc" | "prob_asc";

export default function Recommendations() {
  const [tab, setTab] = useState<"long" | "short">("long");
  const [market, setMarket] = useState<Market>("KR");
  const [sort, setSort] = useState<Sort>("default");

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
  const all: any[] = query.data?.items || [];
  const errors: any[] = (query.data?.errors || []).filter((e: any) => e.market === market);

  const prob = (x: any) => x.prediction?.probability ?? 0;
  const items = all
    .filter((x) => x.market === market)
    .sort((a, b) =>
      sort === "prob_desc" ? prob(b) - prob(a)
      : sort === "prob_asc" ? prob(a) - prob(b)
      : tab === "long" ? (b.long_term_score || 0) - (a.long_term_score || 0)
      : prob(b) - prob(a)
    );

  const countKR = all.filter((x) => x.market === "KR").length;
  const countUS = all.filter((x) => x.market === "US").length;

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

      {/* 장기/단기 탭 */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button className={`btn ${tab === "long" ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab("long")}>
          <TrendingUp size={14} />
          장기투자 추천
        </button>
        <button className={`btn ${tab === "short" ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab("short")}>
          <Zap size={14} />
          단기/스윙 추천
        </button>
      </div>

      {/* 국내/미국 + 정렬 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6 }}>
          {(["KR", "US"] as Market[]).map((m) => (
            <button key={m} className={`btn ${market === m ? "btn-primary" : "btn-ghost"}`} style={{ minWidth: 90 }} onClick={() => setMarket(m)}>
              {m === "KR" ? `🇰🇷 국내 (${countKR})` : `🇺🇸 미국 (${countUS})`}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {([
            ["default", tab === "long" ? "장기 적합도순" : "추천순"],
            ["prob_desc", "상승확률 높은 순"],
            ["prob_asc", "상승확률 낮은 순"],
          ] as [Sort, string][]).map(([k, label]) => (
            <button key={k} className={`btn ${sort === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "6px 10px" }} onClick={() => setSort(k)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {query.isLoading && (
        <div style={{ color: "var(--text-muted)", textAlign: "center", paddingTop: 60 }}>분석 중... (국내 종목은 KIS에서 한 종목씩 받아 10초 정도 걸립니다)</div>
      )}
      {query.error && (
        <div className="card" style={{ padding: 20, borderColor: "rgba(248,113,113,0.4)", marginBottom: 16 }}>
          <p style={{ color: "var(--red)", fontWeight: 600, marginBottom: 6 }}>추천 분석 실패</p>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>{errMsg(query.error)}</p>
        </div>
      )}
      {errors.length > 0 && (
        <p style={{ color: "var(--yellow)", fontSize: 12, marginBottom: 12 }}>
          분석 못한 종목 {errors.length}개: {errors.slice(0, 3).map((e) => `${e.symbol}: ${e.error}`).join(" / ")}{errors.length > 3 ? " …" : ""}
        </p>
      )}
      {query.data && items.length === 0 && (
        <p style={{ color: "var(--text-muted)", textAlign: "center", paddingTop: 40 }}>이 시장의 추천 종목이 없습니다</p>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: 16 }}>
        {items.map((item: any) => (
          <StockCard key={`${item.market}-${item.symbol}`} item={item} type={tab} />
        ))}
      </div>
    </div>
  );
}
