import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient as qc } from "./api/queryClient";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "./store/auth";
import { authApi } from "./api/client";
import Layout from "./components/common/Layout";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import ForgotPassword from "./pages/ForgotPassword";
import MyPage from "./pages/MyPage";
import Dashboard from "./pages/Dashboard";
import Recommendations from "./pages/Recommendations";
import Screener from "./pages/Screener";
import Watchlist from "./pages/Watchlist";
import Portfolio from "./pages/Portfolio";
import CalendarPage from "./pages/Calendar";
import Predictions from "./pages/Predictions";
import Themes from "./pages/Themes";
import Accumulation from "./pages/Accumulation";
import Quant from "./pages/Quant";
import PaperTrading from "./pages/PaperTrading";
import Setup2FA from "./pages/Setup2FA";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore();
  // 2단계 인증 필수인데 아직 안 켰으면 설정 화면으로 (서버도 403 으로 막음 — 이건 화면을 먼저 옮기는 것)
  const me = useQuery({ queryKey: ["me"], queryFn: () => authApi.me().then((r) => r.data), staleTime: 5 * 60 * 1000, enabled: !!token });
  if (!token) return <Navigate to="/login" replace />;
  if (me.data?.totp_required && !me.data?.totp_enabled) return <Navigate to="/setup-2fa" replace />;
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/forgot" element={<ForgotPassword />} />
          <Route path="/setup-2fa" element={<Setup2FA />} />
          <Route path="/mypage" element={<ProtectedRoute><MyPage /></ProtectedRoute>} />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/recommendations" element={<ProtectedRoute><Recommendations /></ProtectedRoute>} />
          <Route path="/screener" element={<ProtectedRoute><Screener /></ProtectedRoute>} />
          <Route path="/watchlist" element={<ProtectedRoute><Watchlist /></ProtectedRoute>} />
          <Route path="/portfolio" element={<ProtectedRoute><Portfolio /></ProtectedRoute>} />
          <Route path="/predictions" element={<ProtectedRoute><Predictions /></ProtectedRoute>} />
          <Route path="/calendar" element={<ProtectedRoute><CalendarPage /></ProtectedRoute>} />
          {/* 예전 종목검색 화면 → 종목탐색(검색 포함)으로 통합 */}
          <Route path="/search" element={<Navigate to="/screener" replace />} />
          <Route path="/themes" element={<ProtectedRoute><Themes /></ProtectedRoute>} />
          <Route path="/quant" element={<ProtectedRoute><Quant /></ProtectedRoute>} />
          <Route path="/accumulation" element={<ProtectedRoute><Accumulation /></ProtectedRoute>} />
          <Route path="/paper" element={<ProtectedRoute><PaperTrading /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
