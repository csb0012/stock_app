import { create } from "zustand";
import { X } from "lucide-react";

/** 화면 아래쪽 알림 — 버튼을 눌렀는데 요청이 실패하면 사유를 보여줌 (예전엔 아무 표시 없이 끝나는 버튼이 있었음) */
type Toast = { id: number; text: string; kind: "error" | "info" };
type Store = { items: Toast[]; push: (text: string, kind?: Toast["kind"]) => void; remove: (id: number) => void };

let seq = 0;
export const useToast = create<Store>((set, get) => ({
  items: [],
  push: (text, kind = "error") => {
    const id = ++seq;
    // 같은 문구가 이미 떠 있으면 하나만
    if (get().items.some((t) => t.text === text)) return;
    set({ items: [...get().items.slice(-2), { id, text, kind }] });
    setTimeout(() => get().remove(id), kind === "error" ? 8000 : 4000);
  },
  remove: (id) => set({ items: get().items.filter((t) => t.id !== id) }),
}));

export function toast(text: string, kind: Toast["kind"] = "error") {
  useToast.getState().push(text, kind);
}

export default function Toaster() {
  const { items, remove } = useToast();
  if (!items.length) return null;
  return (
    <div style={{ position: "fixed", left: "50%", bottom: 24, transform: "translateX(-50%)", zIndex: 300, display: "flex", flexDirection: "column", gap: 8, width: "min(480px, calc(100vw - 32px))" }}>
      {items.map((t) => (
        <div key={t.id} role="alert" data-testid="toast" className="card"
          style={{ padding: "10px 12px", display: "flex", gap: 10, alignItems: "flex-start", boxShadow: "0 6px 24px rgba(0,0,0,0.2)",
            borderColor: t.kind === "error" ? "color-mix(in srgb, var(--red) 50%, transparent)" : "var(--border)" }}>
          <span style={{ flex: 1, fontSize: 13, color: t.kind === "error" ? "var(--red)" : "var(--text-primary)" }}>{t.text}</span>
          <button onClick={() => remove(t.id)} aria-label="알림 닫기" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}><X size={14} /></button>
        </div>
      ))}
    </div>
  );
}
