import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

export type Theme = "dark" | "light";

/** 저장된 테마 (없으면 OS 설정) — index.html 의 초기 스크립트와 같은 규칙 */
export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem("theme", t);
  } catch {
    /* 저장 안 돼도 이번 화면에는 적용 */
  }
}

/** 다크 ↔ 화이트 모드 전환 버튼 */
export default function ThemeToggle({ compact = false, pill = false }: { compact?: boolean; pill?: boolean }) {
  const [theme, setTheme] = useState<Theme>(currentTheme());
  useEffect(() => applyTheme(theme), [theme]);
  const next: Theme = theme === "dark" ? "light" : "dark";
  const Icon = theme === "dark" ? Sun : Moon;
  return (
    <button
      className="btn btn-ghost"
      onClick={() => setTheme(next)}
      title={next === "light" ? "화이트 모드로" : "다크 모드로"}
      style={pill ? { padding: "5px 12px", fontSize: 12, borderRadius: 999 }
        : compact ? { padding: "6px 10px" } : { width: "100%", justifyContent: "flex-start", gap: 10 }}
    >
      <Icon size={pill ? 13 : 15} />
      {!compact && (next === "light" ? "화이트 모드" : "다크 모드")}
    </button>
  );
}
