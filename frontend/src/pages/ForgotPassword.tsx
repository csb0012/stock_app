import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Mail } from "lucide-react";
import { authApi, errMsg } from "../api/client";
import { AuthShell, Field, PasswordHint, passwordProblem, inputStyle, EMAIL_RE } from "../components/common/AuthForm";

/** 비밀번호 찾기: 가입(인증)한 이메일로 6자리 코드 → 새 비밀번호 */
export default function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [cool, setCool] = useState(0);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (cool <= 0) return;
    const t = setTimeout(() => setCool(cool - 1), 1000);
    return () => clearTimeout(t);
  }, [cool]);

  const send = async () => {
    setError(""); setBusy(true);
    try {
      const r = await authApi.forgot(email.trim());
      setSentTo(email.trim().toLowerCase()); setMsg(r.data.message); setCool(60);
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };

  const canReset = sentTo && /^\d{6}$/.test(code) && pw && !passwordProblem(pw) && pw === pw2;
  const reset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canReset) return;
    setError(""); setBusy(true);
    try {
      const r = await authApi.reset(sentTo!, code, pw);
      navigate("/login", { state: { notice: `${r.data.message} (아이디: ${r.data.username})` } });
    } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };

  return (
    <AuthShell title="비밀번호 찾기" subtitle="가입할 때(또는 마이페이지에서) 인증한 이메일로 코드를 보냅니다">
      <form onSubmit={reset} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Field label="이메일" hint={sentTo ? <span>📧 {msg}</span> : undefined}>
          <div style={{ display: "flex", gap: 6 }}>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@naver.com" style={inputStyle} autoComplete="email" />
            <button type="button" className="btn btn-ghost" style={{ flexShrink: 0, fontSize: 12 }}
              disabled={!EMAIL_RE.test(email.trim()) || busy || cool > 0} onClick={send}>
              <Mail size={13} />{cool > 0 ? `${cool}초` : sentTo ? "다시 받기" : "코드 받기"}
            </button>
          </div>
        </Field>
        {sentTo && (
          <>
            <Field label="인증 코드 (6자리)">
              <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric"
                placeholder="000000" style={{ ...inputStyle, letterSpacing: 4, fontSize: 16 }} autoComplete="one-time-code" />
            </Field>
            <Field label="새 비밀번호" hint={<PasswordHint pw={pw} />}>
              <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} style={inputStyle} autoComplete="new-password" />
            </Field>
            <Field label="새 비밀번호 확인" hint={pw2 && pw !== pw2 ? <span style={{ color: "var(--red)" }}>✗ 위와 다름</span> : undefined}>
              <input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} style={inputStyle} autoComplete="new-password" />
            </Field>
          </>
        )}
        {error && <p role="alert" style={{ color: "var(--red)", fontSize: 13 }}>{error}</p>}
        {sentTo && (
          <button type="submit" className="btn btn-primary" disabled={!canReset || busy} style={{ justifyContent: "center", padding: 11 }}>
            {busy ? "처리 중..." : "비밀번호 바꾸기"}
          </button>
        )}
      </form>
      <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 12, lineHeight: 1.6 }}>
        이메일을 인증한 적이 없는 예전 계정은 메일이 가지 않습니다 — 서버(PC)에서
        <code> python create_admin.py --reset-password 아이디 새비밀번호</code> 로 바꾼 뒤, 마이페이지에서 이메일을 인증해 두세요.
      </p>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", textAlign: "center", marginTop: 12 }}>
        <Link to="/login" style={{ color: "var(--accent)" }}>로그인으로 돌아가기</Link>
      </p>
    </AuthShell>
  );
}
