import { create } from "zustand";
import { clearPersisted } from "../api/persist";
import { queryClient } from "../api/queryClient";

interface AuthState {
  token: string | null;
  username: string | null;
  totpEnabled: boolean;
  setToken: (token: string) => void;
  setUser: (username: string, totpEnabled: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem("token"),
  username: null,
  totpEnabled: false,
  setToken: (token) => {
    clearPersisted(queryClient);  // 다른 계정이 저장해 둔 데이터가 섞이지 않도록
    localStorage.setItem("token", token);
    set({ token });
  },
  setUser: (username, totpEnabled) => set({ username, totpEnabled }),
  logout: () => {
    localStorage.removeItem("token");
    clearPersisted(queryClient);  // 다음에 로그인하는 사람에게 이전 데이터가 보이지 않도록
    set({ token: null, username: null });
  },
}));
