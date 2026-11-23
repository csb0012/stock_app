import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient as qc } from "./api/queryClient";
import { useAuthStore } from "./store/auth";
import Layout from "./components/common/Layout";
import Login from "./pages/Login";
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

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore();
  return token ? <Layout>{children}</Layout> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
