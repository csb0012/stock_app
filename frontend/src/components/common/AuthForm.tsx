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
