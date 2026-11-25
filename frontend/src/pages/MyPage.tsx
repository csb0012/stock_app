import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail, KeyRound, ShieldCheck, UserX, UserCircle } from "lucide-react";
import { authApi, errMsg } from "../api/client";
import { useAuthStore } from "../store/auth";
import { Field, PasswordHint, passwordProblem, inputStyle, EMAIL_RE } from "../components/common/AuthForm";
import TotpSection from "../components/common/TotpSection";
import { toast } from "../components/common/Toast";

function Section({ icon: Icon, title, children, testid }: { icon: any; title: string; children: React.ReactNode; testid?: string }) {
  return (
    <section className="card" data-testid={testid} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h2 style={{ fontSize: 14, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}><Icon size={16} style={{ color: "var(--accent)" }} />{title}</h2>
      {children}
    </section>
  );
}

const fmtDate = (v?: string | number | null) => {
  if (!v) return "-";
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v + (String(v).endsWith("Z") || String(v).includes("+") ? "" : "Z"));
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
};

export default function MyPage() {
  const { data: me, isLoading, error } = useQuery({ queryKey: ["me"], queryFn: () => authApi.me().then((r) => r.data), staleTime: 0 });
  return (
    <div style={{ maxWidth: 720 }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>마이페이지</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>내 정보 · 이메일 인증 · 비밀번호 변경 · 2단계 인증 · 회원 탈퇴</p>
      </div>
      {isLoading && <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>}
      {error && <p style={{ color: "var(--red)" }}>{errMsg(error)}</p>}
      {me && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Section icon={UserCircle} title="내 정보" testid="my-info">
            <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", rowGap: 8, fontSize: 13 }}>
              <span style={{ color: "var(--text-muted)" }}>아이디</span><strong>{me.username}</strong>
              <span style={{ color: "var(--text-muted)" }}>이메일</span>
              <span>{me.email ? <>{me.email} <span className="badge badge-up">인증됨</span></> : <span style={{ color: "var(--yellow)" }}>없음 — 아래에서 인증하면 비밀번호 찾기를 쓸 수 있음</span>}</span>
              <span style={{ color: "var(--text-muted)" }}>2단계 인증</span><span>{me.totp_enabled ? <span className="badge badge-up">켜짐</span> : <span className="badge badge-neutral">꺼짐</span>}</span>
              <span style={{ color: "var(--text-muted)" }}>가입일</span><span>{fmtDate(me.created_at)}</span>
              <span style={{ color: "var(--text-muted)" }}>비밀번호 변경</span><span>{me.password_changed_at ? fmtDate(me.password_changed_at) : "바꾼 적 없음"}</span>
            </div>
          </Section>
          <EmailSection current={me.email} />
          <PasswordSection username={me.username} />
          <Section icon={ShieldCheck} title="2단계 인증 (Google Authenticator)"><TotpSection /></Section>
          <DeleteSection totp={me.totp_enabled} username={me.username} />
        </div>
      )}
    </div>
  );
}

function EmailSection({ current }: { current: string | null }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [cool, setCool] = useState(0);
  useEffect(() => {
    if (cool <= 0) return;
    const t = setTimeout(() => setCool(cool - 1), 1000);
    return () => clearTimeout(t);
  }, [cool]);
  const send = useMutation({ mutationFn: () => authApi.emailSendCode(email.trim()).then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => { setSentTo(email.trim().toLowerCase()); setCool(60); toast(d.message, "info"); } });
  const verify = useMutation({ mutationFn: () => authApi.emailVerify(sentTo!, code).then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => { toast(d.message, "info"); setSentTo(null); setCode(""); setEmail(""); qc.invalidateQueries({ queryKey: ["me"] }); } });
  const err = send.error || verify.error;
  return (
    <Section icon={Mail} title={current ? "이메일 변경" : "이메일 인증"} testid="email-section">
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
        {current ? `지금: ${current}. 바꾸려면 새 주소로 인증하세요.` : "비밀번호를 잊었을 때 이 주소로 코드를 받습니다. 아이디 대신 이메일로 로그인할 수도 있습니다."}
      </p>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@naver.com" style={{ ...inputStyle, flex: 1, minWidth: 200 }} aria-label="이메일" />
        <button className="btn btn-ghost" style={{ fontSize: 12 }} disabled={!EMAIL_RE.test(email.trim()) || send.isPending || cool > 0} onClick={() => send.mutate()}>
          {cool > 0 ? `${cool}초` : sentTo ? "다시 받기" : "인증 코드 받기"}
        </button>
      </div>
      {sentTo && (
        <div style={{ display: "flex", gap: 6 }}>
          <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" placeholder="6자리"
            aria-label="이메일 인증 코드" style={{ ...inputStyle, width: 140, letterSpacing: 3 }} />
          <button className="btn btn-primary" disabled={!/^\d{6}$/.test(code) || verify.isPending} onClick={() => verify.mutate()}>확인</button>
        </div>
      )}
      {err && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(err)}</p>}
    </Section>
  );
}

