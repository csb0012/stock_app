import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { stockApi, watchlistApi, errMsg } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import { extPrice, SessionTag } from "../components/common/DaytimePrice";
import StockSearchBox from "../components/common/StockSearchBox";
import StockQuoteCard from "../components/common/StockQuoteCard";
import { TrendingUp, TrendingDown, Star, Check, Flame, ArrowDownRight, BarChart3, Activity, RefreshCw } from "lucide-react";

type Market = "KR" | "US";
type Mode = "volume_surge" | "trading_value" | "gainers" | "losers";

const PAGE = 20;
const REFRESH_SEC = 10;

const MODES: { key: Mode; label: string; icon: any; desc: string }[] = [
  { key: "trading_value",  label: "거래대금",    icon: BarChart3,       desc: "오늘 거래대금 상위 종목" },
  { key: "gainers",        label: "급등",        icon: Flame,           desc: "오늘 상승률 상위 종목" },
  { key: "losers",         label: "급하향",      icon: ArrowDownRight,  desc: "오늘 하락률 상위 종목" },
  { key: "volume_surge",   label: "거래량 급증", icon: Activity,       desc: "평균 대비 거래량 폭증 종목" },
];

export default function Screener() {
  const qc = useQueryClient();
  const [market, setMarket] = useState<Market>("KR");
  const [mode, setMode] = useState<Mode>("trading_value");  // 첫 탭 = 거래대금
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [shown, setShown] = useState(PAGE);
  const [picked, setPicked] = useState<any>(null);

  const { data, isLoading, error, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ["screener", market, mode],
    queryFn: () =>
      market === "KR"
        ? stockApi.screenerKR(mode).then((r) => r.data)
        : stockApi.screenerUS(mode).then((r) => r.data),
    refetchInterval: REFRESH_SEC * 1000,
    refetchIntervalInBackground: false,
  });

  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list().then((r) => r.data),
  });

  const watchlistSymbols = new Set((watchlist as any[]).map((w: any) => w.symbol));

  const addMutation = useMutation({
    mutationFn: (item: any) => watchlistApi.add(item.symbol, item.market || market, item.name),
    meta: { inlineError: true },
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
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>종목 검색(상세 분석·관심 추가) + 국내 · 미국 실시간 스크리너 ({REFRESH_SEC}초마다 갱신) · 국내: KIS 순위 · 미국: Yahoo 전체 시장</p>
      </div>

      {/* 종목 검색 */}
      <div style={{ marginBottom: 16 }}>
        <StockSearchBox onSelect={(item) => setPicked(item)} />
      </div>
      {addMutation.error && (
        <p style={{ color: "var(--red)", fontSize: 12, marginBottom: 10 }}>관심종목 추가 실패: {errMsg(addMutation.error)}</p>
      )}
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

      <p style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text-muted)", fontSize: 12, marginBottom: 10 }}>
        {modeInfo.desc}
        {dataUpdatedAt > 0 && (
          <>
            <span>·</span>
            <RefreshCw size={12} className={isFetching ? "spin" : undefined} />
            마지막 갱신 {new Date(dataUpdatedAt).toLocaleTimeString("ko-KR", { hour12: false })} · {REFRESH_SEC}초마다 자동 갱신
          </>
        )}
      </p>

      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : error ? (
        <div className="card" style={{ padding: 24, borderColor: "color-mix(in srgb, var(--red) 40%, transparent)" }}>
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
                const ext = extPrice(item.daytime);   // 미국 프리·애프터마켓이면 현재가 자리에 그 가격
                const chg = ext ? ext.change_rate : item.change_rate;
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
                        {chg >= 0
                          ? <TrendingUp size={14} style={{ color: "var(--green)" }} />
                          : <TrendingDown size={14} style={{ color: "var(--red)" }} />}
                        <div>
                          <p style={{ fontWeight: 600, fontSize: 13 }}>{item.name}</p>
                          <p style={{ color: "var(--text-muted)", fontSize: 11 }}>{item.symbol}</p>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: "12px 16px", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                      {ext && <><SessionTag d={ext} close={item.price} closeRate={item.change_rate} size={10.5} />{" "}</>}
                      <span data-testid="screener-price">{isKR ? `₩${(item.price || 0).toLocaleString()}` : `$${((ext ? ext.price : item.price) || 0).toFixed(2)}`}</span>
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <ChangeTag value={chg} />
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
                          background: isInWatchlist ? "color-mix(in srgb, var(--green) 10%, transparent)" : "color-mix(in srgb, var(--accent) 10%, transparent)",
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
