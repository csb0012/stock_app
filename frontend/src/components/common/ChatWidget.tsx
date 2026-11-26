import { useEffect, useRef, useState } from "react";
import { Bot, MessageCircle, Send, Trash2, User, Wrench, X } from "lucide-react";
import { chatApi, errMsg } from "../../api/client";
import Markdown from "./Markdown";

/** 화면 오른쪽 아래 떠 있는 챗봇 (규칙 기반 — 질문 키워드로 앱 데이터를 조회해 답함, 마지막 질문만 봄) */
type Msg = { role: "user" | "assistant"; content: string; tools?: string[]; error?: boolean };

const STORE_KEY = "chat_history";
const TOOL_LABEL: Record<string, string> = {
  today_picks: "오늘의 추천", analyze_stock: "종목 분석", my_portfolio: "투자종목", my_watchlist: "관심종목",
  market_overview: "시장 현황", track_record: "예측 적중률", upcoming_events: "이벤트 일정",
  themes: "테마", accumulation: "매집 탐지",
};
const SUGGESTIONS = [
  "오늘 국내 매수 추천 3개", "매집 종목", "오늘 테마", "내 투자종목 점검해줘",
  "엔비디아 어때?", "하락할 종목 있어?", "이번 주 이벤트", "도움말",
];

function load(): Msg[] {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
  } catch {
    return [];
  }
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>(load);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(msgs.slice(-40))); } catch { /* 저장 못 해도 화면은 그대로 */ }
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy, open]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

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
    <>
      {open && (
        <div role="dialog" aria-label="챗봇" className="chat-panel" style={{
          display: "flex", flexDirection: "column",
          background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14,
          boxShadow: "0 12px 40px rgba(0,0,0,0.25)", overflow: "hidden",
        }}>
          {/* 머리 */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
            <Bot size={17} style={{ color: "var(--accent)" }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontWeight: 700, fontSize: 14 }}>챗봇</p>
              <p style={{ fontSize: 10, color: "var(--text-muted)" }}>규칙 기반 · 앱 데이터를 조회해 답함 · 예측은 참고용</p>
            </div>
            {msgs.length > 0 && (
              <button className="btn btn-ghost" title="대화 지우기" style={{ padding: "4px 8px" }} disabled={busy} onClick={() => setMsgs([])}>
                <Trash2 size={13} />
              </button>
            )}
            <button className="btn btn-ghost" title="닫기 (Esc)" style={{ padding: "4px 8px" }} onClick={() => setOpen(false)}>
              <X size={14} />
            </button>
          </div>

          {/* 대화 */}
          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 12, padding: 14 }}>
            {msgs.length === 0 && (
              <div style={{ margin: "auto 0", textAlign: "center" }}>
                <p style={{ color: "var(--text-secondary)", fontSize: 12, marginBottom: 10 }}>이렇게 물어보세요 (종목명은 정확히 — 예: 삼성전자, NVDA)</p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, justifyContent: "center" }}>
                  {SUGGESTIONS.map((s) => (
                    <button key={s} className="btn btn-ghost" style={{ fontSize: 11, padding: "5px 10px", borderRadius: 999 }}
                      disabled={busy} onClick={() => send(s)}>{s}</button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} style={{ display: "flex", gap: 8, flexDirection: m.role === "user" ? "row-reverse" : "row", alignItems: "flex-start" }}>
                <div style={{ width: 24, height: 24, borderRadius: 12, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center",
                  background: m.role === "user" ? "var(--accent)" : "var(--bg-secondary)", color: m.role === "user" ? "var(--on-accent)" : "var(--accent)" }}>
                  {m.role === "user" ? <User size={13} /> : <Bot size={13} />}
                </div>
                <div style={{ maxWidth: "86%", minWidth: 0, overflowX: "auto", fontSize: 12.5, lineHeight: 1.6, padding: "8px 12px", borderRadius: 10,
                  background: m.role === "user" ? "color-mix(in srgb, var(--accent) 12%, transparent)" : m.error ? "color-mix(in srgb, var(--red) 8%, transparent)" : "var(--bg-secondary)",
                  color: m.error ? "var(--red)" : "var(--text-primary)", whiteSpace: m.role === "user" ? "pre-wrap" : undefined }}>
                  {m.role === "assistant" && !m.error ? <Markdown text={m.content} /> : m.content}
                  {m.tools && m.tools.length > 0 && (
                    <p style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "var(--text-muted)", marginTop: 6 }}>
                      <Wrench size={10} /> 조회: {[...new Set(m.tools)].map((t) => TOOL_LABEL[t] || t).join(" · ")}
                    </p>
                  )}
                </div>
              </div>
            ))}
            {busy && (
              <div style={{ display: "flex", gap: 8, alignItems: "center", color: "var(--text-muted)", fontSize: 12 }}>
                <Bot size={14} className="spin" style={{ color: "var(--accent)" }} /> 데이터 조회 중... {elapsed}초
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* 입력 */}
          <form onSubmit={(e) => { e.preventDefault(); send(input); }} style={{ display: "flex", gap: 6, padding: 10, borderTop: "1px solid var(--border)" }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(input); } }}
              placeholder="예: 삼성전자 어때? (Enter 전송)"
              rows={1}
              style={{ flex: 1, resize: "none", padding: "9px 10px", borderRadius: 8, border: "1px solid var(--border)",
                background: "var(--bg-primary)", color: "var(--text-primary)", fontSize: 13, fontFamily: "inherit" }}
            />
            <button type="submit" className="btn btn-primary" disabled={busy || !input.trim()} style={{ padding: "0 12px" }} title="보내기">
              <Send size={14} />
            </button>
          </form>
        </div>
      )}

      {/* 떠 있는 버튼 */}
      <button
        onClick={() => setOpen((o) => !o)}
        title={open ? "챗봇 닫기" : "챗봇 열기"}
        aria-label={open ? "챗봇 닫기" : "챗봇 열기"}
        className="chat-fab"
        style={{
          border: "none", cursor: "pointer", background: "var(--accent)", color: "var(--on-accent)",
          display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 6px 20px rgba(0,0,0,0.25)",
        }}
      >
        {open ? <X size={22} /> : <MessageCircle size={22} />}
      </button>
    </>
  );
}
