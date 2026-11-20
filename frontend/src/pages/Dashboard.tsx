import { useQuery } from "@tanstack/react-query";
import { marketApi } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import { RefreshCw, AlertCircle } from "lucide-react";

const INDEX_LABELS: Record<string, { label: string; unit: string }> = {
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
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <span style={{ fontSize: 20, fontWeight: 700, color: getVixColor(), fontVariantNumeric: "tabular-nums" }}>
          {meta.unit === "₩" ? "₩" : meta.unit === "$" ? "$" : ""}
          {price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          {meta.unit === "%" ? "%" : meta.unit === "₩" ? "" : ""}
        </span>
        <ChangeTag value={changeRate} />
      </div>
      {id === "vix" && (
        <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
          {price >= 30 ? "⚠ 고위험 구간" : price >= 20 ? "⚡ 경계 구간" : "✓ 안정 구간"}
        </p>
      )}
    </div>
  );
}

function BigTechRow({ item }: { item: any }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "10px 0", borderBottom: "1px solid var(--border)",
    }}>
      <div>
        <span style={{ fontWeight: 600, fontSize: 13 }}>{item.symbol}</span>
        <span style={{ color: "var(--text-muted)", fontSize: 12, marginLeft: 8 }}>{item.name}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
          ${item.price.toFixed(2)}
        </span>
        <ChangeTag value={item.change_rate} />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["market-overview"],
    queryFn: () => marketApi.overview().then((r) => r.data),
    refetchInterval: 60_000,
  });

  const now = new Date();
  const timeStr = now.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
  const dateStr = now.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" });

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>오늘의 시장 브리핑</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>{dateStr} {timeStr} 기준</p>
        </div>
        <button className="btn btn-ghost" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw size={14} style={{ animation: isFetching ? "spin 1s linear infinite" : "none" }} />
          새로고침
        </button>
      </div>

      {isError && (
        <div className="card" style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--red)", marginBottom: 20 }}>
          <AlertCircle size={16} />
          데이터를 불러오지 못했습니다. API 키를 확인하거나 잠시 후 다시 시도하세요.
        </div>
      )}

      {isLoading ? (
        <div style={{ color: "var(--text-muted)", textAlign: "center", paddingTop: 60 }}>데이터 로딩 중...</div>
      ) : (
        <>
          {/* 주요 지수 */}
          <section style={{ marginBottom: 32 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
              주요 지수 · 매크로
            </h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
              {Object.entries(data?.indices || {}).map(([id, val]: [string, any]) => (
                <IndexCard key={id} id={id} data={val} />
              ))}
            </div>
          </section>

          {/* 빅테크 */}
          <section style={{ marginBottom: 32 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
              빅테크 동향
            </h2>
            <div className="card" style={{ padding: "4px 16px" }}>
              {(data?.bigtech || []).map((item: any) => (
                <BigTechRow key={item.symbol} item={item} />
              ))}
            </div>
          </section>

          {/* VIX 경고 배너 */}
          {data?.indices?.vix?.price >= 25 && (
            <div className="card" style={{ borderColor: "var(--yellow)", background: "rgba(251, 191, 36, 0.05)" }}>
              <p style={{ color: "var(--yellow)", fontWeight: 600 }}>
                ⚠ VIX {data.indices.vix.price.toFixed(1)} — 시장 불안 구간입니다. 신규 진입 시 주의하세요.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
