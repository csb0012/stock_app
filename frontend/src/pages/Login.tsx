import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { authApi, errMsg } from "../api/client";
import { useAuthStore } from "../store/auth";
import { TrendingUp, Lock, User, Shield } from "lucide-react";
import ThemeToggle from "../components/common/ThemeToggle";

export default function Login() {
  const navigate = useNavigate();
  const { setToken } = useAuthStore();
  const [form, setForm] = useState({ username: "", password: "", totp_code: "" });
  const [needsTotp, setNeedsTotp] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const notice = (useLocation().state as any)?.notice as string | undefined;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await authApi.login(
        form.username,
        form.password,
        needsTotp ? form.totp_code : undefined
      );
      if (res.data.requires_totp) {
        setNeedsTotp(true);
      } else {
        setToken(res.data.access_token);
        navigate("/");
      }
    } catch (err: any) {
      setError(errMsg(err) || "로그인 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg-primary)" }}>
      <div style={{ position: "fixed", top: 16, right: 16 }}><ThemeToggle compact /></div>
      <div style={{ width: 380 }}>
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-3">
            <TrendingUp size={28} style={{ color: "var(--accent)" }} />
            <span style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)" }}>StockApp</span>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>AI 기반 주식 분석 플랫폼</p>
        </div>

        <div className="card">
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {!needsTotp ? (
              <>
                <div>
                  <label style={{ color: "var(--text-secondary)", fontSize: 12, marginBottom: 6, display: "block" }}>
                    아이디 · 이메일 · 휴대폰 번호
                  </label>
                  <div style={{ position: "relative" }}>
                    <User size={15} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
                    <input
                      type="text"
                      value={form.username}
                      onChange={(e) => setForm({ ...form, username: e.target.value })}
                      placeholder="아이디 또는 인증한 이메일·휴대폰 번호"
                      autoComplete="username"
                      required
                      style={{
                        width: "100%", padding: "9px 10px 9px 32px",
                        background: "var(--bg-secondary)", border: "1px solid var(--border)",
                        borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none",
                      }}
                    />
                  </div>
                </div>
                <div>
                  <label style={{ color: "var(--text-secondary)", fontSize: 12, marginBottom: 6, display: "block" }}>
                    비밀번호
                  </label>
                  <div style={{ position: "relative" }}>
                    <Lock size={15} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
                    <input
                      type="password"
                      value={form.password}
                      onChange={(e) => setForm({ ...form, password: e.target.value })}
                      placeholder="••••••••"
                      required
                      style={{
                        width: "100%", padding: "9px 10px 9px 32px",
                        background: "var(--bg-secondary)", border: "1px solid var(--border)",
                        borderRadius: 7, color: "var(--text-primary)", fontSize: 14, outline: "none",
                      }}
                    />
                  </div>
                </div>
              </>
            ) : (
              <div>
                <div style={{ textAlign: "center", marginBottom: 16 }}>
                  <Shield size={32} style={{ color: "var(--accent)", margin: "0 auto 8px" }} />
                  <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                    Google Authenticator에서<br />6자리 코드를 입력하세요
                  </p>
                </div>
                <input
                  type="text"
                  value={form.totp_code}
                  onChange={(e) => setForm({ ...form, totp_code: e.target.value })}
                  placeholder="000000"
                  maxLength={6}
                  required
                  style={{
                    width: "100%", padding: "12px", textAlign: "center",
                    background: "var(--bg-secondary)", border: "1px solid var(--border)",
                    borderRadius: 7, color: "var(--text-primary)", fontSize: 20,
                    letterSpacing: 8, outline: "none",
                  }}
                />
              </div>
            )}

            {notice && !error && (
              <p data-testid="login-notice" style={{ color: "var(--green)", fontSize: 13, textAlign: "center" }}>{notice}</p>
            )}
            {error && (
              <p style={{ color: "var(--red)", fontSize: 13, textAlign: "center" }}>{error}</p>
            )}

            <button type="submit" className="btn btn-primary" disabled={loading}
              style={{ width: "100%", justifyContent: "center", padding: 11, marginTop: 4 }}>
              {loading ? "로그인 중..." : needsTotp ? "인증 완료" : "로그인"}
            </button>

            {needsTotp && (
              <button type="button" className="btn btn-ghost"
                style={{ width: "100%", justifyContent: "center" }}
                onClick={() => setNeedsTotp(false)}>
                뒤로
              </button>
            )}
          </form>
          {!needsTotp && (
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 14, fontSize: 12.5 }}>
              <Link to="/signup" style={{ color: "var(--accent)" }}>회원가입</Link>
              <Link to="/forgot" style={{ color: "var(--text-secondary)" }}>비밀번호 찾기</Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
