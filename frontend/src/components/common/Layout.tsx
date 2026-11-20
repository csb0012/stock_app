import { NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/auth";
import {
  LayoutDashboard, TrendingUp, Star, Calendar,
  Search, LogOut, BarChart2, Briefcase, ClipboardCheck,
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
      <aside style={{
        width: 220, background: "var(--bg-secondary)", borderRight: "1px solid var(--border)",
        display: "flex", flexDirection: "column", padding: "20px 0", flexShrink: 0,
      }}>
        {/* Logo */}
        <div style={{ padding: "0 20px 24px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <TrendingUp size={20} style={{ color: "var(--accent)" }} />
            <span style={{ fontWeight: 700, fontSize: 16, color: "var(--text-primary)" }}>StockApp</span>
          </div>
          {username && (
            <p style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 6 }}>{username}</p>
          )}
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

        {/* Logout */}
        <div style={{ padding: "16px 10px", borderTop: "1px solid var(--border)" }}>
          <button onClick={handleLogout} className="btn btn-ghost"
            style={{ width: "100%", justifyContent: "flex-start", gap: 10 }}>
            <LogOut size={15} />
            로그아웃
          </button>
        </div>
      </aside>

      {/* Main */}
      <main style={{ flex: 1, overflow: "auto", background: "var(--bg-primary)" }}>
        <div style={{ maxWidth: 1400, margin: "0 auto", padding: "28px 32px" }}>
          {children}
        </div>
      </main>
    </div>
  );
}
