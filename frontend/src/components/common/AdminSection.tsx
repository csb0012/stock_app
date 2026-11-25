import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Ticket, Ban, CheckCircle2 } from "lucide-react";
import { adminApi, errMsg } from "../../api/client";
import { inputStyle } from "./AuthForm";
import { toast } from "./Toast";

const STATUS: Record<string, [string, string]> = {
  active: ["사용 가능", "badge-up"], used: ["사용됨", "badge-neutral"], expired: ["만료", "badge-neutral"], revoked: ["취소", "badge-down"],
};
const when = (t?: number | string | null) => {
  if (!t) return "-";
  const d = typeof t === "number" ? new Date(t * 1000) : new Date(String(t) + (/[Z+]/.test(String(t)) ? "" : "Z"));
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
};
const codeInput = (v: string, set: (s: string) => void, label: string) => (
  <input value={v} onChange={(e) => set(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" placeholder="2단계 코드"
    aria-label={label} style={{ ...inputStyle, width: 120, letterSpacing: 2 }} autoComplete="one-time-code" />
);

/** 마이페이지 '관리자' 구역 (앱 주인만): 초대 코드 만들기·목록·취소 + 회원 목록·차단. 만들기·차단은 2단계 코드를 다시 받음 */
export default function AdminSection() {
  const qc = useQueryClient();
  const inv = useQuery({ queryKey: ["admin-invites"], queryFn: () => adminApi.invites().then((r) => r.data), staleTime: 0 });
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => adminApi.users().then((r) => r.data), staleTime: 0 });
  const [memo, setMemo] = useState("");
  const [days, setDays] = useState(3);
  const [code, setCode] = useState("");
  const [made, setMade] = useState<{ code: string; memo?: string; expires_at: number } | null>(null);
  const [blockCode, setBlockCode] = useState("");

  const create = useMutation({ mutationFn: () => adminApi.createInvite(memo.trim(), days, code).then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => { setMade(d); setMemo(""); setCode(""); qc.invalidateQueries({ queryKey: ["admin-invites"] }); } });
  const revoke = useMutation({ mutationFn: (id: number) => adminApi.revokeInvite(id).then((r) => r.data),
    onSuccess: (d) => { toast(d.message, "info"); qc.invalidateQueries({ queryKey: ["admin-invites"] }); } });
  const setActive = useMutation({ mutationFn: (v: { id: number; active: boolean }) => adminApi.setActive(v.id, v.active, blockCode).then((r) => r.data),
    meta: { inlineError: true },
    onSuccess: (d) => { toast(d.message, "info"); setBlockCode(""); qc.invalidateQueries({ queryKey: ["admin-users"] }); } });
  const copy = async (t: string) => {
    try { await navigator.clipboard.writeText(t); toast("복사했습니다", "info"); } catch { toast("복사하지 못했습니다 — 직접 선택해 복사하세요"); }
  };
  const items: any[] = inv.data?.items || [];
  const members: any[] = users.data?.items || [];
  const th = { padding: "6px 8px", fontWeight: 500 } as const;
  const td = { padding: "6px 8px", whiteSpace: "nowrap" } as const;

  return (
    <div data-testid="admin-section" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <strong style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}><Ticket size={14} /> 초대 코드 만들기</strong>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          믿는 사람에게만 직접(카톡·문자 등) 전달하세요. 1회용이고 기간이 지나면 못 씁니다. 가입한 사람도 2단계 인증을 등록해야 앱을 쓸 수 있습니다.
        </p>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <input value={memo} onChange={(e) => setMemo(e.target.value.slice(0, 40))} placeholder="누구에게? (메모, 선택)" aria-label="초대 메모"
            style={{ ...inputStyle, flex: 1, minWidth: 160 }} />
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="유효 기간" className="input" style={{ width: 90 }}>
            {[1, 3, 7, 14].map((d) => <option key={d} value={d}>{d}일</option>)}
          </select>
          {codeInput(code, setCode, "초대 2단계 코드")}
          <button className="btn btn-primary" disabled={!/^\d{6}$/.test(code) || create.isPending} onClick={() => create.mutate()}>만들기</button>
        </div>
        {create.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(create.error)}</p>}
        {made && (
          <div data-testid="invite-made" style={{ border: "1px solid var(--accent)", borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 6,
            background: "color-mix(in srgb, var(--accent) 7%, transparent)" }}>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>새 초대 코드{made.memo ? ` (${made.memo})` : ""} — <strong>지금만 보입니다</strong>, {when(made.expires_at)}까지</span>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <code data-testid="invite-code" style={{ fontSize: 20, letterSpacing: 2, fontWeight: 700 }}>{made.code}</code>
              <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => copy(made.code)}><Copy size={13} /> 복사</button>
              <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => setMade(null)}>닫기</button>
            </div>
          </div>
        )}
        {inv.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(inv.error)}</p>}
        {items.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table data-testid="invite-table" style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
                <th style={th}>코드</th><th style={th}>메모</th><th style={th}>상태</th><th style={th}>만료</th><th style={th}></th>
              </tr></thead>
              <tbody>
                {items.map((i) => {
                  const [label, cls] = STATUS[i.status] || [i.status, "badge-neutral"];
                  return (
                    <tr key={i.id} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ ...td, fontFamily: "monospace" }}>…{i.hint}</td>
                      <td style={td}>{i.memo || "-"}</td>
                      <td style={td}><span className={`badge ${cls}`} style={{ fontSize: 10.5 }}>{label}</span>{i.used_by ? <span style={{ color: "var(--text-muted)" }}> {i.used_by}</span> : null}</td>
                      <td style={td}>{when(i.expires_at)}</td>
                      <td style={td}>{i.status === "active" && (
                        <button className="btn btn-ghost" style={{ fontSize: 11.5, padding: "2px 8px", color: "var(--red)" }} disabled={revoke.isPending}
                          onClick={() => { if (window.confirm(`…${i.hint} 초대 코드를 취소할까요?`)) revoke.mutate(i.id); }}>취소</button>
                      )}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <strong style={{ fontSize: 13 }}>회원 목록</strong>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>차단·해제할 때 2단계 코드:</span>
          {codeInput(blockCode, setBlockCode, "차단 2단계 코드")}
          <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>차단하면 바로 모든 기기에서 끊기고 로그인 못 합니다 (데이터는 남음)</span>
        </div>
        {setActive.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(setActive.error)}</p>}
        {users.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(users.error)}</p>}
        <div style={{ overflowX: "auto" }}>
          <table data-testid="member-table" style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
            <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
              <th style={th}>아이디</th><th style={th}>2단계</th><th style={th}>초대한 사람</th><th style={th}>최근 로그인</th><th style={th}></th>
            </tr></thead>
            <tbody>
              {members.map((u) => (
                <tr key={u.id} style={{ borderTop: "1px solid var(--border)", opacity: u.is_active ? 1 : 0.55 }}>
                  <td style={td}>{u.display_name}{u.display_name !== u.username ? <span style={{ color: "var(--text-muted)" }}> ({u.username})</span> : null}
                    {u.is_admin && <span className="badge badge-up" style={{ fontSize: 10, marginLeft: 4 }}>관리자</span>}
                    {!u.is_active && <span className="badge badge-down" style={{ fontSize: 10, marginLeft: 4 }}>차단됨</span>}</td>
                  <td style={td}>{u.totp_enabled ? <CheckCircle2 size={13} style={{ color: "var(--green)" }} aria-label="등록" /> : <span style={{ color: "var(--yellow)" }}>미등록</span>}</td>
                  <td style={td}>{u.invited_by || "-"}</td>
                  <td style={td}>{when(u.last_login)}</td>
                  <td style={td}>{!u.me && !u.is_admin && (
                    <button className="btn btn-ghost" style={{ fontSize: 11.5, padding: "2px 8px", color: u.is_active ? "var(--red)" : undefined }}
                      disabled={!/^\d{6}$/.test(blockCode) || setActive.isPending}
                      onClick={() => { if (window.confirm(u.is_active ? `${u.username} 을(를) 차단할까요?` : `${u.username} 차단을 풀까요?`)) setActive.mutate({ id: u.id, active: !u.is_active }); }}>
                      {u.is_active ? <><Ban size={12} /> 차단</> : "차단 해제"}
                    </button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
