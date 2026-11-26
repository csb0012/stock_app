import { useState } from "react";
import type React from "react";
import { useQuery } from "@tanstack/react-query";
import FetchStatus from "../components/common/FetchStatus";
import { useNarrow } from "../components/common/useNarrow";
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

const TH: React.CSSProperties = { padding: "11px 16px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", fontWeight: 600 };
const TD: React.CSSProperties = { padding: "11px 16px", fontSize: 12 };

/** 이전 대비 변화 — 오름·내림이 좋은지 나쁜지는 지표마다 달라서 색은 중립, 화살표로만 구분 */
function ChangeBadge({ e }: { e: any }) {
  if (!e.change_text) return null;
  const arrow = e.change === "up" || e.change === "down";
  return (
    <span className="badge badge-neutral" style={{ fontWeight: 600, whiteSpace: "nowrap", color: arrow ? "var(--text-primary)" : undefined }}>
      {e.change_text}
    </span>
  );
}

const FLAG: Record<string, string> = { KR: "🇰🇷", US: "🇺🇸" };

/** 이벤트 관련 기사 (발표일 앞뒤 며칠만, 믿을 만한 국내 언론사만 — 서버 econ_calendar._attach_news) */
function EventNews({ e }: { e: any }) {
  if (e.news_error) return <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>관련 뉴스를 못 받았습니다</p>;
  if (!e.news?.length) return null;
  return (
    <div data-testid="cal-news" style={{ marginTop: 10, fontSize: 12.5 }}>
      <strong style={{ color: "var(--text-primary)" }}>관련 뉴스</strong>
      <ul style={{ margin: "4px 0 0", paddingLeft: 18, lineHeight: 1.7 }}>
        {e.news.map((n: any) => (
          <li key={n.url || n.title}>
            {/^https?:\/\//.test(n.url || "") ? <a href={n.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>{n.title}</a> : n.title}
            <span style={{ color: "var(--text-muted)", fontSize: 11 }}> · {n.press} {n.date?.slice(5)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Explain({ e }: { e: any }) {
  const x = e.explain;
  if (!x) return null;
  const scenarios = Object.entries(x.scenarios || {}) as [string, string][];
  return (
    <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.7, display: "flex", flexDirection: "column", gap: 8 }}>
      <p><strong style={{ color: "var(--text-primary)" }}>어떤 지표?</strong> {x.about}</p>
      {e.released && x.effect ? (
        <p>
          <strong style={{ color: "var(--text-primary)" }}>이번 결과 — {e.change_text}</strong>
          {e.period ? ` (${e.period}, ${x.metric} ${e.prev} → ${e.actual})` : ` (${e.prev} → ${e.actual})`}
          <br />→ {x.effect}
          {e.statement && <><br /><span style={{ color: "var(--text-muted)" }}>결정문: {e.statement}</span></>}
        </p>
      ) : (
        <div>
          <strong style={{ color: "var(--text-primary)" }}>
            {e.note ? "발표값을 아직 못 받음 — 결과에 따라 생길 수 있는 현상" : "발표 결과에 따라 생길 수 있는 현상"}
          </strong>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {scenarios.map(([word, text]) => (
              <li key={word}><strong>{word}</strong>: {text}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function EventRow({ e, past }: { e: any; past: boolean }) {
  const [open, setOpen] = useState(false);
  const cols = past ? 5 : 3;
  return (
    <>
      <tr
        style={{ borderBottom: open ? "none" : "1px solid var(--border)", cursor: "pointer" }}
        onClick={() => setOpen(!open)}
        onMouseEnter={(el) => ((el.currentTarget as HTMLElement).style.background = "var(--bg-hover)")}
        onMouseLeave={(el) => ((el.currentTarget as HTMLElement).style.background = "transparent")}
      >
        <td style={{ ...TD, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{e.date?.slice(0, 10)}</td>
        <td style={{ ...TD, fontWeight: 500, fontSize: 13 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: IMPACT_COLOR[e.impact] || "var(--text-muted)", flexShrink: 0 }} />
            <span title={e.country === "KR" ? "한국" : "미국"}>{FLAG[e.country] || ""}</span> {e.event}
            {e.news?.length > 0 && <span className="badge badge-neutral" style={{ fontSize: 10.5 }}>뉴스 {e.news.length}</span>}
          </div>
          {e.period && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2, marginLeft: 15 }}>{e.period} · {e.explain?.metric}</div>}
        </td>
        {past ? (
          <>
            <td style={TD}>
              {e.released
                ? <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{e.actual}</span>
                : <span style={{ color: "var(--text-muted)" }} title={e.note}>{e.note ? "값 없음" : "-"}</span>}
            </td>
            <td style={{ ...TD, color: "var(--text-muted)" }}>{e.released ? e.prev : "-"}</td>
            <td style={TD}><ChangeBadge e={e} /></td>
          </>
        ) : (
          <td style={{ ...TD, color: "var(--text-muted)" }}>{e.explain?.metric}</td>
        )}
        <td style={{ ...TD, color: "var(--text-muted)", width: 24 }}>{open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}</td>
      </tr>
      {open && (
        <tr style={{ borderBottom: "1px solid var(--border)" }}>
          <td colSpan={cols + 1} style={{ padding: "4px 16px 14px 31px", background: "color-mix(in srgb, var(--accent) 4%, transparent)" }}>
            {e.note && <p style={{ fontSize: 12, color: "var(--yellow)", margin: "8px 0" }}>⚠ {e.note}</p>}
            <div style={{ paddingTop: 8 }}><Explain e={e} /></div>
            <EventNews e={e} />
          </td>
        </tr>
      )}
    </>
  );
}

/** 휴대폰: 한 일정 = 한 칸 (표는 이벤트 이름이 한 글자씩 세로로 쪼개졌음) — 누르면 해설 */
function EventCard({ e, past }: { e: any; past: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div data-testid="cal-card" style={{ borderBottom: "1px solid var(--border)" }}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        style={{ all: "unset", boxSizing: "border-box", width: "100%", cursor: "pointer", padding: "11px 14px", display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <div style={{ width: 7, height: 7, borderRadius: "50%", background: IMPACT_COLOR[e.impact] || "var(--text-muted)", flexShrink: 0 }} />
          <strong style={{ fontSize: 13.5, flex: 1, minWidth: 0 }}>{FLAG[e.country] || ""} {e.event}</strong>
          <span style={{ fontSize: 11.5, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{e.date?.slice(5, 10).replace("-", "/")}</span>
          {open ? <ChevronUp size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} /> : <ChevronDown size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />}
        </div>
        {e.period && <div style={{ fontSize: 11.5, color: "var(--text-muted)", paddingLeft: 15 }}>{e.period} · {e.explain?.metric}</div>}
        {past ? (
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", paddingLeft: 15, fontSize: 12.5 }}>
            {e.released
              ? <span>실제 <strong>{e.actual}</strong></span>
              : <span style={{ color: "var(--text-muted)" }}>{e.note ? "값 없음" : "발표 전"}</span>}
            {e.released && <span style={{ color: "var(--text-muted)" }}>이전 {e.prev}</span>}
            <ChangeBadge e={e} />
          </div>
        ) : !e.period && e.explain?.metric ? <div style={{ fontSize: 11.5, color: "var(--text-muted)", paddingLeft: 15 }}>{e.explain.metric}</div> : null}
      </button>
      {open && (
        <div style={{ padding: "2px 14px 12px 29px", background: "color-mix(in srgb, var(--accent) 4%, transparent)" }}>
          {e.note && <p style={{ fontSize: 12, color: "var(--yellow)", margin: "8px 0" }}>⚠ {e.note}</p>}
          <div style={{ paddingTop: 8 }}><Explain e={e} /></div>
          <EventNews e={e} />
        </div>
      )}
    </div>
  );
}

function EventTable({ title, events, past }: { title: string; events: any[]; past: boolean }) {
  const heads = past ? ["날짜", "이벤트", "실제", "이전", "변화", ""] : ["날짜", "이벤트", "발표 내용", ""];
  const narrow = useNarrow();
  if (narrow) {
    return (
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 10, letterSpacing: 1 }}>{title}</h2>
        <div className="card" style={{ padding: 0 }}>
          {events.map((e: any) => <EventCard key={`${e.key}-${e.date}`} e={e} past={past} />)}
        </div>
      </section>
    );
  }
  return (
    <section style={{ marginBottom: 32 }}>
      <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12, letterSpacing: 1 }}>{title}</h2>
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              {heads.map((h, i) => <th key={i} style={TH}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {events.map((e: any) => <EventRow key={`${e.key}-${e.date}`} e={e} past={past} />)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function CalendarPage() {
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["calendar"],
    queryFn: () => marketApi.calendar().then((r) => r.data),
    staleTime: 60 * 60 * 1000,
  });

  // 브라우저 기준 오늘 (toISOString 은 UTC 라 한국 오전 9시 전엔 어제 날짜가 됨)
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const events: any[] = data?.events || [];
  const isPast = (e: any) => e.released || e.date?.slice(0, 10) < today;   // 오늘 발표돼 값이 있으면 '최근 발표'로
  const pastEvents = events.filter(isPast);
  const futureEvents = events.filter((e: any) => !isPast(e));

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>경제 캘린더</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          최근 2주 발표 + 앞으로 4주 일정 (미국 지표·FOMC + 🇰🇷 한국은행 금통위) · 실제 발표값과 이전 대비 변화 · 결과에 따른 시장 영향 해설 · 발표일 앞뒤엔 관련 뉴스
          {data?.source && <span> · 출처: {data.source}</span>}
        </p>
        {data?.disclaimer && <p style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 4 }}>ⓘ {data.disclaimer}</p>}
        {data?.errors?.length > 0 && (
          <p style={{ color: "var(--yellow)", fontSize: 12, marginTop: 4 }}>⚠ {data.errors.join(" / ")}</p>
        )}
      </div>

      {/* 발표값·해설(explain)이 하나도 없으면 업데이트 전 백엔드가 준 예전 형식 → 서버 재시작 안내 */}
      {events.length > 0 && events.every((e: any) => !e.explain) && !isFetching && (
        <p data-testid="calendar-old-format" style={{ color: "var(--yellow)", fontSize: 12, marginBottom: 8 }}>
          ⚠ 백엔드가 예전 버전의 캘린더 데이터를 주고 있습니다 (발표값·해설 없음) — 백엔드를 다시 시작하세요
          (start.bat 창을 닫고 다시 실행 / Docker: docker compose restart backend / 클라우드: bash deploy/update.sh)
        </p>
      )}
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
          {pastEvents.length > 0 && <EventTable title="최근 발표 결과 (행을 누르면 해설)" events={[...pastEvents].reverse()} past />}
          {futureEvents.length > 0 && <EventTable title="향후 주요 일정 (행을 누르면 결과별 시나리오)" events={futureEvents} past={false} />}
        </>
      )}

      {/* 주요 이벤트 가이드 */}
      <details style={{ marginBottom: 20 }}>
        <summary style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12, cursor: "pointer", letterSpacing: 1 }}>
          주요 경제 지표 가이드 (눌러서 펼치기)
        </summary>
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
      </details>

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

    </div>
  );
}
