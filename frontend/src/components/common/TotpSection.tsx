import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Shield } from "lucide-react";
import { authApi, errMsg } from "../../api/client";
import { toast } from "./Toast";

/** 마이페이지 '2단계 인증' 구역 — 켜기(QR → 6자리 확인)·끄기(현재 코드) */
export default function TotpSection() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => authApi.me().then((r) => r.data), staleTime: 0 });
  const [setup, setSetup] = useState<any>(null);
  const [code, setCode] = useState("");

  const start = useMutation({ mutationFn: () => authApi.setupTotp().then((r) => r.data), meta: { inlineError: true },
    onSuccess: (d) => { setSetup(d); setCode(""); } });
  const enable = useMutation({ mutationFn: () => authApi.enableTotp(code.trim()), meta: { inlineError: true },
    onSuccess: () => { toast("2단계 인증을 켰습니다 — 다음 로그인부터 앱의 6자리 코드를 입력합니다", "info"); setSetup(null); setCode(""); qc.invalidateQueries({ queryKey: ["me"] }); } });
  const disable = useMutation({ mutationFn: () => authApi.disableTotp(code.trim()), meta: { inlineError: true },
    onSuccess: () => { toast("2단계 인증을 껐습니다", "info"); setCode(""); qc.invalidateQueries({ queryKey: ["me"] }); } });
  const err = start.error || enable.error || disable.error;
  const on = me.data?.totp_enabled;
  const codeOk = /^\d{6}$/.test(code.trim());

  const input = (
    <input value={code} onChange={(e) => setCode(e.target.value.replace(/[^\d]/g, "").slice(0, 6))} inputMode="numeric" autoFocus
      placeholder="앱에 보이는 6자리" aria-label="인증 코드"
      style={{ width: 160, padding: "8px 10px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 7,
        color: "var(--text-primary)", fontSize: 16, letterSpacing: 3, outline: "none" }} />
  );

  return (
    <div data-testid="totp-section" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {me.isLoading ? <p style={{ fontSize: 13, color: "var(--text-muted)" }}>불러오는 중...</p> : on ? (
          <>
            <p style={{ fontSize: 13, color: "var(--green)", fontWeight: 600 }}>켜져 있음 — 로그인할 때 비밀번호 + 앱의 6자리 코드가 필요합니다</p>
            <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>끄려면 지금 앱에 보이는 코드를 입력하세요.</p>
            <div style={{ display: "flex", gap: 8 }}>
              {input}
              <button className="btn btn-ghost" style={{ color: "var(--red)" }} disabled={!codeOk || disable.isPending} onClick={() => disable.mutate()}>끄기</button>
            </div>
          </>
        ) : !setup ? (
          <>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              꺼져 있음. 켜면 비밀번호가 새어도 휴대폰 앱의 코드 없이는 로그인할 수 없습니다.
              <strong> 클라우드 서버처럼 인터넷에 열려 있으면 켜 두세요.</strong>
            </p>
            <button className="btn btn-primary" style={{ alignSelf: "flex-start" }} disabled={start.isPending} onClick={() => start.mutate()}>
              <Shield size={14} /> 켜기 — QR 코드 만들기
            </button>
          </>
        ) : (
          <>
            <ol style={{ fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.7, paddingLeft: 18 }}>
              <li>휴대폰에 Google Authenticator 를 설치하고 <strong>QR 코드 스캔</strong></li>
              <li>앱에 나온 6자리를 입력하고 <strong>확인</strong> (30초마다 바뀜)</li>
            </ol>
            <img src={`data:image/png;base64,${setup.qr_code}`} alt="2단계 인증 QR 코드" style={{ width: 180, height: 180, alignSelf: "center", background: "#fff", borderRadius: 8 }} />
            <p style={{ fontSize: 11, color: "var(--text-muted)", wordBreak: "break-all" }}>QR 을 못 찍으면 앱에 직접 입력: <code>{setup.secret}</code></p>
            <div style={{ display: "flex", gap: 8 }}>
              {input}
              <button className="btn btn-primary" disabled={!codeOk || enable.isPending} onClick={() => enable.mutate()}>확인</button>
            </div>
            <p style={{ fontSize: 11, color: "var(--text-muted)" }}>확인을 누르기 전까지는 켜지지 않습니다 (창을 닫으면 취소).</p>
          </>
        )}
        {err && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(err)}</p>}
    </div>
  );
}