function PasswordSection({ username }: { username: string }) {
  const { replaceToken } = useAuthStore();
  const qc = useQueryClient();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const change = useMutation({ mutationFn: () => authApi.changePassword(cur, pw).then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => {
      replaceToken(d.access_token);   // 지금 화면은 계속 로그인, 다른 기기는 끊김
      setCur(""); setPw(""); setPw2("");
      toast(d.message, "info");
      qc.invalidateQueries({ queryKey: ["me"] });
    } });
  const ok = cur && pw && !passwordProblem(pw, username) && pw === pw2 && pw !== cur;
  return (
    <Section icon={KeyRound} title="비밀번호 변경" testid="password-section">
      <Field label="현재 비밀번호"><input type="password" value={cur} onChange={(e) => setCur(e.target.value)} style={inputStyle} autoComplete="current-password" /></Field>
      <Field label="새 비밀번호" hint={<PasswordHint pw={pw} username={username} />}>
        <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} style={inputStyle} autoComplete="new-password" />
      </Field>
      <Field label="새 비밀번호 확인" hint={pw2 && pw !== pw2 ? <span style={{ color: "var(--red)" }}>✗ 위와 다름</span> : pw && pw === cur ? <span style={{ color: "var(--red)" }}>✗ 지금 비밀번호와 같음</span> : undefined}>
        <input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} style={inputStyle} autoComplete="new-password" />
      </Field>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <button className="btn btn-primary" disabled={!ok || change.isPending} onClick={() => change.mutate()}>비밀번호 바꾸기</button>
        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>바꾸면 다른 기기·브라우저의 로그인은 끊깁니다</span>
      </div>
      {change.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(change.error)}</p>}
    </Section>
  );
}

function DeleteSection({ totp, username }: { totp: boolean; username: string }) {
  const navigate = useNavigate();
  const { logout } = useAuthStore();
  const [pw, setPw] = useState("");
  const [code, setCode] = useState("");
  const [typed, setTyped] = useState("");
  const del = useMutation({ mutationFn: () => authApi.deleteAccount(pw, totp ? code : undefined), meta: { inlineError: true },
    // 먼저 로그인 화면으로 옮긴 뒤 로그아웃 (먼저 로그아웃하면 보호된 화면이 안내 문구 없이 /login 으로 보내 버림)
    onSuccess: () => { navigate("/login", { replace: true, state: { notice: "탈퇴했습니다 — 관심종목·투자종목도 지웠습니다" } }); setTimeout(logout, 0); } });
  const ok = pw && typed === username && (!totp || /^\d{6}$/.test(code));
  return (
    <Section icon={UserX} title="회원 탈퇴" testid="delete-section">
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>계정과 내 관심종목·투자종목이 지워지고 되돌릴 수 없습니다.</p>
      <Field label={`확인을 위해 아이디(${username})를 입력`}><input value={typed} onChange={(e) => setTyped(e.target.value)} style={inputStyle} aria-label="탈퇴 확인 아이디" /></Field>
      <Field label="비밀번호"><input type="password" value={pw} onChange={(e) => setPw(e.target.value)} style={inputStyle} aria-label="탈퇴 비밀번호" autoComplete="current-password" /></Field>
      {totp && (
        <Field label="2단계 인증 코드"><input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" style={{ ...inputStyle, width: 140 }} aria-label="탈퇴 2단계 코드" /></Field>
      )}
      <button className="btn btn-ghost" style={{ color: "var(--red)", alignSelf: "flex-start" }} disabled={!ok || del.isPending}
        onClick={() => { if (window.confirm("정말 탈퇴할까요? 되돌릴 수 없습니다.")) del.mutate(); }}>탈퇴하기</button>
      {del.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(del.error)}</p>}
    </Section>
  );
}
