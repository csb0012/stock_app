import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Mail, KeyRound, ShieldCheck, UserX, UserCircle, Smartphone, BadgeCheck, MonitorSmartphone, Download, AlertTriangle, Pencil, Crown,
} from "lucide-react";
import { authApi, errMsg, portfolioApi, watchlistApi } from "../api/client";
import { useAuthStore } from "../store/auth";
import {
  Field, PasswordHint, passwordProblem, inputStyle, EMAIL_RE, PHONE_RE, formatPhone, useCooldown, NICK_RE,
} from "../components/common/AuthForm";
import TotpSection from "../components/common/TotpSection";
import { toast } from "../components/common/Toast";
import { KIND_LABEL, deviceName } from "../components/common/accountEvents";

const SECTIONS = [
  ["profile", "프로필"], ["verify", "본인인증"], ["password", "비밀번호"], ["totp", "2단계 인증"],
  ["devices", "로그인 기록"], ["data", "내 데이터"], ["leave", "회원 탈퇴"],
] as const;

function Section({ id, icon: Icon, title, desc, children, testid }: { id: string; icon: any; title: string; desc?: string; children: React.ReactNode; testid?: string }) {
  return (
    <section id={`my-${id}`} className="card" data-testid={testid} style={{ display: "flex", flexDirection: "column", gap: 12, scrollMarginTop: 70 }}>
      <div>
        <h2 style={{ fontSize: 14, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}><Icon size={16} style={{ color: "var(--accent)" }} />{title}</h2>
        {desc && <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{desc}</p>}
      </div>
      {children}
    </section>
  );
}

const fmtDate = (v?: string | number | null, withTime = true) => {
  if (!v) return "-";
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v + (String(v).endsWith("Z") || String(v).includes("+") ? "" : "Z"));
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString("ko-KR", withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "long" });
};

const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => authApi.me().then((r) => r.data), staleTime: 0 });

