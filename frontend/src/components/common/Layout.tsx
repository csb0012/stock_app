import { NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/auth";
import { useQuery } from "@tanstack/react-query";
import { marketApi } from "../../api/client";
import ThemeToggle from "./ThemeToggle";
import {
  LayoutDashboard, TrendingUp, Star, Calendar,
  Search, LogOut, BarChart2, Briefcase, ClipboardCheck, UserCircle,
} from "lucide-react";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "대시보드" },
  { to: "/recommendations", icon: TrendingUp, label: "AI 추천" },
  { to: "/screener", icon: BarChart2, label: "종목탐색" },
  { to: "/watchlist", icon: Star, label: "관심종목" },
  { to: "/portfolio", icon: Briefcase, label: "투자종목" },
  { to: "/predictions", icon: ClipboardCheck, label: "예측 검증" },
  { to: "/calendar", icon: Calendar, label: "경제캘린더" },
  { to: "/search", icon: Search, label: "종목검색" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { username, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      {/* Sidebar */}
      <aside className="sidebar" style={{
        width: 220, background: "var(--bg-secondary)", borderRight: "1px solid var(--border)",
        display: "flex", flexDirection: "column", padding: "20px 0", flexShrink: 0,
      }}>
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
      <main style={{ flex: 1, overflow: "auto", background: "var(--bg-primary)" }}>
        <div style={{ maxWidth: 1400, margin: "0 auto", padding: "14px 32px 28px" }}>
          {/* 상단 바: 사용자 · 화이트/다크 모드 · 로그아웃 */}
          <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 6, marginBottom: 14 }}>
            {username && (
              <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)", marginRight: 6 }}>
                <UserCircle size={15} /> {username}
              </span>
            )}
            <ThemeToggle pill />
            <button onClick={handleLogout} className="btn btn-ghost" style={{ padding: "5px 12px", fontSize: 12, borderRadius: 999 }}>
              <LogOut size={13} />
              로그아웃
            </button>
          </div>
          {children}
        </div>
      </main>
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
          </div>
        );
      })}
    </div>
  );
}
