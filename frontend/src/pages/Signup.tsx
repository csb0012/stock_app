import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Mail, Smartphone } from "lucide-react";
import { authApi, errMsg, type Contact } from "../api/client";
import { useAuthStore } from "../store/auth";
import {
  AuthShell, Field, PasswordHint, passwordProblem, inputStyle, MethodTabs, ContactInput, contactOf, contactValid,
  useCooldown, NICK_RE, type Method,
} from "../components/common/AuthForm";

/** 회원가입: 본인인증(이메일 또는 휴대폰 6자리) → 아이디·닉네임·비밀번호 → 가입하면 바로 로그인 */
export default function Signup() {
  const navigate = useNavigate();
  const { setToken } = useAuthStore();
  const opts = useQuery({ queryKey: ["auth-options"], queryFn: () => authApi.options().then((r) => r.data), staleTime: 60_000 });
  const mail = !!opts.data?.mail_configured, sms = !!opts.data?.sms_configured;
  const [picked, setPicked] = useState<Method | null>(null);
  const method: Method = picked ?? (mail || !sms ? "email" : "phone");
  const [contact, setContact] = useState("");
  const [invite, setInvite] = useState("");
  const inviteNeeded = !!opts.data?.invite_required;
  const inviteOk = !inviteNeeded || invite.replace(/[^A-Za-z0-9]/g, "").length === 12;
  const [code, setCode] = useState("");
  const [username, setUsername] = useState("");
  const [nickname, setNickname] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [sentTo, setSentTo] = useState<Contact | null>(null);
  const [cool, startCool] = useCooldown();
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const switchMethod = (m: Method) => { setPicked(m); setContact(""); setSentTo(null); setCode(""); setMsg(""); setError(""); };

  const sendCode = async () => {
    setError(""); setMsg(""); setBusy(true);
    try {
      const c = contactOf(method, contact);
      const r = await authApi.signupSendCode(c, inviteNeeded ? invite.trim() : undefined);
      setSentTo(c); setMsg(r.data.message); startCool();
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };

  const usernameOk = /^[A-Za-z0-9_]{3,20}$/.test(username);
  const nickOk = !nickname || NICK_RE.test(nickname);
  const canSubmit = sentTo && inviteOk && /^\d{6}$/.test(code) && usernameOk && nickOk && !passwordProblem(pw, username) && pw.length > 0 && pw === pw2;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setError(""); setBusy(true);
    try {
      const r = await authApi.register(username.trim(), pw, sentTo!, code, nickname.trim(), inviteNeeded ? invite.trim() : undefined);
      setToken(r.data.access_token);
      navigate(r.data.totp_setup_required ? "/setup-2fa" : "/");   // 2단계 필수 → QR 등록부터
    } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };

  const closed = opts.data && (!opts.data.signup_open || (!mail && !sms));
  return (
    <AuthShell title="회원가입" subtitle={inviteNeeded ? "초대 코드 + 이메일 또는 휴대폰 본인인증으로 가입합니다" : "이메일 또는 휴대폰으로 본인인증 후 가입합니다"}>
      {closed ? (
        <p data-testid="signup-closed" style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          {!opts.data.signup_open ? "지금은 회원가입을 받지 않습니다." : "메일·문자 발송 설정이 없어 회원가입을 할 수 없습니다 (관리자가 backend/.env 에 SMTP_* 또는 SMS_* 를 설정해야 함)."}
        </p>
      ) : (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {inviteNeeded && (
            <Field label="초대 코드" hint={invite && !inviteOk ? <span style={{ color: "var(--red)" }}>✗ 12글자 (예: K7QM-2XRA-9PWD)</span>
              : "관리자(앱 주인)에게 받은 1회용 코드 — 이 앱은 초대받은 사람만 가입할 수 있습니다"}>
              <input value={invite} onChange={(e) => setInvite(e.target.value.toUpperCase().slice(0, 16))} placeholder="XXXX-XXXX-XXXX"
                aria-label="초대 코드" style={{ ...inputStyle, letterSpacing: 2, fontFamily: "monospace" }} autoComplete="off" disabled={!!sentTo} />
            </Field>
          )}
          <MethodTabs value={method} onChange={switchMethod} mail={mail} sms={sms} />
          <Field label={method === "email" ? "이메일" : "휴대폰 번호"}
            hint={sentTo ? <span>{method === "email" ? "📧" : "📱"} {msg}{method === "email" ? " — 메일이 안 오면 스팸함 확인" : ""}</span>
              : method === "email" ? "네이버·Gmail 등 받을 수 있는 주소 (비밀번호 찾기에 씀)" : "문자로 6자리 인증번호를 보냅니다 (비밀번호 찾기·로그인에 씀)"}>
            <div style={{ display: "flex", gap: 6 }}>
              <ContactInput method={method} value={contact} onChange={setContact} />
              <button type="button" className="btn btn-ghost" style={{ flexShrink: 0, fontSize: 12 }}
                disabled={!contactValid(method, contact) || !inviteOk || busy || cool > 0} onClick={sendCode}>
                {method === "email" ? <Mail size={13} /> : <Smartphone size={13} />}{cool > 0 ? `${cool}초` : sentTo ? "다시 받기" : "인증 코드 받기"}
              </button>
            </div>
          </Field>
          {sentTo && (
            <>
              <Field label="인증 코드 (6자리)">
                <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric"
                  placeholder="000000" style={{ ...inputStyle, letterSpacing: 4, fontSize: 16 }} autoComplete="one-time-code" />
              </Field>
              <Field label="아이디" hint={username && !usernameOk ? <span style={{ color: "var(--red)" }}>✗ 영문·숫자·밑줄 3~20자</span> : "영문·숫자·밑줄 3~20자 (나중에 못 바꿈)"}>
                <input value={username} onChange={(e) => setUsername(e.target.value.trim())} style={inputStyle} autoComplete="username" />
              </Field>
              <Field label="닉네임 (선택)" hint={!nickOk ? <span style={{ color: "var(--red)" }}>✗ 한글·영문·숫자·밑줄 2~12자</span> : "화면 오른쪽 위에 보이는 이름. 비우면 아이디 — 마이페이지에서 언제든 바꿈"}>
                <input value={nickname} onChange={(e) => setNickname(e.target.value.trim())} style={inputStyle} aria-label="닉네임" maxLength={12} />
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
