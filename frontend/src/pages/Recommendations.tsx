import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { stockApi, watchlistApi, errMsg } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import PredictionReasons from "../components/common/PredictionReasons";
import BuyPrice from "../components/common/BuyPrice";
import { TrendingUp, Zap, AlertTriangle, RefreshCw, Newspaper, Star, Check } from "lucide-react";
import { sessionLabel, fmtPrice } from "../components/common/format";

function Delta({ now, prev }: { now: number; prev?: number | null }) {
  if (prev === undefined || prev === null || prev === now) return null;
  const d = now - prev;
  return (
    <span style={{ fontSize: 11, fontWeight: 700, color: d > 0 ? "var(--green)" : "var(--red)", marginLeft: 6 }}>
      {d > 0 ? "▲" : "▼"}{Math.abs(d)}%p
    </span>
  );
}

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

function WatchButton({ item, inList }: { item: any; inList: boolean }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => watchlistApi.add(item.symbol, item.market, item.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  const done = inList || m.isSuccess;
  return (
    <button
      title={m.error ? errMsg(m.error) : done ? "관심종목에 있음" : "관심종목 추가"}
      disabled={done || m.isPending}
      onClick={() => m.mutate()}
      style={{ display: "flex", alignItems: "center", gap: 3, padding: "3px 8px", borderRadius: 6, border: "none", cursor: done ? "default" : "pointer",
        background: m.error ? "color-mix(in srgb, var(--red) 10%, transparent)" : done ? "color-mix(in srgb, var(--green) 10%, transparent)" : "color-mix(in srgb, var(--accent) 10%, transparent)",
        color: m.error ? "var(--red)" : done ? "var(--green)" : "var(--accent)", fontSize: 11 }}
    >
      {done ? <Check size={12} /> : <Star size={12} />}
      {m.error ? "실패" : done ? "관심" : "관심+"}
    </button>
  );
}

function StockCard({ item, type, inWatchlist }: { item: any; type: "long" | "short"; inWatchlist: boolean }) {
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
            {fmtPrice(item.price, item.market)}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <WatchButton item={item} inList={inWatchlist} />
          {item.change_rate !== undefined && <ChangeTag value={item.change_rate} />}
        </div>
      </div>

      {/* 다음 거래일 상승 확률 */}
      <div>
        <p style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
          <span>
            {sessionLabel(pred)} 상승 확률
            <Delta now={pred.probability} prev={item.prev_probability} />
          </span>
          <span>
            하락 확률 <strong style={{ color: "var(--red)" }}>{100 - (pred.probability || 50)}%</strong>
          </span>
        </p>
        <ProbabilityBar value={pred.probability || 50} />
        {pred.signal && (
          <span style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4, display: "block" }}>
            {pred.signal} · 신뢰도 {pred.confidence}
          </span>
        )}
      </div>

      {/* 추천 매입가 / 목표가 / 손절가 */}
      {pred.target_price && (
        <>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
          <BuyPrice pred={pred} market={item.market} />
          <div style={{ background: "color-mix(in srgb, var(--green) 7%, transparent)", borderRadius: 7, padding: "8px 10px" }}>
            <p style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>목표가 (익절)</p>
            <p style={{ fontWeight: 700, color: "var(--green)", fontSize: 13 }}>
              {isKR ? `₩${Math.round(pred.target_price).toLocaleString()}` : `$${pred.target_price.toFixed(2)}`}
            </p>
          </div>
          <div style={{ background: "color-mix(in srgb, var(--red) 7%, transparent)", borderRadius: 7, padding: "8px 10px" }}>
            <p style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>손절가</p>
            <p style={{ fontWeight: 700, color: "var(--red)", fontSize: 13 }}>
              {isKR ? `₩${Math.round(pred.stop_loss || 0).toLocaleString()}` : `$${(pred.stop_loss || 0).toFixed(2)}`}
            </p>
          </div>
        </div>
        {(pred.buy_comment || pred.entry_comment) && (
          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: -6 }}>
            💡 {pred.buy_comment || pred.entry_comment}
          </p>
        )}
        </>
      )}

      {/* 근거 */}
      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 2 }}>
        <PredictionReasons pred={pred} />
      </div>

      {/* 최근 뉴스 */}
      {item.news?.headlines?.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          {item.news.headlines.slice(0, 2).map((h: any, i: number) => (
            <div key={i} style={{ display: "flex", gap: 6, fontSize: 11, color: "var(--text-muted)" }}>
              <Newspaper size={11} style={{ flexShrink: 0, marginTop: 2, color: h.tone === "pos" ? "var(--green)" : h.tone === "neg" ? "var(--red)" : "var(--text-muted)" }} />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.title}</span>
            </div>
          ))}
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

type Group = "KR" | "US" | "SPAC" | "ETF";
type Sort = "default" | "prob_desc" | "down_desc";

const GROUPS: { key: Group; label: string; match: (x: any) => boolean }[] = [
  { key: "KR", label: "🇰🇷 국내 주식", match: (x) => x.market === "KR" && x.category === "stock" },
  { key: "US", label: "🇺🇸 미국", match: (x) => x.market === "US" && x.category !== "etf" },
  { key: "SPAC", label: "스팩", match: (x) => x.category === "spac" },
  { key: "ETF", label: "ETF·ETN", match: (x) => x.category === "etf" },
];

