import { useEffect, useState } from "react";

/** 휴대폰처럼 좁은 화면인지 (기본 640px 이하) — 표 대신 카드로 보여줄 때 */
export function useNarrow(px = 640): boolean {
  const q = `(max-width: ${px}px)`;
  const [m, setM] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const f = () => setM(mq.matches);
    f();
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, [q]);
  return m;
}
