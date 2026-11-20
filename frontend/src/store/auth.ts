import { create } from "zustand";

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
    localStorage.setItem("token", token);
    set({ token });
  },
  setUser: (username, totpEnabled) => set({ username, totpEnabled }),
  logout: () => {
    localStorage.removeItem("token");
    set({ token: null, username: null });
  },
}));
