import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import { authApi, errMsg } from "../api/client";
import { useAuthStore } from "../store/auth";
import { AuthShell, Field, PasswordHint, passwordProblem, inputStyle, EMAIL_RE } from "../components/common/AuthForm";

/** 회원가입: 이메일 6자리 인증 → 아이디·비밀번호 → 가입하면 바로 로그인 */
export default function Signup() {
  const navigate = useNavigate();
  const { setToken } = useAuthStore();
  const opts = useQuery({ queryKey: ["auth-options"], queryFn: () => authApi.options().then((r) => r.data), staleTime: 60_000 });
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [username, setUsername] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [cool, setCool] = useState(0);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (cool <= 0) return;
    const t = setTimeout(() => setCool(cool - 1), 1000);
    return () => clearTimeout(t);
  }, [cool]);

  const sendCode = async () => {
    setError(""); setMsg(""); setBusy(true);
    try {
      const r = await authApi.signupSendCode(email.trim());
      setSentTo(email.trim().toLowerCase()); setMsg(r.data.message); setCool(60);
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };

  const usernameOk = /^[A-Za-z0-9_]{3,20}$/.test(username);
  const canSubmit = sentTo && /^\d{6}$/.test(code) && usernameOk && !passwordProblem(pw, username) && pw.length > 0 && pw === pw2;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setError(""); setBusy(true);
    try {
      const r = await authApi.register(username.trim(), pw, sentTo!, code);
      setToken(r.data.access_token);
      navigate("/");
    } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };

  const closed = opts.data && (!opts.data.signup_open || !opts.data.mail_configured);
  return (
    <AuthShell title="회원가입" subtitle="이메일 인증 후 가입합니다">
      {closed ? (
        <p data-testid="signup-closed" style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          {!opts.data.signup_open ? "지금은 회원가입을 받지 않습니다." : "메일 발송 설정이 없어 회원가입을 할 수 없습니다 (관리자가 backend/.env 에 SMTP 를 설정해야 함)."}
        </p>
      ) : (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Field label="이메일" hint={sentTo ? <span>📧 {msg} — 메일이 안 오면 스팸함 확인</span> : "네이버·Gmail 등 받을 수 있는 주소 (비밀번호 찾기에 씀)"}>
            <div style={{ display: "flex", gap: 6 }}>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@naver.com" style={inputStyle} autoComplete="email" />
              <button type="button" className="btn btn-ghost" style={{ flexShrink: 0, fontSize: 12 }}
                disabled={!EMAIL_RE.test(email.trim()) || busy || cool > 0} onClick={sendCode}>
                <Mail size={13} />{cool > 0 ? `${cool}초` : sentTo ? "다시 받기" : "인증 코드 받기"}
              </button>
            </div>
          </Field>
          {sentTo && (
            <>
              <Field label="인증 코드 (6자리)">
                <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric"
                  placeholder="000000" style={{ ...inputStyle, letterSpacing: 4, fontSize: 16 }} autoComplete="one-time-code" />
              </Field>
              <Field label="아이디" hint={username && !usernameOk ? <span style={{ color: "var(--red)" }}>✗ 영문·숫자·밑줄 3~20자</span> : "영문·숫자·밑줄 3~20자"}>
                <input value={username} onChange={(e) => setUsername(e.target.value.trim())} style={inputStyle} autoComplete="username" />
              </Field>
              <Field label="비밀번호" hint={<PasswordHint pw={pw} username={username} />}>
                <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} style={inputStyle} autoComplete="new-password" />
              </Field>
              <Field label="비밀번호 확인" hint={pw2 && pw !== pw2 ? <span style={{ color: "var(--red)" }}>✗ 위와 다름</span> : undefined}>
                <input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} style={inputStyle} autoComplete="new-password" />
              </Field>
            </>
          )}
          {error && <p role="alert" style={{ color: "var(--red)", fontSize: 13 }}>{error}</p>}
          <button type="submit" className="btn btn-primary" disabled={!canSubmit || busy} style={{ justifyContent: "center", padding: 11 }}>
            {busy ? "처리 중..." : "가입하기"}
          </button>
        </form>
      )}
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", textAlign: "center", marginTop: 14 }}>
        이미 계정이 있나요? <Link to="/login" style={{ color: "var(--accent)" }}>로그인</Link>
      </p>
    </AuthShell>
  );
}
