import { useEffect, useRef, useState } from "react";
import { Bot, Send, Trash2, User, Wrench } from "lucide-react";
import { chatApi, errMsg } from "../api/client";
import Markdown from "../components/common/Markdown";

type Msg = { role: "user" | "assistant"; content: string; tools?: string[]; error?: boolean };

const STORE_KEY = "chat_history";
// 이 챗봇은 마지막 질문만 보고 답함 (앞 대화 내용은 기억하지 않음)
const TOOL_LABEL: Record<string, string> = {
  today_picks: "오늘의 추천", analyze_stock: "종목 분석", my_portfolio: "투자종목", my_watchlist: "관심종목",
  market_overview: "시장 현황", track_record: "예측 적중률", upcoming_events: "이벤트 일정",
};
const SUGGESTIONS = [
  "오늘 국내 매수 추천 3개",
  "하락 확률 높은 종목 중 내가 가진 거 있어?",
  "내 투자종목 점검해줘",
  "엔비디아 어때?",
  "관심종목 보여줘",
  "오늘 시장 어때?",
  "이번 주 이벤트",
  "예측 적중률 알려줘",
  "도움말",
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
      const r = await chatApi.send([{ role: "user", content: q }]);
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
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>챗봇</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            질문의 키워드(종목명·매수·매도·투자종목·관심종목·시장·적중률·이벤트)로 앱 데이터를 조회해 답합니다 · 규칙 기반 (외부 AI 없음) · 예측은 참고용
          </p>
        </div>
        {msgs.length > 0 && (
          <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 10px" }} disabled={busy} onClick={() => setMsgs([])}>
            <Trash2 size={13} /> 대화 지우기
          </button>
        )}
      </div>

      <div className="card" style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 14, padding: 16 }}>
        {msgs.length === 0 && (
          <div style={{ margin: "auto", textAlign: "center", maxWidth: 640 }}>
            <Bot size={32} style={{ color: "var(--accent)", margin: "0 auto 8px" }} />
            <p style={{ color: "var(--text-secondary)", marginBottom: 14 }}>이렇게 물어보세요 (종목명은 정확히 — 예: 삼성전자, NVDA):</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, justifyContent: "center" }}>
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn btn-ghost" style={{ fontSize: 12, padding: "6px 12px", borderRadius: 999 }}
                  disabled={busy} onClick={() => send(s)}>{s}</button>
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
            데이터 조회 중... {elapsed}초 (보통 바로, 처음 조회하는 데이터는 몇 초)
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
          style={{ flex: 1, resize: "none", padding: "10px 12px", borderRadius: 10, border: "1px solid var(--border)",
            background: "var(--bg-card)", color: "var(--text-primary)", fontSize: 13, fontFamily: "inherit" }}
        />
        <button type="submit" className="btn btn-primary" disabled={busy || !input.trim()} style={{ alignSelf: "stretch" }}>
          <Send size={15} /> 보내기
        </button>
      </form>
    </div>
  );
}
