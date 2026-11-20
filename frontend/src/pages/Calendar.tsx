import { useQuery } from "@tanstack/react-query";
import { marketApi } from "../api/client";
import { Calendar, AlertCircle } from "lucide-react";

const IMPACT_COLOR: Record<string, string> = {
  high: "var(--red)",
  medium: "var(--yellow)",
  low: "var(--text-muted)",
};

const KNOWN_EVENTS = [
  { event: "FOMC 금리결정", country: "US", impact: "high", description: "연준 기준금리 결정 (연 8회). 전 세계 증시 최대 이벤트." },
  { event: "미국 CPI", country: "US", impact: "high", description: "소비자물가지수. 물가↑ → 금리인하 지연 → 주식 불리." },
  { event: "미국 고용보고서 (비농업)", country: "US", impact: "high", description: "매월 첫째 금요일. 고용 과열 or 침체 신호." },
  { event: "미국 PCE 물가", country: "US", impact: "high", description: "연준이 가장 중시하는 물가 지표." },
  { event: "한국은행 금통위", country: "KR", impact: "high", description: "한국 기준금리 결정 (연 8회)." },
  { event: "한국 수출입 동향", country: "KR", impact: "medium", description: "매월 1일. 반도체 수출 수치가 핵심." },
  { event: "옵션 만기일", country: "KR", impact: "medium", description: "매월 둘째 목요일. 3·6·9·12월은 '네 마녀의 날'." },
];

export default function CalendarPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["calendar"],
    queryFn: () => marketApi.calendar().then((r) => r.data),
    staleTime: 60 * 60 * 1000,
  });

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>경제 캘린더</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>주요 경제 지표 일정 · 발표치 vs 예상치에 주목하세요</p>
      </div>

      {/* 주요 이벤트 가이드 */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
          주요 경제 지표 가이드
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {KNOWN_EVENTS.map((e) => (
            <div key={e.event} className="card" style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: IMPACT_COLOR[e.impact], flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{e.event}</span>
                  <span className="badge badge-neutral">{e.country}</span>
                </div>
                <p style={{ color: "var(--text-secondary)", fontSize: 12, marginTop: 2 }}>{e.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CME FedWatch 안내 */}
      <div className="card" style={{ marginBottom: 24, borderColor: "rgba(79,142,247,0.3)", background: "rgba(79,142,247,0.04)" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <AlertCircle size={15} style={{ color: "var(--accent)", flexShrink: 0, marginTop: 1 }} />
          <div>
            <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>💡 CME FedWatch 활용 팁</p>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              FOMC 발표 전 시장이 예상하는 금리 인상·인하 확률을 확인하세요.
              발표된 숫자보다 <strong style={{ color: "var(--text-primary)" }}>"예상보다 좋았는가 나빴는가"</strong>에 시장이 반응합니다.
            </p>
          </div>
        </div>
      </div>

      {/* 실시간 캘린더 (Finnhub) */}
      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : data && data.length > 0 ? (
        <section>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
            향후 2주 일정
          </h2>
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["날짜", "국가", "이벤트", "예상", "이전"].map((h) => (
                    <th key={h} style={{ padding: "12px 16px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((e: any, i: number) => (
                  <tr key={i} style={{ borderBottom: i < data.length - 1 ? "1px solid var(--border)" : "none" }}>
                    <td style={{ padding: "11px 16px", fontSize: 12, color: "var(--text-secondary)" }}>{e.date?.slice(0, 10)}</td>
                    <td style={{ padding: "11px 16px" }}>
                      <span className="badge badge-neutral">{e.country}</span>
                    </td>
                    <td style={{ padding: "11px 16px", fontWeight: 500, fontSize: 13 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ width: 7, height: 7, borderRadius: "50%", background: IMPACT_COLOR[e.impact] || "var(--text-muted)", flexShrink: 0 }} />
                        {e.event}
                      </div>
                    </td>
                    <td style={{ padding: "11px 16px", color: "var(--text-secondary)", fontSize: 13 }}>{e.estimate ?? "-"}</td>
                    <td style={{ padding: "11px 16px", color: "var(--text-muted)", fontSize: 13 }}>{e.prev ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}
