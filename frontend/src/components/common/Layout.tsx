import { useEffect, useState } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../../store/auth";
import { useQuery } from "@tanstack/react-query";
import { marketApi, authApi } from "../../api/client";
import ThemeToggle from "./ThemeToggle";
import {
  LayoutDashboard, TrendingUp, Star, Calendar,
  LogOut, BarChart2, Briefcase, ClipboardCheck, UserCircle, Layers, Radar, Menu, X, Gauge, Bot, Crown, Landmark,
} from "lucide-react";
import ChatWidget from "./ChatWidget";
import Toaster from "./Toast";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "대시보드" },
  { to: "/recommendations", icon: TrendingUp, label: "AI 추천" },
  { to: "/screener", icon: BarChart2, label: "종목탐색" },
  { to: "/themes", icon: Layers, label: "테마별 주식" },
  { to: "/quant", icon: Gauge, label: "퀀트 점수" },
  { to: "/accumulation", icon: Radar, label: "매집 탐지" },
  { to: "/watchlist", icon: Star, label: "관심종목" },
  { to: "/portfolio", icon: Briefcase, label: "투자종목" },
  { to: "/paper", icon: Bot, label: "AI 모의투자" },
  { to: "/predictions", icon: ClipboardCheck, label: "예측 검증" },
  { to: "/calendar", icon: Calendar, label: "경제캘린더" },
];
// 관리자만 보이는 메뉴 (일반 사용자 메뉴와 따로)
const adminItems = [
  { to: "/admin", icon: Crown, label: "관리자" },
  { to: "/kis", icon: Landmark, label: "KIS 모의투자 주문" },
];

function NavItem({ to, icon: Icon, label }: { to: string; icon: any; label: string }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      style={({ isActive }) => ({
        display: "flex", alignItems: "center", gap: 10,
        padding: "9px 12px", borderRadius: 7, textDecoration: "none",
        fontSize: 13, fontWeight: 500, transition: "all 0.15s",
        background: isActive ? "var(--bg-hover)" : "transparent",
        color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
        borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
      })}
    >
      <Icon size={16} />
      {label}
    </NavLink>
  );
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { username, logout } = useAuthStore();
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: () => authApi.me().then((r) => r.data), staleTime: 5 * 60 * 1000 });
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };
  // 좁은 화면(휴대폰): 사이드바는 ☰ 버튼으로 여는 메뉴 — 화면을 옮기면 닫힘
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setNavOpen(false), [location.pathname]);

  return (
    <div className={`app-shell${navOpen ? " nav-open" : ""}`}>
      {navOpen && <div className="nav-backdrop" onClick={() => setNavOpen(false)} />}
      {/* Sidebar */}
      <aside className="sidebar" aria-label="메뉴">
        {/* Logo */}
        <div style={{ padding: "0 20px 24px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <TrendingUp size={20} style={{ color: "var(--accent)" }} />
            <span style={{ fontWeight: 700, fontSize: 16, color: "var(--text-primary)" }}>StockApp</span>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "16px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
          {navItems.map((item) => <NavItem key={item.to} {...item} />)}
          {me?.is_admin && (
            <div data-testid="admin-nav" style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ fontSize: 11, color: "var(--text-muted)", padding: "0 12px 4px", fontWeight: 600 }}>관리자 전용</span>
              {adminItems.map((item) => <NavItem key={item.to} {...item} />)}
            </div>
          )}
        </nav>

        {/* 장 운영 상태 */}
        <MarketStatus />

      </aside>

      {/* Main */}
      <main style={{ flex: 1, minWidth: 0, overflow: "auto", background: "var(--bg-primary)" }}>
        {/* 상단 바 (창 오른쪽 끝): 사용자 · 화이트/다크 모드 · 로그아웃 */}
        <div className="top-bar">
          <button className="btn btn-ghost menu-btn" onClick={() => setNavOpen(!navOpen)} aria-label={navOpen ? "메뉴 닫기" : "메뉴 열기"}
            style={{ padding: "5px 10px", marginRight: "auto" }}>
            {navOpen ? <X size={16} /> : <Menu size={16} />}
          </button>
          {/* 닉네임(없으면 아이디) = 마이페이지 (닉네임·본인인증·비밀번호·2단계 인증·기기 관리·탈퇴) */}
          <NavLink to="/mypage" className="btn btn-ghost" data-testid="mypage-link" title="마이페이지"
            style={{ padding: "5px 12px", fontSize: 12, borderRadius: 999, textDecoration: "none" }}>
            <UserCircle size={14} /> <span className="top-user">{me?.display_name || me?.username || username || "내 계정"}</span>
            {me && !(me.email || me.phone) && <span data-testid="unverified-dot" title="본인인증(이메일 또는 휴대폰) 안 함 — 비밀번호 찾기를 쓰려면 인증하세요" style={{ width: 7, height: 7, borderRadius: 4, background: "var(--yellow)" }} />}
          </NavLink>
          <ThemeToggle pill />
          <button onClick={handleLogout} className="btn btn-ghost" style={{ padding: "5px 12px", fontSize: 12, borderRadius: 999 }}>
            <LogOut size={13} />
            로그아웃
          </button>
        </div>
        <div className="page-body">
          {me?.password_leaked && (
            <div data-testid="leaked-banner" role="alert" style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 8, fontSize: 13,
              border: "1px solid var(--red)", background: "color-mix(in srgb, var(--red) 8%, transparent)", color: "var(--text-primary)" }}>
              <strong style={{ color: "var(--red)" }}>지금 비밀번호가 해킹 유출 목록에 있습니다.</strong>{" "}
              다른 사이트에서 털린 비밀번호 목록에 같은 비밀번호가 있어, 해커가 가장 먼저 대입해 보는 비밀번호입니다.{" "}
              <NavLink to="/mypage#password" style={{ color: "var(--accent)", fontWeight: 600 }}>마이페이지에서 비밀번호 바꾸기 →</NavLink>
            </div>
          )}
          {children}
        </div>
      </main>

      {/* 챗봇: 오른쪽 아래 떠 있는 버튼 (모든 화면) */}
      <ChatWidget />
      <Toaster />
    </div>
  );
}