const REFRESH_SEC = 15;

export default function Recommendations() {
  const [tab, setTab] = useState<"long" | "short">("long");
  const [group, setGroup] = useState<Group>("KR");
  const [sort, setSort] = useState<Sort>("default");

  // 15초마다 현재가·뉴스로 상승 확률을 다시 계산한 결과를 받아옴
  const longQuery = useQuery({
    queryKey: ["longterm"],
    queryFn: () => stockApi.longterm().then((r) => r.data),
    enabled: tab === "long",
    refetchInterval: REFRESH_SEC * 1000,
    refetchIntervalInBackground: false,
  });

  const shortQuery = useQuery({
    queryKey: ["shortterm"],
    queryFn: () => stockApi.shortterm().then((r) => r.data),
    enabled: tab === "short",
    refetchInterval: REFRESH_SEC * 1000,
    refetchIntervalInBackground: false,
  });

  const query = tab === "long" ? longQuery : shortQuery;
  const { data: watchlist = [] } = useQuery({ queryKey: ["watchlist"], queryFn: () => watchlistApi.list().then((r) => r.data) });
  const watchSet = new Set((watchlist as any[]).map((w) => `${w.market}-${w.symbol}`));
  const all: any[] = query.data?.items || [];
  const g = GROUPS.find((x) => x.key === group)!;
  const errors: any[] = (query.data?.errors || []).filter((e: any) => (group === "US" ? e.market === "US" : e.market === "KR"));

  const prob = (x: any) => x.prediction?.probability ?? 0;
  const items = all
    .filter(g.match)
    .sort((a, b) =>
      sort === "prob_desc" ? prob(b) - prob(a)
      : sort === "down_desc" ? prob(a) - prob(b)
      : tab === "long" ? (b.long_term_score || 0) - (a.long_term_score || 0)
      : prob(b) - prob(a)
    );

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>AI 주식 추천</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          학습 모델·기술적 분석 + 뉴스 분위기 · {REFRESH_SEC}초마다 현재가·뉴스로 확률 재계산 · 투자 손실에 대한 책임은 본인에게 있습니다
        </p>
      </div>

      {/* Disclaimer */}
      <div className="card" style={{ display: "flex", gap: 10, alignItems: "flex-start", marginBottom: 20, borderColor: "color-mix(in srgb, var(--yellow) 30%, transparent)", background: "color-mix(in srgb, var(--yellow) 4%, transparent)" }}>
        <AlertTriangle size={15} style={{ color: "var(--yellow)", flexShrink: 0, marginTop: 1 }} />
        <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          상승 확률은 과거 2년 일봉으로 학습한 모델(백테스트에서 기존 지표 점수보다 잘 맞을 때만 사용, 아니면 RSI·MACD·볼린저·이평 점수)에
          뉴스·외부 데이터를 소폭 반영한 값이며, 미래 수익을 보장하지 않습니다.
          실제 적중률은 사이드바의 "예측 검증"에서 확인할 수 있습니다.
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

      {/* 분류 + 정렬 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {GROUPS.map((x) => (
            <button key={x.key} className={`btn ${group === x.key ? "btn-primary" : "btn-ghost"}`} style={{ minWidth: 80 }} onClick={() => setGroup(x.key)}>
              {x.label} ({all.filter(x.match).length})
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {([
            ["default", tab === "long" ? "장기 적합도순" : "추천순"],
            ["prob_desc", "상승확률 높은 순"],
            ["down_desc", "하락확률 높은 순"],
          ] as [Sort, string][]).map(([k, label]) => (
            <button key={k} className={`btn ${sort === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 12, padding: "6px 10px" }} onClick={() => setSort(k)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {query.data?.updated_at && (
        <p style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text-muted)", fontSize: 12, marginBottom: 14 }}>
          <RefreshCw size={12} className={query.isFetching ? "spin" : undefined} />
          마지막 갱신 {query.data.updated_at} · {REFRESH_SEC}초마다 자동 갱신
          {query.data.live_errors?.length > 0 && (
            <span style={{ color: "var(--yellow)" }}> · 현재가 조회 실패: {query.data.live_errors.join(" / ")}</span>
          )}
        </p>
      )}

      {query.isLoading && (
        <div style={{ color: "var(--text-muted)", textAlign: "center", paddingTop: 60 }}>분석 중... (처음엔 KIS·뉴스를 받느라 10~20초 걸립니다)</div>
      )}
      {query.error && (
        <div className="card" style={{ padding: 20, borderColor: "color-mix(in srgb, var(--red) 40%, transparent)", marginBottom: 16 }}>
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
        <p style={{ color: "var(--text-muted)", textAlign: "center", paddingTop: 40 }}>
          {group === "SPAC" || group === "ETF" ? "오늘 거래량 급증 종목 중 해당 분류가 없습니다 (단기/스윙 탭에서 주로 나옵니다)" : "추천 종목이 없습니다"}
        </p>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: 16 }}>
        {items.map((item: any) => (
          <StockCard key={`${item.market}-${item.symbol}`} item={item} type={tab} inWatchlist={watchSet.has(`${item.market}-${item.symbol}`)} />
        ))}
      </div>
    </div>
  );
}
