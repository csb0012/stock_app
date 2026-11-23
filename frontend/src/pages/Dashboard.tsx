import { useQuery } from "@tanstack/react-query";
import { marketApi, errMsg } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import FetchStatus from "../components/common/FetchStatus";
import { RefreshCw, AlertCircle } from "lucide-react";

const INDEX_LABELS: Record<string, { label: string; unit: string }> = {
  kospi: { label: "코스피 (KOSPI)", unit: "pt" },
  kosdaq: { label: "코스닥 (KOSDAQ)", unit: "pt" },
  dow: { label: "다우존스", unit: "pt" },
  sp500: { label: "S&P 500", unit: "pt" },
  nasdaq: { label: "나스닥", unit: "pt" },
  sox: { label: "필라델피아 반도체 (SOX)", unit: "pt" },
  vix: { label: "VIX (공포지수)", unit: "" },
  us10y: { label: "미국 10년물 금리", unit: "%" },
  dxy: { label: "달러인덱스 (DXY)", unit: "" },
  wti: { label: "WTI 원유", unit: "$" },
  usdkrw: { label: "원/달러 환율", unit: "₩" },
};

/** "KIS 실시간 · 11/20" / "Yahoo · 11/20 종가" + 날짜가 늦으면 경고 */
function SourceLine({ data, close = false }: { data: any; close?: boolean }) {
  if (!data || data.error || !data.source) return null;
  const d = data.as_of ? `${Number(data.as_of.slice(5, 7))}/${Number(data.as_of.slice(8, 10))}` : "";
  const src = data.source === "Yahoo Finance" ? "Yahoo" : data.source;
  return (
    <p style={{ fontSize: 10, color: data.stale ? "var(--yellow)" : "var(--text-muted)", marginTop: 4 }} title={data.stale || ""}>
      {src}{d && ` · ${d}${close && data.source !== "KIS 실시간" ? " 종가" : ""}`}{data.stale ? " ⚠ 최신 아님" : ""}
    </p>
  );
}

function IndexCard({ id, data }: { id: string; data: any }) {
  const meta = INDEX_LABELS[id] || { label: id, unit: "" };
  const price = data?.price ?? 0;
  const changeRate = data?.change_rate ?? 0;

  const getVixColor = () => {
    if (id !== "vix") return "var(--text-primary)";
    if (price >= 30) return "var(--red)";
    if (price >= 20) return "var(--yellow)";
    return "var(--green)";
  };

  return (
    <div className="card" style={{ padding: "14px 16px" }}>
      <p style={{ color: "var(--text-muted)", fontSize: 11, marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>
        {meta.label}
      </p>
      {data?.error ? (
        // 조회 실패를 0 으로 보여주면 실제 값처럼 보이므로 실패라고 표시
        <p style={{ color: "var(--red)", fontSize: 12 }} title={data.error}>조회 실패 — {data.error.slice(0, 60)}</p>
      ) : (
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <span style={{ fontSize: 20, fontWeight: 700, color: getVixColor(), fontVariantNumeric: "tabular-nums" }}>
          {meta.unit === "₩" ? "₩" : meta.unit === "$" ? "$" : ""}
          {price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          {meta.unit === "%" ? "%" : meta.unit === "₩" ? "" : ""}
        </span>
        <ChangeTag value={changeRate} />
      </div>
      )}
      {id === "vix" && !data?.error && (
        <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
          {price >= 30 ? "⚠ 고위험 구간" : price >= 20 ? "⚡ 경계 구간" : "✓ 안정 구간"}
        </p>
      )}
      <SourceLine data={data} close={!["usdkrw", "wti", "dxy"].includes(id)} />
    </div>
  );
}

/** 미국 종목 한 줄: 정규장 종가(기준일) + 시간외(애프터·프리마켓) */
function UsRow({ item }: { item: any }) {
  const d = item.as_of ? `${Number(item.as_of.slice(5, 7))}/${Number(item.as_of.slice(8, 10))}` : "";
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "10px 0", borderBottom: "1px solid var(--border)", gap: 12,
    }}>
      <div>
        <span style={{ fontWeight: 600, fontSize: 13 }}>{item.symbol}</span>
        <span style={{ color: "var(--text-muted)", fontSize: 12, marginLeft: 8 }}>{item.name}</span>
      </div>
      {item.error ? (
        <span style={{ color: "var(--red)", fontSize: 12 }}>조회 실패 — {item.error.slice(0, 60)}</span>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {item.ext && (
            <span style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }} title={`${item.ext.time} 기준`}>
              {item.ext.label}
              <strong style={{ fontVariantNumeric: "tabular-nums", color: "var(--text-primary)" }}>${item.ext.price.toFixed(2)}</strong>
              <span style={{ color: item.ext.change_rate >= 0 ? "var(--green)" : "var(--red)" }}>
                {item.ext.change_rate >= 0 ? "+" : ""}{item.ext.change_rate.toFixed(2)}%
              </span>
            </span>
          )}
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: item.stale ? "var(--yellow)" : "var(--text-muted)" }} title={item.stale || ""}>
              {d} 종가{item.stale ? " ⚠" : ""}
            </span>
            <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>${item.price.toFixed(2)}</span>
            <ChangeTag value={item.change_rate} />
          </span>
        </div>
      )}
    </div>
  );
}

