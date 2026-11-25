import { useEffect, useState } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../../store/auth";
import { useQuery } from "@tanstack/react-query";
import { marketApi } from "../../api/client";
import ThemeToggle from "./ThemeToggle";
import {
  LayoutDashboard, TrendingUp, Star, Calendar,
  LogOut, BarChart2, Briefcase, ClipboardCheck, UserCircle, Layers, Radar, Menu, X, Gauge,
} from "lucide-react";
import ChatWidget from "./ChatWidget";
import Toaster from "./Toast";
import SecuritySettings from "./SecuritySettings";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "대시보드" },
  { to: "/recommendations", icon: TrendingUp, label: "AI 추천" },
  { to: "/screener", icon: BarChart2, label: "종목탐색" },
  { to: "/themes", icon: Layers, label: "테마별 주식" },
  { to: "/quant", icon: Gauge, label: "퀀트 점수" },
  { to: "/accumulation", icon: Radar, label: "매집 탐지" },
  { to: "/watchlist", icon: Star, label: "관심종목" },
  { to: "/portfolio", icon: Briefcase, label: "투자종목" },
  { to: "/predictions", icon: ClipboardCheck, label: "예측 검증" },
  { to: "/calendar", icon: Calendar, label: "경제캘린더" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { username, logout } = useAuthStore();
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
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
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
          ))}
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
          {username && (
            <span className="top-user" style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)", marginRight: 6 }}>
              <UserCircle size={15} /> {username}
            </span>
          )}
          <SecuritySettings />
          <ThemeToggle pill />
          <button onClick={handleLogout} className="btn btn-ghost" style={{ padding: "5px 12px", fontSize: 12, borderRadius: 999 }}>
            <LogOut size={13} />
            로그아웃
          </button>
        </div>
        <div className="page-body">
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
          </div>
        );
      })}
    </div>
  );
}
