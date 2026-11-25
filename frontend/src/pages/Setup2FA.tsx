import { Navigate, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { authApi, errMsg } from "../api/client";
import { useAuthStore } from "../store/auth";
import { AuthShell } from "../components/common/AuthForm";
import TotpSection from "../components/common/TotpSection";

/** 2단계 인증 필수 — 등록하기 전에는 이 화면만 쓸 수 있음 (서버도 다른 API 를 403 으로 막음) */
export default function Setup2FA() {
  const navigate = useNavigate();
  const { token, logout } = useAuthStore();
  const me = useQuery({ queryKey: ["me"], queryFn: () => authApi.me().then((r) => r.data), staleTime: 0, enabled: !!token });
  if (!token) return <Navigate to="/login" replace />;
  // 저장해 둔(오래된) 내 정보로 판단하면 등록 화면 ↔ 첫 화면을 오갈 수 있어서, 이 화면에서 새로 받은 값으로만 판단
  if (me.isFetchedAfterMount && me.data && (me.data.totp_enabled || !me.data.totp_required)) return <Navigate to="/" replace />;
  return (
    <AuthShell title="2단계 인증 등록 (필수)" subtitle="비밀번호가 새어도 내 휴대폰 없이는 아무도 로그인하지 못하게 합니다">
      <div data-testid="setup-2fa" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <p style={{ fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.65 }}>
          이 앱은 Google Authenticator 2단계 인증을 켜야 쓸 수 있습니다{me.data ? <> (계정 <strong>{me.data.username}</strong>)</> : null}.
          휴대폰에 <strong>Google Authenticator</strong> 앱을 설치한 뒤 아래에서 QR 코드를 만들어 스캔하세요.
          다음 로그인부터는 비밀번호 + 앱의 6자리 코드가 필요합니다.
        </p>
        {me.error && <p style={{ color: "var(--red)", fontSize: 12 }}>{errMsg(me.error)}</p>}
        <TotpSection onEnabled={() => navigate("/", { replace: true })} />
        <p style={{ fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.6 }}>
          휴대폰을 잃어버리면 서버에서 <code>python create_admin.py --reset-totp 아이디</code> 로 등록을 지우고 다시 등록합니다.
        </p>
        <button className="btn btn-ghost" style={{ justifyContent: "center" }}
          onClick={() => { navigate("/login", { replace: true }); setTimeout(logout, 0); }}>로그아웃</button>
      </div>
    </AuthShell>
  );
}
