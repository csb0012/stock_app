// 계정 활동 기록 표시 (마이페이지 '로그인 기록' · 관리자 페이지 회원 상세·보안 기록 공통)

export const KIND_LABEL: Record<string, string> = {
  login: "로그인", login_fail: "로그인 실패", account_locked: "계정 잠금 (로그인 실패 많음)", signup: "가입", password_change: "비밀번호 변경", password_reset: "비밀번호 찾기로 재설정",
  email_change: "이메일 인증", phone_change: "휴대폰 인증", contact_remove: "본인인증 수단 삭제", logout_all: "모든 기기 로그아웃",
  totp_on: "2단계 인증 켬", totp_off: "2단계 인증 끔", invite_create: "초대 코드 만듦", invite_revoke: "초대 코드 취소",
  user_block: "회원 차단", user_unblock: "회원 차단 해제",
};

/** User-Agent → "Chrome · Windows" 처럼 짧게 */
export function deviceName(ua?: string | null): string {
  if (!ua) return "-";
  const os = /iPhone|iPad/.test(ua) ? "iPhone/iPad" : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows"
    : /Mac OS X|Macintosh/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : "";
  const br = /Whale\//.test(ua) ? "웨일" : /SamsungBrowser/.test(ua) ? "삼성 인터넷" : /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox"
    : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "";
  return [br, os].filter(Boolean).join(" · ") || ua.slice(0, 40);
}
