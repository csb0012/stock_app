import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { stockApi, watchlistApi, errMsg } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import StockSearchBox from "../components/common/StockSearchBox";
import StockQuoteCard from "../components/common/StockQuoteCard";
import { TrendingUp, TrendingDown, Star, Check, Flame, ArrowDownRight, BarChart3, Activity } from "lucide-react";

type Market = "KR" | "US";
type Mode = "volume_surge" | "trading_value" | "gainers" | "losers";

const PAGE = 20;

const MODES: { key: Mode; label: string; icon: any; desc: string }[] = [
  { key: "volume_surge",   label: "거래량 급증", icon: Activity,       desc: "평균 대비 거래량 폭증 종목" },
  { key: "trading_value",  label: "거래대금",    icon: BarChart3,       desc: "오늘 거래대금 상위 종목" },
  { key: "gainers",        label: "급등",        icon: Flame,           desc: "오늘 상승률 상위 종목" },
  { key: "losers",         label: "급하향",      icon: ArrowDownRight,  desc: "오늘 하락률 상위 종목" },
];

export default function Screener() {
  const qc = useQueryClient();
  const [market, setMarket] = useState<Market>("KR");
  const [mode, setMode] = useState<Mode>("volume_surge");
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [shown, setShown] = useState(PAGE);
  const [picked, setPicked] = useState<any>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["screener", market, mode],
    queryFn: () =>
      market === "KR"
        ? stockApi.screenerKR(mode).then((r) => r.data)
        : stockApi.screenerUS(mode).then((r) => r.data),
    refetchInterval: 60_000,
  });

  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list().then((r) => r.data),
  });

  const watchlistSymbols = new Set((watchlist as any[]).map((w: any) => w.symbol));

  const addMutation = useMutation({
    mutationFn: (item: any) => watchlistApi.add(item.symbol, item.market || market, item.name),
    onSuccess: (_, item) => {
      setAdded((prev) => new Set(prev).add(item.symbol));
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const modeInfo = MODES.find((m) => m.key === mode)!;
  const allRows = (data || []) as any[];
  const rows = allRows.slice(0, shown);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>종목 탐색</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>국내 · 미국 시장 실시간 스크리너 (1분 갱신) · 국내: KIS 순위 · 미국: Yahoo 전체 시장</p>
      </div>

      {/* 종목 검색 */}
      <div style={{ marginBottom: 16 }}>
        <StockSearchBox onSelect={(item) => setPicked(item)} />
      </div>
      {picked && (
        <StockQuoteCard
          item={picked}
          onClose={() => setPicked(null)}
          actions={(() => {
            const inList = watchlistSymbols.has(picked.symbol) || added.has(picked.symbol);
            return (
              <button
                className={`btn ${inList ? "btn-ghost" : "btn-primary"}`}
                disabled={inList || addMutation.isPending}
                onClick={() => addMutation.mutate(picked)}
                style={{ padding: "6px 12px", fontSize: 12 }}
              >
                {inList ? <Check size={13} /> : <Star size={13} />}
                {inList ? "관심종목에 있음" : "관심종목 추가"}
              </button>
            );
          })()}
        />
      )}

      {/* 국장 / 미장 탭 */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {(["KR", "US"] as Market[]).map((m) => (
          <button
            key={m}
            className={`btn ${market === m ? "btn-primary" : "btn-ghost"}`}
            style={{ minWidth: 80 }}
            onClick={() => { setMarket(m); setShown(PAGE); }}
          >
            {m === "KR" ? "🇰🇷 국내" : "🇺🇸 미국"}
          </button>
        ))}
      </div>

      {/* 스크리너 모드 탭 */}
      <div style={{ display: "flex", gap: 6, marginBottom: 20, flexWrap: "wrap" }}>
        {MODES.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            className={`btn ${mode === key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => { setMode(key); setShown(PAGE); }}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      <p style={{ color: "var(--text-muted)", fontSize: 12, marginBottom: 10 }}>{modeInfo.desc}</p>

      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : error ? (
        <div className="card" style={{ padding: 24, borderColor: "rgba(248,113,113,0.4)" }}>
          <p style={{ color: "var(--red)", fontWeight: 600, marginBottom: 6 }}>스크리너 조회 실패</p>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>{errMsg(error)}</p>
        </div>
      ) : allRows.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <p style={{ color: "var(--text-muted)" }}>조건에 맞는 종목이 없습니다</p>
        </div>
      ) : (
        <>
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {[
                  "종목명",
                  "현재가",
                  "등락률",
                  mode === "trading_value" ? "거래대금" : "거래량",
                  mode === "volume_surge" ? "거래량 증가율" : "",
                  "",
                ].map((h, i) => (
                  <th key={i} style={{ padding: "12px 16px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((item: any, i: number) => {
                const isInWatchlist = watchlistSymbols.has(item.symbol) || added.has(item.symbol);
                const isKR = item.market === "KR" || market === "KR";
                return (
                  <tr
                    key={item.symbol}
                    onClick={() => setPicked({ market: item.market || market, symbol: item.symbol, name: item.name })}
                    style={{ cursor: "pointer", borderBottom: i < rows.length - 1 ? "1px solid var(--border)" : "none" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
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
                      {isKR ? `₩${(item.price || 0).toLocaleString()}` : `$${(item.price || 0).toFixed(2)}`}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <ChangeTag value={item.change_rate} />
                    </td>
                    <td style={{ padding: "12px 16px", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums", fontSize: 13 }}>
                      {mode === "trading_value"
                        ? (item.trading_value_display || "-")
                        : ((item.volume || 0) >= 1_000_000
                            ? `${((item.volume || 0) / 1_000_000).toFixed(1)}M`
                            : `${((item.volume || 0) / 1_000).toFixed(0)}K`)}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      {mode === "volume_surge" && item.volume_ratio !== undefined && (
                        <span style={{
                          color: item.volume_ratio > 500 ? "var(--red)" : item.volume_ratio > 200 ? "var(--yellow)" : "var(--text-secondary)",
                          fontWeight: 600, fontSize: 13,
                        }}>
                          {item.volume_ratio.toFixed(0)}%
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <button
                        onClick={(e) => { e.stopPropagation(); if (!isInWatchlist) addMutation.mutate(item); }}
                        disabled={isInWatchlist}
                        style={{
                          display: "flex", alignItems: "center", gap: 4,
                          padding: "5px 10px", borderRadius: 6, border: "none", cursor: isInWatchlist ? "default" : "pointer",
                          background: isInWatchlist ? "rgba(52,211,153,0.1)" : "rgba(79,142,247,0.1)",
                          color: isInWatchlist ? "var(--green)" : "var(--accent)",
                          fontSize: 12, fontWeight: 500, transition: "all 0.15s", whiteSpace: "nowrap",
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
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12, marginTop: 14 }}>
          <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{rows.length} / {allRows.length}종목</span>
          {shown < allRows.length && (
            <button className="btn btn-ghost" onClick={() => setShown(shown + PAGE)}>
              더보기 (+{Math.min(PAGE, allRows.length - shown)})
            </button>
          )}
        </div>
        </>
      )}
    </div>
  );
}
