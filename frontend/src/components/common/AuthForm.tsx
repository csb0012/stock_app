import { useEffect, useState } from "react";
import { TrendingUp } from "lucide-react";
import ThemeToggle from "./ThemeToggle";

/** 로그인·회원가입·비밀번호 찾기 공통 틀 (가운데 카드) */
export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-primary)", padding: 16 }}>
      <div style={{ position: "fixed", top: 16, right: 16 }}><ThemeToggle compact /></div>
      <div style={{ width: 400, maxWidth: "100%" }}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <TrendingUp size={26} style={{ color: "var(--accent)" }} />
            <span style={{ fontSize: 21, fontWeight: 700, color: "var(--text-primary)" }}>StockApp</span>
          </div>
          <h1 style={{ fontSize: 16, fontWeight: 700 }}>{title}</h1>
          {subtitle && <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginTop: 4 }}>{subtitle}</p>}
        </div>
        <div className="card">{children}</div>
      </div>
    </div>
  );
}

export const inputStyle: React.CSSProperties = {
  width: "100%", padding: "9px 11px", background: "var(--bg-secondary)", border: "1px solid var(--border)",
  borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none", minWidth: 0,
};

export function Field({ label, hint, children }: { label: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>{label}</span>
      {children}
      {hint && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{hint}</span>}
    </label>
  );
}

/** 비밀번호 규칙 (서버 check_password 와 같음) — 입력하는 동안 바로 안내 */
export function passwordProblem(pw: string, username = ""): string | null {
  if (!pw) return null;
  if (pw.length < 8) return "8자 이상";
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return "영문과 숫자를 함께";
  if (username && pw.toLowerCase().includes(username.toLowerCase())) return "아이디를 넣을 수 없음";
  return null;
}

export function PasswordHint({ pw, username }: { pw: string; username?: string }) {
  const p = passwordProblem(pw, username);
  if (!pw) return <span>8자 이상, 영문+숫자. 다른 사이트와 다른 비밀번호를 쓰세요</span>;
  return p ? <span style={{ color: "var(--red)" }}>✗ {p}</span> : <span style={{ color: "var(--green)" }}>✓ 사용 가능</span>;
}

export const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

// ---------------- 본인인증 수단: 이메일 또는 휴대폰 ----------------

export type Method = "email" | "phone";
export const PHONE_RE = /^01[016789]\d{7,8}$/;
const digits = (v: string) => v.replace(/\D/g, "");

/** 입력하는 동안 010-1234-5678 모양으로 */
export function formatPhone(v: string): string {
  const d = digits(v).slice(0, 11);
  if (d.length < 4) return d;
  if (d.length < 8) return `${d.slice(0, 3)}-${d.slice(3)}`;
  if (d.length === 10) return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
}

export const contactValid = (m: Method, v: string) => (m === "email" ? EMAIL_RE.test(v.trim()) : PHONE_RE.test(digits(v)));
export const contactOf = (m: Method, v: string) => (m === "email" ? { email: v.trim().toLowerCase() } : { phone: digits(v) });

/** [이메일로] [휴대폰으로] 고르기 — 서버에 발송 설정이 없는 쪽은 눌리지 않음 */
export function MethodTabs({ value, onChange, mail, sms }: { value: Method; onChange: (m: Method) => void; mail: boolean; sms: boolean }) {
  const tab = (m: Method, label: string, ok: boolean) => (
    <button type="button" role="tab" aria-selected={value === m} disabled={!ok} onClick={() => onChange(m)}
      title={ok ? undefined : m === "email" ? "메일 발송 설정이 없음 (SMTP_*)" : "문자 발송 설정이 없음 (SMS_*)"}
      style={{ flex: 1, padding: "8px 0", fontSize: 12.5, fontWeight: value === m ? 700 : 500, borderRadius: 6, border: "none", cursor: ok ? "pointer" : "not-allowed",
        background: value === m ? "var(--bg-card)" : "transparent", color: !ok ? "var(--text-muted)" : value === m ? "var(--accent)" : "var(--text-secondary)",
        boxShadow: value === m ? "0 1px 3px rgba(0,0,0,.15)" : "none" }}>
      {label}{!ok && " (준비 안 됨)"}
    </button>
  );
  return (
    <div role="tablist" aria-label="본인인증 방법" style={{ display: "flex", gap: 4, padding: 3, borderRadius: 8, background: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
      {tab("email", "이메일로 인증", mail)}
      {tab("phone", "휴대폰으로 인증", sms)}
    </div>
  );
}

/** 이메일 주소 또는 휴대폰 번호 입력칸 */
export function ContactInput({ method, value, onChange }: { method: Method; value: string; onChange: (v: string) => void }) {
  return method === "email" ? (
    <input type="email" value={value} onChange={(e) => onChange(e.target.value)} placeholder="you@naver.com" style={inputStyle} autoComplete="email" aria-label="이메일" />
  ) : (
    <input type="tel" value={value} onChange={(e) => onChange(formatPhone(e.target.value))} placeholder="010-1234-5678" style={inputStyle}
      autoComplete="tel" inputMode="numeric" aria-label="휴대폰 번호" />
  );
}

/** 다시 받기 대기 시간(초) — [남은 초, 시작] */
export function useCooldown(): [number, (s?: number) => void] {
  const [cool, setCool] = useState(0);
  useEffect(() => {
    if (cool <= 0) return;
    const t = setTimeout(() => setCool(cool - 1), 1000);
    return () => clearTimeout(t);
  }, [cool]);
  return [cool, (s = 60) => setCool(s)];
}

/** 닉네임 규칙 (서버 _check_nickname 과 같음) */
export const NICK_RE = /^[가-힣A-Za-z0-9_]{2,12}$/;
