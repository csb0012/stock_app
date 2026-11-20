import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { stockApi, watchlistApi } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import { TrendingUp, TrendingDown, Star, Check, Flame, ArrowDownRight, BarChart3, Activity } from "lucide-react";

type Market = "KR" | "US";
type Mode = "volume_surge" | "trading_value" | "gainers" | "losers";

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

  const { data, isLoading } = useQuery({
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
    mutationFn: (item: any) => watchlistApi.add(item.symbol, market, item.name),
    onSuccess: (_, item) => {
      setAdded((prev) => new Set(prev).add(item.symbol));
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const modeInfo = MODES.find((m) => m.key === mode)!;
  const rows = (data || []) as any[];

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>종목 탐색</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>국내 · 미국 시장 실시간 스크리너 (1분 갱신)</p>
      </div>

      {/* 국장 / 미장 탭 */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {(["KR", "US"] as Market[]).map((m) => (
          <button
            key={m}
            className={`btn ${market === m ? "btn-primary" : "btn-ghost"}`}
            style={{ minWidth: 80 }}
            onClick={() => setMarket(m)}
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
            onClick={() => setMode(key)}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : rows.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <p style={{ color: "var(--text-muted)" }}>데이터 없음 — KIS API 연결 또는 거래시간을 확인하세요</p>
          <p style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 8 }}>
            국내 거래량/거래대금: KIS 실서버 필요 | 그 외: yfinance (무료)
          </p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {[
                  "종목명",
                  "현재가",
                  "등락률",
                  mode === "trading_value" ? "거래대금" : "거래량",
                  mode === "volume_surge" ? "거래량비율" : (mode === "trading_value" ? "" : ""),
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
                    style={{ borderBottom: i < rows.length - 1 ? "1px solid var(--border)" : "none" }}
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
                        : ((item.volume || 0) > 1_000_000
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
                        onClick={() => !isInWatchlist && addMutation.mutate(item)}
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
      )}
    </div>
  );
}
