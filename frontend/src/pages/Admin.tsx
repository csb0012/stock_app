import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Crown, Users, Ticket, ShieldAlert, Landmark, UserSearch, AlertTriangle } from "lucide-react";
import { adminApi, errMsg } from "../api/client";
import { InvitePanel, MemberPanel, th, td, when } from "../components/common/AdminPanels";
import { KIND_LABEL, deviceName } from "../components/common/accountEvents";

function Card({ icon: Icon, title, desc, children, testid }: { icon: any; title: string; desc?: string; children: React.ReactNode; testid?: string }) {
  return (
    <section className="card" data-testid={testid} style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
      <div>
        <h2 style={{ fontSize: 14, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}><Icon size={16} style={{ color: "var(--accent)" }} />{title}</h2>
        {desc && <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{desc}</p>}
      </div>
      {children}
    </section>
  );
}

function Stat({ label, value, warn }: { label: string; value: number | string; warn?: boolean }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", minWidth: 0 }}>
      <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: warn ? "var(--yellow)" : undefined }}>{value}</div>
    </div>
  );
}

function EventTable({ items, withUser }: { items: any[]; withUser?: boolean }) {
  if (!items.length) return <p style={{ fontSize: 12, color: "var(--text-muted)" }}>기록 없음</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
        <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
          <th style={th}>시각</th>{withUser && <th style={th}>회원</th>}<th style={th}>내용</th><th style={th}>IP</th><th style={th}>기기</th>
        </tr></thead>
        <tbody>
          {items.map((e, i) => (
            <tr key={i} style={{ borderTop: "1px solid var(--border)", color: e.ok ? undefined : "var(--red)" }}>
              <td style={td}>{when(e.at)}</td>
              {withUser && <td style={td}>{e.user || "-"}</td>}
              <td style={{ ...td, whiteSpace: "normal" }}>{KIND_LABEL[e.kind] || e.kind}{e.detail ? <span style={{ color: "var(--text-muted)" }}> · {e.detail}</span> : null}</td>
              <td style={{ ...td, fontFamily: "monospace" }}>{e.ip || "-"}</td>
              <td style={td} title={e.user_agent || ""}>{deviceName(e.user_agent)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UserDetail({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["admin-user", id], queryFn: () => adminApi.user(id).then((r) => r.data), staleTime: 0 });
  if (q.error) return <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(q.error)}</p>;
  const d = q.data;
  if (!d) return <p style={{ fontSize: 12, color: "var(--text-muted)" }}>불러오는 중...</p>;
  const row = (k: string, v: React.ReactNode) => (
    <div style={{ display: "flex", gap: 8, fontSize: 12.5 }}><span style={{ color: "var(--text-muted)", width: 96, flexShrink: 0 }}>{k}</span><span style={{ minWidth: 0, overflowWrap: "anywhere" }}>{v}</span></div>
  );
  return (
    <div data-testid="user-detail" style={{ display: "flex", flexDirection: "column", gap: 10, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
      <strong style={{ fontSize: 14 }}>{d.display_name}{d.display_name !== d.username ? <span style={{ color: "var(--text-muted)", fontWeight: 400 }}> ({d.username})</span> : null}
        {d.is_admin && <span className="badge badge-up" style={{ fontSize: 10, marginLeft: 6 }}>관리자</span>}
        {!d.is_active && <span className="badge badge-down" style={{ fontSize: 10, marginLeft: 6 }}>차단됨</span>}</strong>
      {(d.password_leaked || d.locked_until || !d.totp_enabled) && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--yellow)" }}>
          {!d.totp_enabled && <span><AlertTriangle size={12} /> 2단계 인증을 아직 등록하지 않음 — 등록 전에는 앱 데이터를 못 봄</span>}
          {d.password_leaked && <span><AlertTriangle size={12} /> 유출된 적 있는 비밀번호를 쓰는 중</span>}
          {d.locked_until && <span><AlertTriangle size={12} /> 로그인 실패가 많아 {when(d.locked_until)}까지 잠김</span>}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 6 }}>
        {row("가입", when(d.created_at))}
        {row("초대한 사람", d.invited_by || "-")}
        {row("이메일", d.email || "인증 안 함")}
        {row("휴대폰", d.phone || "인증 안 함")}
        {row("최근 7일 실패", `${d.login_fail_7d}번`)}
        {row("로그인한 IP", d.ips.length ? d.ips.join(", ") : "-")}
        {row("쓰는 기능", `관심 ${d.usage.watchlist} · 투자 ${d.usage.portfolio} · 모의투자 계좌 ${d.usage.paper_accounts} · 시뮬레이션 ${d.usage.paper_sims}`)}
      </div>
      <strong style={{ fontSize: 12.5 }}>최근 활동</strong>
      <EventTable items={d.events} />
    </div>
  );
}

export default function Admin() {
  const sum = useQuery({ queryKey: ["admin-summary"], queryFn: () => adminApi.summary().then((r) => r.data), staleTime: 0 });
  const events = useQuery({ queryKey: ["admin-events"], queryFn: () => adminApi.events().then((r) => r.data), staleTime: 0 });
  const [sel, setSel] = useState<number | null>(null);
  const s = sum.data;
  return (
    <div data-testid="admin-page" style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 1100 }}>
      <div>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}><Crown size={18} style={{ color: "var(--accent)" }} /> 관리자</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>회원 · 초대 코드 · 보안 기록 — 관리자만 보이는 화면입니다 (서버도 관리자가 아니면 막음)</p>
      </div>

      {sum.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(sum.error)}</p>}
      {s && (
        <div data-testid="admin-summary" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 8 }}>
          <Stat label="회원" value={`${s.users}명`} />
          <Stat label="2단계 미등록" value={`${s.totp_missing}명`} warn={s.totp_missing > 0} />
          <Stat label="차단" value={`${s.blocked}명`} />
          <Stat label="24시간 안 로그인" value={`${s.login_users_24h}명`} />
          <Stat label="7일 로그인 실패" value={`${s.login_fail_7d}번`} warn={s.login_fail_7d >= 10} />
          <Stat label="사용 가능한 초대" value={`${s.invites_active}개`} />
        </div>
      )}

      <Link to="/kis" className="card" data-testid="kis-link" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", color: "inherit" }}>
        <Landmark size={16} style={{ color: "var(--accent)" }} />
        <span style={{ fontSize: 13 }}><strong>KIS 모의투자 주문</strong> — AI 가 제안한 주문을 승인하는 화면 (관리자만)</span>
      </Link>

      <Card icon={Users} title="회원" desc="차단하면 바로 모든 기기에서 끊기고 로그인 못 합니다. '상세'로 그 회원의 로그인 기록을 봅니다" testid="admin-members">
        <MemberPanel selected={sel} onSelect={(id) => setSel(sel === id ? null : id)} />
        {sel != null && <UserDetail id={sel} />}
        {sel == null && <p style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 6 }}><UserSearch size={13} /> 회원의 '상세'를 누르면 활동 기록이 보입니다</p>}
      </Card>

      <Card icon={Ticket} title="초대 코드" desc="이 앱은 내가 초대한 사람만 가입할 수 있습니다 (1회용, 기본 3일)" testid="admin-invites">
        <InvitePanel />
      </Card>

      <Card icon={ShieldAlert} title="보안 기록 (전체 회원)" desc="로그인 실패·계정 잠금·비밀번호·2단계·연락처 변경·차단·초대 — 최근 100개" testid="admin-events">
        {events.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(events.error)}</p>}
        {events.data && <EventTable items={events.data.items} withUser />}
      </Card>
    </div>
  );
}