export default function MyPage() {
  const { data: me, isLoading, error } = useMe();
  const go = (id: string) => document.getElementById(`my-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  return (
    <div style={{ maxWidth: 760 }}>
      <div style={{ marginBottom: 14 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>마이페이지</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>프로필 · 본인인증(이메일/휴대폰) · 보안 · 내 데이터</p>
      </div>
      {isLoading && <p style={{ color: "var(--text-muted)" }}>불러오는 중...</p>}
      {error && <p style={{ color: "var(--red)" }}>{errMsg(error)}</p>}
      {me && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <ProfileCard me={me} />
          <nav aria-label="마이페이지 메뉴" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {SECTIONS.map(([id, label]) => (
              <button key={id} className="btn btn-ghost" style={{ fontSize: 12, padding: "4px 11px", borderRadius: 999 }} onClick={() => go(id)}>{label}</button>
            ))}
          </nav>
          {me.is_admin && (
            <Link to="/admin" data-testid="admin-link" className="card" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", color: "inherit",
              borderColor: "var(--accent)" }}>
              <Crown size={16} style={{ color: "var(--accent)" }} />
              <span style={{ fontSize: 13 }}><strong>관리자 페이지</strong> — 회원 · 초대 코드 · 보안 기록은 관리자 페이지에서 봅니다</span>
            </Link>
          )}
          <NicknameSection me={me} />
          <VerifySection me={me} />
          <PasswordSection username={me.username} />
          <Section id="totp" icon={ShieldCheck} title="2단계 인증 (Google Authenticator)" desc="비밀번호가 새어도 휴대폰 앱의 6자리 코드 없이는 로그인 못 하게 합니다"><TotpSection /></Section>
          <DevicesSection />
          <DataSection />
          <DeleteSection totp={me.totp_enabled} username={me.username} />
        </div>
      )}
    </div>
  );
}

/** 맨 위 요약: 이름 · 아이디 · 인증 상태 · 가입일 */
function ProfileCard({ me }: { me: any }) {
  const verified = !!(me.email || me.phone);
  const chip = (ok: boolean, label: string) => (
    <span className={`badge ${ok ? "badge-up" : "badge-neutral"}`} style={{ fontSize: 11 }}>{ok ? "✓ " : ""}{label}</span>
  );
  return (
    <div className="card" data-testid="my-info" style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <div aria-hidden style={{ width: 54, height: 54, borderRadius: 27, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        background: "color-mix(in srgb, var(--accent) 16%, transparent)", color: "var(--accent)", fontSize: 22, fontWeight: 700 }}>
        {(me.display_name || me.username).slice(0, 1).toUpperCase()}
      </div>
      <div style={{ flex: 1, minWidth: 200, display: "flex", flexDirection: "column", gap: 5 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
          <strong style={{ fontSize: 17 }}>{me.display_name || me.username}</strong>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>아이디 {me.username}</span>
        </div>
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
          {chip(!!me.email, "이메일")}{chip(!!me.phone, "휴대폰")}{chip(!!me.totp_enabled, "2단계 인증")}
        </div>
        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>가입일 {fmtDate(me.created_at, false)}</span>
      </div>
      {!verified && (
        <p data-testid="verify-warning" style={{ width: "100%", fontSize: 12, color: "var(--yellow)", display: "flex", gap: 6, alignItems: "center" }}>
          <AlertTriangle size={14} /> 본인인증(이메일 또는 휴대폰)을 하지 않았습니다 — 비밀번호를 잊으면 '비밀번호 찾기'를 쓸 수 없습니다
        </p>
      )}
    </div>
  );
}

function NicknameSection({ me }: { me: any }) {
  const qc = useQueryClient();
  const [nick, setNick] = useState(me.nickname || "");
  const save = useMutation({ mutationFn: () => authApi.updateProfile(nick.trim()).then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => { toast(d.message, "info"); qc.invalidateQueries({ queryKey: ["me"] }); } });
  const v = nick.trim();
  const ok = (!v || NICK_RE.test(v)) && v !== (me.nickname || "");
  return (
    <Section id="profile" icon={Pencil} title="닉네임" desc="화면 오른쪽 위에 보이는 이름입니다. 로그인은 계속 아이디(또는 인증한 이메일·휴대폰)로 합니다" testid="nickname-section">
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <input value={nick} onChange={(e) => setNick(e.target.value)} placeholder={`비우면 아이디(${me.username})`} maxLength={12}
          aria-label="닉네임" style={{ ...inputStyle, flex: 1, minWidth: 180 }} />
        <button className="btn btn-primary" disabled={!ok || save.isPending} onClick={() => save.mutate()}>{v ? "저장" : "지우기"}</button>
      </div>
      <span style={{ fontSize: 11.5, color: v && !NICK_RE.test(v) ? "var(--red)" : "var(--text-muted)" }}>
        {v && !NICK_RE.test(v) ? "✗ " : ""}한글·영문·숫자·밑줄 2~12자, 띄어쓰기 안 됨, 다른 사람과 겹치면 안 됨
      </span>
      {save.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(save.error)}</p>}
    </Section>
  );
}

/** 본인인증 수단 — 이메일·휴대폰 중 하나 이상. 등록/변경(코드 확인)·삭제(비밀번호, 하나는 남아야) */
function VerifySection({ me }: { me: any }) {
  const opts = useQuery({ queryKey: ["auth-options"], queryFn: () => authApi.options().then((r) => r.data), staleTime: 60_000 });
  const both = !!(me.email && me.phone);
  return (
    <Section id="verify" icon={BadgeCheck} title="본인인증 (이메일 · 휴대폰)" testid="verify-section"
      desc="둘 중 하나만 인증해도 됩니다. 인증한 수단으로 비밀번호 찾기·로그인을 할 수 있습니다">
      <ContactRow kind="email" current={me.email} ready={!!opts.data?.mail_configured} canRemove={both} />
      <ContactRow kind="phone" current={me.phone} ready={!!opts.data?.sms_configured} canRemove={both} />
    </Section>
  );
}

function ContactRow({ kind, current, ready, canRemove }: { kind: "email" | "phone"; current: string | null; ready: boolean; canRemove: boolean }) {
  const qc = useQueryClient();
  const isEmail = kind === "email";
  const label = isEmail ? "이메일" : "휴대폰";
  const [mode, setMode] = useState<"" | "edit" | "remove">("");
  const [value, setValue] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [cool, startCool] = useCooldown();
  const close = () => { setMode(""); setValue(""); setSentTo(null); setCode(""); setPw(""); };
  const target = isEmail ? value.trim().toLowerCase() : value.replace(/\D/g, "");
  const valid = isEmail ? EMAIL_RE.test(value.trim()) : PHONE_RE.test(target);
  const send = useMutation({ mutationFn: () => (isEmail ? authApi.emailSendCode(target) : authApi.phoneSendCode(target)).then((r) => r.data),
    meta: { inlineError: true }, onSuccess: (d) => { setSentTo(target); startCool(); toast(d.message, "info"); } });
  const verify = useMutation({ mutationFn: () => (isEmail ? authApi.emailVerify(sentTo!, code) : authApi.phoneVerify(sentTo!, code)).then((r) => r.data),
    meta: { inlineError: true }, onSuccess: (d) => { toast(d.message, "info"); close(); qc.invalidateQueries({ queryKey: ["me"] }); } });
  const remove = useMutation({ mutationFn: () => authApi.removeContact(kind, pw).then((r) => r.data),
    meta: { inlineError: true }, onSuccess: (d) => { toast(d.message, "info"); close(); qc.invalidateQueries({ queryKey: ["me"] }); } });
  const err = send.error || verify.error || remove.error;
  const Icon = isEmail ? Mail : Smartphone;
  return (
    <div data-testid={`${kind}-row`} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <Icon size={15} style={{ color: "var(--text-muted)" }} />
        <span style={{ fontSize: 12.5, color: "var(--text-secondary)", width: 44 }}>{label}</span>
        <span style={{ flex: 1, fontSize: 13, minWidth: 140 }}>
          {current ? <>{current} <span className="badge badge-up" style={{ fontSize: 10.5 }}>인증됨</span></> : <span style={{ color: "var(--text-muted)" }}>등록 안 함</span>}
        </span>
        {mode === "" && (
          <>
            <button className="btn btn-ghost" style={{ fontSize: 12, padding: "4px 10px" }} disabled={!ready} title={ready ? undefined : isEmail ? "서버에 메일 발송 설정(SMTP_*)이 없음" : "서버에 문자 발송 설정(SMS_*)이 없음"}
              onClick={() => setMode("edit")}>{current ? "변경" : "등록"}</button>
            {current && (
              <button className="btn btn-ghost" style={{ fontSize: 12, padding: "4px 10px", color: "var(--red)" }} disabled={!canRemove}
                title={canRemove ? undefined : "본인인증 수단이 하나는 남아야 합니다"} onClick={() => setMode("remove")}>삭제</button>
            )}
          </>
        )}
        {mode !== "" && <button className="btn btn-ghost" style={{ fontSize: 12, padding: "4px 10px" }} onClick={close}>취소</button>}
      </div>
      {!ready && mode === "" && !current && (
        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{isEmail ? "관리자가 메일 발송(SMTP_*)을 설정하면 쓸 수 있습니다" : "관리자가 문자 발송(SMS_*, 솔라피)을 설정하면 쓸 수 있습니다"}</span>
      )}
      {mode === "edit" && (
        <>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <input type={isEmail ? "email" : "tel"} value={value} inputMode={isEmail ? undefined : "numeric"}
              onChange={(e) => setValue(isEmail ? e.target.value : formatPhone(e.target.value))}
              placeholder={isEmail ? "you@naver.com" : "010-1234-5678"} aria-label={isEmail ? "새 이메일" : "새 휴대폰 번호"} style={{ ...inputStyle, flex: 1, minWidth: 200 }} />
            <button className="btn btn-ghost" style={{ fontSize: 12 }} disabled={!valid || send.isPending || cool > 0} onClick={() => send.mutate()}>
              {cool > 0 ? `${cool}초` : sentTo ? "다시 받기" : "인증 코드 받기"}
            </button>
          </div>
          {sentTo && (
            <div style={{ display: "flex", gap: 6 }}>
              <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" placeholder="6자리"
                aria-label={`${label} 인증 코드`} style={{ ...inputStyle, width: 140, letterSpacing: 3 }} autoComplete="one-time-code" />
              <button className="btn btn-primary" disabled={!/^\d{6}$/.test(code) || verify.isPending} onClick={() => verify.mutate()}>확인</button>
            </div>
          )}
        </>
      )}
      {mode === "remove" && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="비밀번호 확인" aria-label={`${label} 삭제 비밀번호`}
            style={{ ...inputStyle, flex: 1, minWidth: 180 }} autoComplete="current-password" />
          <button className="btn btn-ghost" style={{ color: "var(--red)" }} disabled={!pw || remove.isPending} onClick={() => remove.mutate()}>{label} 삭제</button>
        </div>
      )}
      {err && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(err)}</p>}
    </div>
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
      qc.invalidateQueries({ queryKey: ["account-activity"] });
    } });
  const ok = cur && pw && !passwordProblem(pw, username) && pw === pw2 && pw !== cur;
  return (
    <Section id="password" icon={KeyRound} title="비밀번호 변경" testid="password-section">
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


function DevicesSection() {
  const qc = useQueryClient();
  const { replaceToken } = useAuthStore();
  const act = useQuery({ queryKey: ["account-activity"], queryFn: () => authApi.activity(30).then((r) => r.data), staleTime: 0 });
  const out = useMutation({ mutationFn: () => authApi.logoutAll().then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => { replaceToken(d.access_token); toast(d.message, "info"); qc.invalidateQueries({ queryKey: ["account-activity"] }); } });
  const items: any[] = act.data?.items || [];
  return (
    <Section id="devices" icon={MonitorSmartphone} title="로그인 기기 · 최근 활동" testid="devices-section"
      desc="내가 하지 않은 로그인이 보이면 비밀번호를 바꾸고 '모든 기기에서 로그아웃'을 누르세요">
      {act.data?.recent_failures > 0 && (
        <p data-testid="fail-warning" style={{ fontSize: 12.5, color: "var(--yellow)", display: "flex", gap: 6, alignItems: "center" }}>
          <AlertTriangle size={14} /> 최근 7일 동안 내 계정으로 로그인 실패 {act.data.recent_failures}번
        </p>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <button className="btn btn-ghost" disabled={out.isPending}
          onClick={() => { if (window.confirm("이 화면만 빼고 다른 모든 기기·브라우저에서 로그아웃할까요?")) out.mutate(); }}>모든 기기에서 로그아웃</button>
        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>지금 이 화면은 그대로 로그인 상태로 남습니다</span>
      </div>
      {out.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(out.error)}</p>}
      {act.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(act.error)}</p>}
      {act.data && items.length === 0 && <p style={{ fontSize: 12.5, color: "var(--text-muted)" }}>아직 기록이 없습니다 (이번 업데이트 이후의 로그인부터 남습니다)</p>}
      {items.length > 0 && (
        <div style={{ overflowX: "auto", maxHeight: 320, overflowY: "auto" }}>
          <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }} data-testid="activity-table">
            <thead>
              <tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
                <th style={{ padding: "6px 8px", fontWeight: 500 }}>시각</th><th style={{ padding: "6px 8px", fontWeight: 500 }}>활동</th>
                <th style={{ padding: "6px 8px", fontWeight: 500 }}>IP</th><th style={{ padding: "6px 8px", fontWeight: 500 }}>기기</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e, i) => (
                <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>{fmtDate(e.at)}</td>
                  <td style={{ padding: "6px 8px", color: e.ok ? "var(--text-primary)" : "var(--red)" }}>
                    {KIND_LABEL[e.kind] || e.kind}{e.detail ? <span style={{ color: "var(--text-muted)" }}> · {e.detail}</span> : null}
                  </td>
                  <td style={{ padding: "6px 8px", whiteSpace: "nowrap", fontFamily: "monospace" }}>{e.ip || "-"}</td>
                  <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }} title={e.user_agent || ""}>{deviceName(e.user_agent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

/** 표 → CSV 파일 (엑셀에서 한글이 안 깨지게 BOM) */
function downloadCsv(name: string, header: string[], rows: (string | number | null | undefined)[][]) {
  const esc = (v: any) => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const text = "﻿" + [header, ...rows].map((r) => r.map(esc).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function DataSection() {
  const today = new Date().toISOString().slice(0, 10);
  const wl = useMutation({ mutationFn: () => watchlistApi.list().then((r) => r.data),
    onSuccess: (rows: any[]) => downloadCsv(`watchlist-${today}.csv`, ["시장", "종목코드", "종목명", "목표 매수가", "메모", "추가한 날"],
      rows.map((i) => [i.market, i.symbol, i.name, i.target_price, i.memo, i.added_at?.slice(0, 10)])) });
  const pf = useMutation({ mutationFn: () => portfolioApi.list().then((r) => r.data),
    onSuccess: (rows: any[]) => downloadCsv(`portfolio-${today}.csv`, ["시장", "종목코드", "종목명", "수량", "평단가"],
      rows.map((i) => [i.market, i.symbol, i.name, i.quantity, i.avg_price])) });
  return (
    <Section id="data" icon={Download} title="내 데이터 내려받기" desc="엑셀에서 열 수 있는 CSV 파일로 받습니다 (백업·다른 앱으로 옮길 때)" testid="data-section">
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn btn-ghost" disabled={wl.isPending} onClick={() => wl.mutate()}><Download size={13} /> 관심종목 CSV</button>
        <button className="btn btn-ghost" disabled={pf.isPending} onClick={() => pf.mutate()}><Download size={13} /> 투자종목 CSV</button>
      </div>
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
    onSuccess: () => { navigate("/login", { replace: true, state: { notice: "탈퇴했습니다 — 관심종목·투자종목·모의투자 기록도 지웠습니다" } }); setTimeout(logout, 0); } });
  const ok = pw && typed === username && (!totp || /^\d{6}$/.test(code));
  return (
    <Section id="leave" icon={UserX} title="회원 탈퇴" testid="delete-section">
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>계정과 내 관심종목·투자종목·활동 기록이 지워지고 되돌릴 수 없습니다. 필요하면 위에서 먼저 CSV 로 받아 두세요.</p>
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
