import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Layers, RefreshCw, Search as SearchIcon } from "lucide-react";
import { themeApi, errMsg } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import FetchStatus from "../components/common/FetchStatus";
import StockQuoteCard from "../components/common/StockQuoteCard";
import WatchButton from "../components/common/WatchButton";
import AccumBadge from "../components/common/AccumBadge";

type Sort = "avg" | "strong" | "name";

function fmtVol(v?: number | null) {
  if (v == null) return "-";
  return v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : `${(v / 1_000).toFixed(0)}K`;
}

export default function Themes() {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<Sort>("avg");
  const [selected, setSelected] = useState<string | null>(null);
  const [picked, setPicked] = useState<any>(null);

  const list = useQuery({
    queryKey: ["themes"],
    queryFn: () => themeApi.list().then((r) => r.data),
    // 서버가 이전 값을 주고 뒤에서 갱신 중이면 3초 뒤 다시, 아니면 1분마다
    // 테마 구성을 받는 중이라 아직 없으면(오류) 5초마다 다시 확인
    refetchInterval: (qq) => (qq.state.data?.refreshing ? 3000 : !qq.state.data && qq.state.error ? 5000 : 60_000),
    retry: false,
  });
  const refresh = useMutation({ mutationFn: () => themeApi.refresh(), onSuccess: () => setTimeout(() => list.refetch(), 1500) });

  const themes: any[] = useMemo(() => {
    const rows = (list.data?.themes || []).filter((t: any) => !q || t.name.toLowerCase().includes(q.toLowerCase()));
    if (sort === "strong") return [...rows].sort((a, b) => b.strong - a.strong || b.avg_change - a.avg_change);
    if (sort === "name") return [...rows].sort((a, b) => a.name.localeCompare(b.name, "ko"));
    return rows;
  }, [list.data, q, sort]);

  const current = selected || themes[0]?.no || null;
  const detail = useQuery({
    queryKey: ["theme", current],
    queryFn: () => themeApi.detail(current!).then((r) => r.data),
    enabled: !!current,
    refetchInterval: (qq) => (qq.state.data?.refreshing ? 3000 : 30_000),
  });
  const st = list.data?.status;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>테마별 주식</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            테마 분류: 네이버 증권 (하루 1번 갱신) · 등락률: KIS 실시간 시세로 직접 계산 · 같은 테마가 같이 움직이는지 확인하세요
          </p>
          <div style={{ marginTop: 4, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <FetchStatus updatedAt={list.data?.updated_at} fetching={list.isFetching || list.data?.refreshing}
                         error={list.data?.refresh_error} />
            {st?.updated_at && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>테마 구성 {st.updated_at.slice(5, 16).replace("T", " ")} 기준 · {st.theme_count}개</span>}
            {st?.running && <span style={{ fontSize: 11, color: "var(--accent)" }}>테마 구성 받는 중 {st.done}/{st.total || "?"}</span>}
            {st?.error && <span style={{ fontSize: 11, color: "var(--red)" }}>테마 갱신 실패: {st.error}</span>}
          </div>
        </div>
        <button className="btn btn-ghost" style={{ fontSize: 12 }} disabled={refresh.isPending || st?.running} onClick={() => refresh.mutate()}
                title="네이버에서 테마 구성을 다시 받습니다 (2~3분)">
          <RefreshCw size={13} className={st?.running ? "spin" : undefined} /> 테마 구성 다시 받기
        </button>
      </div>

      {list.isLoading && <p style={{ color: "var(--text-muted)" }}>테마 불러오는 중... (처음엔 테마 종목 시세를 받느라 조금 걸립니다)</p>}
      {list.error && !list.data && (
        <div className="card" style={{ padding: 20, borderColor: "color-mix(in srgb, var(--red) 40%, transparent)" }}>
          <p style={{ color: "var(--red)", fontWeight: 600, marginBottom: 6 }}>테마 조회 실패</p>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>{errMsg(list.error)}</p>
        </div>
      )}

      {list.data && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 400px) 1fr", gap: 16, alignItems: "start" }}>
          {/* 테마 목록 */}
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ padding: 12, borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ position: "relative" }}>
                <SearchIcon size={13} style={{ position: "absolute", left: 10, top: 10, color: "var(--text-muted)" }} />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="테마 이름 검색 (예: 로봇, 2차전지)"
                  style={{ width: "100%", padding: "7px 10px 7px 30px", borderRadius: 8, border: "1px solid var(--border)",
                    background: "var(--bg-primary)", color: "var(--text-primary)", fontSize: 12 }} />
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                {([["avg", "평균 등락률순"], ["strong", "강세 종목 수순"], ["name", "이름순"]] as [Sort, string][]).map(([k, label]) => (
                  <button key={k} className={`btn ${sort === k ? "btn-primary" : "btn-ghost"}`} style={{ fontSize: 11, padding: "4px 8px" }}
                    onClick={() => setSort(k)}>{label}</button>
                ))}
              </div>
            </div>
            <div style={{ maxHeight: "calc(100vh - 260px)", overflowY: "auto" }}>
              {themes.length === 0 && <p style={{ padding: 16, color: "var(--text-muted)", fontSize: 13 }}>맞는 테마가 없습니다</p>}
              {themes.map((t) => (
                <div key={t.no} onClick={() => { setSelected(t.no); setPicked(null); }}
                  style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", cursor: "pointer",
                    background: current === t.no ? "var(--bg-hover)" : "transparent",
                    borderLeft: current === t.no ? "2px solid var(--accent)" : "2px solid transparent" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: 13, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.name}</span>
                    <ChangeTag value={t.avg_change} />
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3, display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <span>{t.count}종목 · <span style={{ color: "var(--green)" }}>▲{t.up}</span> <span style={{ color: "var(--red)" }}>▼{t.down}</span>{t.strong > 0 && <> · +5% 이상 {t.strong}</>}</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t.leaders.slice(0, 2).map((l: any) => `${l.name} ${l.change_rate >= 0 ? "+" : ""}${l.change_rate.toFixed(1)}%`).join(", ")}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 선택한 테마의 종목 */}
          <div>
            {picked && <StockQuoteCard item={picked} onClose={() => setPicked(null)} actions={<WatchButton item={picked} />} />}
            <div className="card" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <Layers size={15} style={{ color: "var(--accent)" }} />
                <span style={{ fontWeight: 700 }}>{detail.data?.name || themes.find((t) => t.no === current)?.name || "테마를 고르세요"}</span>
                {detail.data && <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{detail.data.items.length}종목 · 오늘 등락률순</span>}
                <span style={{ marginLeft: "auto" }}><FetchStatus updatedAt={detail.data?.updated_at} fetching={detail.isFetching} /></span>
              </div>
              {detail.data?.description && (
                <p style={{ padding: "10px 16px", fontSize: 12, lineHeight: 1.6, color: "var(--text-secondary)", borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}>
                  {detail.data.description}
                </p>
              )}
              {detail.isLoading && <p style={{ padding: 16, color: "var(--text-muted)", fontSize: 13 }}>불러오는 중...</p>}
              {detail.error && !detail.data && <p style={{ padding: 16, color: "var(--red)", fontSize: 13 }}>{errMsg(detail.error)}</p>}
              {detail.data && (
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["종목", "현재가", "등락률", "거래량", "매집 점수", ""].map((h, i) => (
                        <th key={i} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.data.items.map((r: any) => (
                      <tr key={r.symbol} onClick={() => setPicked({ market: "KR", symbol: r.symbol, name: r.name })}
                        style={{ cursor: "pointer", borderBottom: "1px solid var(--border)" }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                        <td style={{ padding: "10px 14px" }}>
                          <p style={{ fontWeight: 600, fontSize: 13 }}>{r.name} <span style={{ color: "var(--text-muted)", fontSize: 11, fontWeight: 400 }}>{r.symbol}</span></p>
                          {r.reason && (
                            <p title={r.reason} style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2, maxWidth: 460, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.reason}</p>
                          )}
                          {r.other_themes?.length > 0 && (
                            <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>다른 테마: {r.other_themes.join(", ")}</p>
                          )}
                        </td>
                        <td style={{ padding: "10px 14px", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{r.price != null ? `₩${r.price.toLocaleString()}` : "-"}</td>
                        <td style={{ padding: "10px 14px" }}>{r.change_rate != null ? <ChangeTag value={r.change_rate} /> : <span style={{ color: "var(--text-muted)" }}>시세 없음</span>}</td>
                        <td style={{ padding: "10px 14px", fontSize: 12, color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>{fmtVol(r.volume)}</td>
                        <td style={{ padding: "10px 14px" }}><AccumBadge score={r.accum_score} /></td>
                        <td style={{ padding: "10px 14px" }}><WatchButton item={{ symbol: r.symbol, market: "KR", name: r.name }} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            {list.data.price_errors?.length > 0 && (
              <p style={{ fontSize: 11, color: "var(--yellow)", marginTop: 8 }}>일부 시세 조회 실패: {list.data.price_errors[0]}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