/** 대시보드 한 구역 조회 — 구역마다 따로 받아서 먼저 온 것부터 표시 (느린 구역이 나머지를 막지 않음) */
function useSection(name: string) {
  return useQuery({
    queryKey: ["market-section", name],
    queryFn: () => marketApi.section(name).then((r) => r.data),
    // 서버가 이전 값을 먼저 주고 뒤에서 갱신 중(refreshing)이면 3초 뒤 다시 받아 최신 값으로, 아니면 1분마다
    refetchInterval: (q) => (q.state.data?.refreshing ? 3000 : 60_000),
  });
}

function SectionTitle({ title, q }: { title: string; q: any }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
      <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 1 }}>
        {title}
      </h2>
      <FetchStatus updatedAt={q.data?.updated_at} fetching={q.isFetching || q.data?.refreshing}
                   error={q.data?.refresh_error || (q.isError && q.data ? errMsg(q.error) : null)} />
    </div>
  );
}

function SectionError({ q }: { q: any }) {
  if (!q.isError || q.data) return null;  // 이전 데이터가 있으면 그걸 보여주고 제목 옆에 실패 표시
  return (
    <div className="card" style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--red)", fontSize: 13 }}>
      <AlertCircle size={16} /> 불러오지 못했습니다 — {errMsg(q.error)}
    </div>
  );
}

function Skeleton({ height = 70, count = 1, grid = false }: { height?: number; count?: number; grid?: boolean }) {
  const box = <div className="card" style={{ height, opacity: 0.45, animation: "pulse 1.4s ease-in-out infinite" }} />;
  return grid ? (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
      {Array.from({ length: count }, (_, i) => <div key={i}>{box}</div>)}
    </div>
  ) : box;
}

const INDEX_ORDER = Object.keys(INDEX_LABELS);

export default function Dashboard() {
  const krQ = useSection("kr_indices");
  const glQ = useSection("global_indices");
  const bigQ = useSection("bigtech");
  const etfQ = useSection("etfs");
  const all = [krQ, glQ, bigQ, etfQ];
  const anyFetching = all.some((q) => q.isFetching);

  const now = new Date();
  const timeStr = now.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
  const dateStr = now.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" });

  // 국내(KIS)·해외(Yahoo) 지수를 화면 순서대로 합침 — 먼저 온 쪽부터 카드가 채워지고 나머지는 자리만 표시
  const indexCards = INDEX_ORDER.map((id) => {
    const src = id === "kospi" || id === "kosdaq" ? krQ : glQ;
    return { id, data: src.data?.[id], loading: !src.data && src.isLoading, failed: !src.data && src.isError };
  });
  const vix = glQ.data?.vix;
  const latest = [krQ.data?.updated_at, glQ.data?.updated_at].filter(Boolean).sort().pop();

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>오늘의 시장 브리핑</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>{dateStr} {timeStr} 기준</p>
          <p style={{ color: "var(--text-muted)", fontSize: 11, marginTop: 2 }}>
            국내 지수: KIS 실시간 · 해외 지수·종목·환율: Yahoo Finance (정규장 종가 기준, 미국 종목은 시간외 가격 따로 표시, 장중 최대 15분 지연)
          </p>
        </div>
        <button className="btn btn-ghost" onClick={() => all.forEach((q) => q.refetch())} disabled={anyFetching}>
          <RefreshCw size={14} style={{ animation: anyFetching ? "spin 1s linear infinite" : "none" }} />
          새로고침
        </button>
      </div>

      {/* 주요 지수 */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 1 }}>
            주요 지수 · 매크로
          </h2>
          <FetchStatus updatedAt={latest} fetching={krQ.isFetching || glQ.isFetching || krQ.data?.refreshing || glQ.data?.refreshing}
                       error={krQ.data?.refresh_error || glQ.data?.refresh_error} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
          {indexCards.map(({ id, data, loading, failed }) =>
            loading ? <Skeleton key={id} height={78} /> :
            failed ? <IndexCard key={id} id={id} data={{ error: errMsg((id === "kospi" || id === "kosdaq" ? krQ : glQ).error) }} /> :
            <IndexCard key={id} id={id} data={data} />
          )}
        </div>
      </section>

      {/* 빅테크 */}
      <section style={{ marginBottom: 32 }}>
        <SectionTitle title="빅테크 동향" q={bigQ} />
        <SectionError q={bigQ} />
        {bigQ.isLoading ? <Skeleton height={300} /> : bigQ.data && (
          <div className="card" style={{ padding: "4px 16px" }}>
            {(bigQ.data.items || []).map((item: any) => <UsRow key={item.symbol} item={item} />)}
          </div>
        )}
      </section>

      {/* 미국 주요 ETF */}
      <section style={{ marginBottom: 32 }}>
        <SectionTitle title="미국 주요 ETF" q={etfQ} />
        <SectionError q={etfQ} />
        {etfQ.isLoading ? <Skeleton height={220} /> : etfQ.data && (
          <div className="card" style={{ padding: "4px 16px" }}>
            {(etfQ.data.items || []).map((item: any) => <UsRow key={item.symbol} item={item} />)}
          </div>
        )}
      </section>

      {/* VIX 경고 배너 */}
      {vix?.price >= 25 && !vix.error && (
        <div className="card" style={{ borderColor: "var(--yellow)", background: "color-mix(in srgb, var(--yellow) 5%, transparent)" }}>
          <p style={{ color: "var(--yellow)", fontWeight: 600 }}>
            ⚠ VIX {vix.price.toFixed(1)} — 시장 불안 구간입니다. 신규 진입 시 주의하세요.
          </p>
        </div>
      )}
    </div>
  );
}
