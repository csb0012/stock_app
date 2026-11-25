import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Mail, Smartphone } from "lucide-react";
import { authApi, errMsg, type Contact } from "../api/client";
import {
  AuthShell, Field, PasswordHint, passwordProblem, inputStyle, MethodTabs, ContactInput, contactOf, contactValid, useCooldown, type Method,
} from "../components/common/AuthForm";

/** 비밀번호 찾기: 인증해 둔 이메일 또는 휴대폰으로 6자리 코드 → 새 비밀번호 */
export default function ForgotPassword() {
  const navigate = useNavigate();
  const opts = useQuery({ queryKey: ["auth-options"], queryFn: () => authApi.options().then((r) => r.data), staleTime: 60_000 });
  const mail = !!opts.data?.mail_configured, sms = !!opts.data?.sms_configured;
  const [picked, setPicked] = useState<Method | null>(null);
  const method: Method = picked ?? (mail || !sms ? "email" : "phone");
  const [contact, setContact] = useState("");
  const [sentTo, setSentTo] = useState<Contact | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [cool, startCool] = useCooldown();
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const switchMethod = (m: Method) => { setPicked(m); setContact(""); setSentTo(null); setCode(""); setMsg(""); setError(""); };

  const send = async () => {
    setError(""); setBusy(true);
    try {
      const c = contactOf(method, contact);
      const r = await authApi.forgot(c);
      setSentTo(c); setMsg(r.data.message); startCool();
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
    <AuthShell title="비밀번호 찾기" subtitle="가입할 때(또는 마이페이지에서) 인증한 이메일·휴대폰으로 코드를 보냅니다">
      <form onSubmit={reset} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <MethodTabs value={method} onChange={switchMethod} mail={mail} sms={sms} />
        <Field label={method === "email" ? "이메일" : "휴대폰 번호"} hint={sentTo ? <span>{method === "email" ? "📧" : "📱"} {msg}</span> : undefined}>
          <div style={{ display: "flex", gap: 6 }}>
            <ContactInput method={method} value={contact} onChange={setContact} />
            <button type="button" className="btn btn-ghost" style={{ flexShrink: 0, fontSize: 12 }}
              disabled={!contactValid(method, contact) || busy || cool > 0} onClick={send}>
              {method === "email" ? <Mail size={13} /> : <Smartphone size={13} />}{cool > 0 ? `${cool}초` : sentTo ? "다시 받기" : "코드 받기"}
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
        이메일·휴대폰을 인증한 적이 없는 예전 계정은 코드가 가지 않습니다 — 서버(PC)에서
        <code> python create_admin.py --reset-password 아이디 새비밀번호</code> 로 바꾼 뒤, 마이페이지에서 본인인증을 해 두세요.
      </p>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", textAlign: "center", marginTop: 12 }}>
        <Link to="/login" style={{ color: "var(--accent)" }}>로그인으로 돌아가기</Link>
      </p>
    </AuthShell>
  );
}