function MarketStatus() {
  const { data } = useQuery({
    queryKey: ["market-status"],
    queryFn: () => marketApi.status().then((r) => r.data),
    refetchInterval: 60_000,
  });
  if (!data) return null;
  return (
    <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 6 }}>
      {(["KR", "US"] as const).map((m) => {
        const st = data[m];
        const color = st.open ? "var(--green)" : st.state === "휴장" ? "var(--red)" : "var(--text-muted)";
        return (
          <div key={m} style={{ fontSize: 11, whiteSpace: "nowrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: 3, background: color, flexShrink: 0 }} />
              <span style={{ color: "var(--text-secondary)" }}>{m === "KR" ? "국내" : "미국"}</span>
              <span style={{ color }}>{st.state}</span>
            </div>
            {!st.open && st.next_open_kst && (
              <div style={{ color: "var(--text-muted)", paddingLeft: 12 }}>개장 {st.next_open_kst} (한국시간)</div>
            )}
            {st.daytime?.open && (
              <div style={{ color: "var(--accent)", paddingLeft: 12 }} title="한국 낮 시간 미국 주식 거래 (블루오션) — 관심종목·대시보드 등에 '주간거래' 가격 표시">
                주간거래 중 (~{st.daytime.end_kst})
              </div>
            )}
            {st.extended?.open && (
              <div style={{ color: "var(--accent)", paddingLeft: 12 }} title="미국 정규장 밖 거래 — 관심종목·투자종목·AI 추천에 그 가격을 따로 표시 (Yahoo 5분봉)">
                {st.extended.label} 중 (~{st.extended.hours_kst?.split("~")[1]})
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
