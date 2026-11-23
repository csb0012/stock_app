import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, Send, Trash2, User, Wrench } from "lucide-react";
import { chatApi, errMsg } from "../api/client";
import Markdown from "../components/common/Markdown";

type Msg = { role: "user" | "assistant"; content: string; tools?: string[]; error?: boolean };

const STORE_KEY = "chat_history";
const TOOL_LABEL: Record<string, string> = {
  today_picks: "오늘의 추천", analyze_stock: "종목 분석", my_portfolio: "투자종목", my_watchlist: "관심종목",
  market_overview: "시장 현황", track_record: "예측 적중률", upcoming_events: "이벤트 일정",
};
const SUGGESTIONS = [
  "오늘 국내 매수 추천 3개 — 언제 얼마에 사고 언제 팔지 알려줘",
  "오늘 하락 확률 높은 종목 중 내가 가진 게 있어?",
  "내 투자종목 점검해줘",
  "엔비디아 지금 사도 돼?",
  "이번 주 조심해야 할 이벤트 있어?",
  "AI 예측 적중률이 실제로 어느 정도야?",
];

function load(): Msg[] {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
  } catch {
    return [];
  }
}

export default function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>(load);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const endRef = useRef<HTMLDivElement>(null);
  const { data: status } = useQuery({ queryKey: ["chat-status"], queryFn: () => chatApi.status().then((r) => r.data) });

  useEffect(() => {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(msgs.slice(-40))); } catch { /* 저장 못 해도 화면은 그대로 */ }
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  useEffect(() => {
    if (!busy) return;
    setElapsed(0);
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    const next: Msg[] = [...msgs, { role: "user", content: q }];
    setMsgs(next);
    setInput("");
    setBusy(true);
    try {
      // 오류 메시지는 대화 기록으로 보내지 않음
      const history = next.filter((m) => !m.error).map(({ role, content }) => ({ role, content }));
      const r = await chatApi.send(history);
      setMsgs([...next, { role: "assistant", content: r.data.reply, tools: r.data.tools }]);
    } catch (e) {
      setMsgs([...next, { role: "assistant", content: errMsg(e), error: true }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 90px)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>AI 챗봇</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            앱의 AI 추천·종목 분석·내 투자종목·시장·적중률을 직접 조회해서 답합니다
            {status?.model && ` · ${status.model}`} · 예측은 참고용 (확실한 종목은 없습니다)
          </p>
        </div>
        {msgs.length > 0 && (
          <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 10px" }} disabled={busy} onClick={() => setMsgs([])}>
            <Trash2 size={13} /> 대화 지우기
          </button>
        )}
      </div>

      {status && !status.enabled && (
        <div className="card" style={{ marginBottom: 12, borderColor: "color-mix(in srgb, var(--yellow) 40%, transparent)" }}>
          <p style={{ fontWeight: 600, color: "var(--yellow)", marginBottom: 4 }}>챗봇을 쓰려면 Claude API 키가 필요합니다</p>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.7 }}>
            console.anthropic.com 에서 API 키를 만든 뒤 <code>backend/.env</code> 에 <code>ANTHROPIC_API_KEY=키</code> 를 넣고 백엔드를 재시작하세요.
            사용한 만큼 요금이 나갑니다 (질문 1번에 보통 수십 원 수준, 도구 조회가 많으면 더).
          </p>
        </div>
      )}

      <div className="card" style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 14, padding: 16 }}>
        {msgs.length === 0 && (
          <div style={{ margin: "auto", textAlign: "center", maxWidth: 640 }}>
            <Bot size={32} style={{ color: "var(--accent)", margin: "0 auto 8px" }} />
            <p style={{ color: "var(--text-secondary)", marginBottom: 14 }}>무엇이든 물어보세요. 예를 들면:</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, justifyContent: "center" }}>
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn btn-ghost" style={{ fontSize: 12, padding: "6px 12px", borderRadius: 999 }}
                  disabled={busy || status?.enabled === false} onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ display: "flex", gap: 10, flexDirection: m.role === "user" ? "row-reverse" : "row", alignItems: "flex-start" }}>
            <div style={{ width: 28, height: 28, borderRadius: 14, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center",
              background: m.role === "user" ? "var(--accent)" : "var(--bg-secondary)", color: m.role === "user" ? "var(--on-accent)" : "var(--accent)" }}>
              {m.role === "user" ? <User size={15} /> : <Bot size={15} />}
            </div>
            <div style={{ maxWidth: "78%", fontSize: 13, lineHeight: 1.65, padding: "10px 14px", borderRadius: 12,
              background: m.role === "user" ? "color-mix(in srgb, var(--accent) 12%, transparent)" : m.error ? "color-mix(in srgb, var(--red) 8%, transparent)" : "var(--bg-secondary)",
              color: m.error ? "var(--red)" : "var(--text-primary)", whiteSpace: m.role === "user" ? "pre-wrap" : undefined }}>
              {m.role === "assistant" && !m.error ? <Markdown text={m.content} /> : m.content}
              {m.tools && m.tools.length > 0 && (
                <p style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "var(--text-muted)", marginTop: 8 }}>
                  <Wrench size={10} /> 조회: {[...new Set(m.tools)].map((t) => TOOL_LABEL[t] || t).join(" · ")}
                </p>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div style={{ display: "flex", gap: 10, alignItems: "center", color: "var(--text-muted)", fontSize: 12 }}>
            <Bot size={15} className="spin" style={{ color: "var(--accent)" }} />
            데이터 조회·분석 중... {elapsed}초 (보통 10~60초)
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send(input); }} style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(input); } }}
          placeholder="예: 삼성전자 내일 사도 돼? (Enter 전송, Shift+Enter 줄바꿈)"
          rows={2}
          disabled={status?.enabled === false}
          style={{ flex: 1, resize: "none", padding: "10px 12px", borderRadius: 10, border: "1px solid var(--border)",
            background: "var(--bg-card)", color: "var(--text-primary)", fontSize: 13, fontFamily: "inherit" }}
        />
        <button type="submit" className="btn btn-primary" disabled={busy || !input.trim() || status?.enabled === false} style={{ alignSelf: "stretch" }}>
          <Send size={15} /> 보내기
        </button>
      </form>
    </div>
  );
}
