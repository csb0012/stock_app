import { useQuery } from "@tanstack/react-query";
import { stockApi } from "../api/client";
import ChangeTag from "../components/common/ChangeTag";
import { TrendingUp, TrendingDown } from "lucide-react";

export default function Screener() {
  const { data, isLoading } = useQuery({
    queryKey: ["volume-surge"],
    queryFn: () => stockApi.volumeSurge().then((r) => r.data),
    refetchInterval: 60_000,
  });

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>종목 탐색</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>거래량 급증 · 국내 시장 (1분 갱신)</p>
      </div>

      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["종목명", "현재가", "등락률", "거래량", "거래량 비율"].map((h) => (
                  <th key={h} style={{ padding: "12px 16px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data || []).map((item: any, i: number) => (
                <tr key={item.symbol} style={{ borderBottom: i < data.length - 1 ? "1px solid var(--border)" : "none" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
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
                    ₩{item.price.toLocaleString()}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <ChangeTag value={item.change_rate} />
                  </td>
                  <td style={{ padding: "12px 16px", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                    {(item.volume / 1000).toFixed(0)}K
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{ color: item.volume_ratio > 500 ? "var(--red)" : item.volume_ratio > 200 ? "var(--yellow)" : "var(--text-secondary)", fontWeight: 600 }}>
                      {item.volume_ratio.toFixed(0)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
