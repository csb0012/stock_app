import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import FetchStatus from "../components/common/FetchStatus";
import { marketApi, errMsg } from "../api/client";
import { AlertCircle, ChevronDown, ChevronUp } from "lucide-react";

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

function ResultBadge({ result }: { result: string | null }) {
  if (!result) return null;
  const color = result.includes("상회") ? "var(--green)" : result.includes("하회") ? "var(--red)" : "var(--text-muted)";
  return (
    <span style={{ fontSize: 11, padding: "2px 7px", borderRadius: 4, background: "rgba(128,128,128,0.1)", color, fontWeight: 600, whiteSpace: "nowrap" }}>
      {result}
    </span>
  );
}

function EventRow({ e, isPast }: { e: any; isPast: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const hasAnalysis = !!e.analysis;

  return (
    <>
      <tr
        style={{ borderBottom: "1px solid var(--border)", background: isPast ? "rgba(255,255,255,0.01)" : "transparent" }}
        onClick={() => hasAnalysis && setExpanded(!expanded)}
        onMouseEnter={(el) => hasAnalysis && ((el.currentTarget as HTMLElement).style.background = "var(--bg-hover)")}
        onMouseLeave={(el) => ((el.currentTarget as HTMLElement).style.background = isPast ? "rgba(255,255,255,0.01)" : "transparent")}
      >
        <td style={{ padding: "11px 16px", fontSize: 12, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
          {isPast && <span style={{ marginRight: 4, color: "var(--text-muted)", fontSize: 10 }}>●</span>}
          {e.date?.slice(0, 10)}
        </td>
        <td style={{ padding: "11px 16px" }}>
          <span className="badge badge-neutral">{e.country}</span>
        </td>
        <td style={{ padding: "11px 16px", fontWeight: 500, fontSize: 13 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: IMPACT_COLOR[e.impact] || "var(--text-muted)", flexShrink: 0 }} />
            {e.event}
          </div>
        </td>
        <td style={{ padding: "11px 16px", fontSize: 12 }}>
          {e.actual
            ? <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{e.actual}</span>
            : <span style={{ color: "var(--text-muted)" }}>{e.estimate ?? "-"}</span>}
        </td>
        <td style={{ padding: "11px 16px", color: "var(--text-muted)", fontSize: 12 }}>{e.estimate ?? "-"}</td>
        <td style={{ padding: "11px 16px", color: "var(--text-muted)", fontSize: 12 }}>{e.prev ?? "-"}</td>
        <td style={{ padding: "11px 16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <ResultBadge result={e.result} />
            {hasAnalysis && (
              <span style={{ color: "var(--text-muted)" }}>{expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}</span>
            )}
          </div>
        </td>
      </tr>
      {expanded && e.analysis && (
        <tr style={{ borderBottom: "1px solid var(--border)" }}>
          <td colSpan={7} style={{ padding: "12px 16px 14px 32px", background: "color-mix(in srgb, var(--accent) 4%, transparent)" }}>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.7 }}>
              💬 {e.analysis}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

export default function CalendarPage() {
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["calendar"],
    queryFn: () => marketApi.calendar().then((r) => r.data),
    staleTime: 60 * 60 * 1000,
  });

  const today = new Date().toISOString().slice(0, 10);
  const events: any[] = data?.events || [];
  const pastEvents = events.filter((e: any) => e.date?.slice(0, 10) < today);
  const futureEvents = events.filter((e: any) => e.date?.slice(0, 10) >= today);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>경제 캘린더</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          최근 2주 발표 + 앞으로 4주 일정 · 발표치 vs 예상치
          {data?.source && <span> · 출처: {data.source}</span>}
        </p>
        {data?.errors?.length > 0 && (
          <p style={{ color: "var(--yellow)", fontSize: 12, marginTop: 4 }}>⚠ {data.errors.join(" / ")}</p>
        )}
      </div>

      {/* 주요 이벤트 가이드 */}
      <section style={{ marginBottom: 28 }}>
        <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
          주요 경제 지표 가이드
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {KNOWN_EVENTS.map((e) => (
            <div key={e.event} className="card" style={{ display: "flex", alignItems: "center", gap: 14, padding: "10px 16px" }}>
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

      {/* CME FedWatch */}
      <div className="card" style={{ marginBottom: 24, borderColor: "color-mix(in srgb, var(--accent) 30%, transparent)", background: "color-mix(in srgb, var(--accent) 4%, transparent)" }}>
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

      {data && <div style={{ marginBottom: 12 }}><FetchStatus updatedAt={data.updated_at} fetching={isFetching || data.refreshing} error={data.refresh_error} /></div>}
      {error && (
        <div className="card" style={{ padding: 20, borderColor: "color-mix(in srgb, var(--red) 40%, transparent)", marginBottom: 16 }}>
          <p style={{ color: "var(--red)", fontWeight: 600, marginBottom: 6 }}>경제 캘린더 조회 실패{data ? " — 아래는 이전 일정" : ""}</p>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>{errMsg(error)}</p>
        </div>
      )}
      {isLoading ? (
        <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>
      ) : error && !data ? null : events.length === 0 ? (
        <p style={{ color: "var(--text-muted)" }}>이 기간에 해당하는 주요 일정이 없습니다.</p>
      ) : (
        <>
          {/* 과거 이벤트 */}
          {pastEvents.length > 0 && (
            <section style={{ marginBottom: 32 }}>
              <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
                최근 발표 결과
              </h2>
              <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["날짜", "국가", "이벤트", "실제", "예상", "이전", "결과"].map((h) => (
                        <th key={h} style={{ padding: "11px 16px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {pastEvents.map((e: any, i: number) => (
                      <EventRow key={i} e={e} isPast={true} />
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* 향후 일정 */}
          {futureEvents.length > 0 && (
            <section>
              <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
                향후 주요 일정
              </h2>
              <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["날짜", "국가", "이벤트", "예상", "이전", "", ""].map((h, i) => (
                        <th key={i} style={{ padding: "11px 16px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {futureEvents.map((e: any, i: number) => (
                      <EventRow key={i} e={e} isPast={false} />
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
