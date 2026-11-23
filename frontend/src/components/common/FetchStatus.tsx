import { RefreshCw } from "lucide-react";

/** "11:42:05 기준 · 최신 데이터 받는 중…" — 저장된/이전 데이터를 먼저 보여줄 때 기준 시각과 갱신 상태를 같이 표시 */
export default function FetchStatus({ updatedAt, fetching, error }: {
  updatedAt?: string | number | null;   // 서버 updated_at(ISO) 또는 React Query dataUpdatedAt(ms)
  fetching?: boolean;
  error?: string | null;                // 갱신 실패 사유 (기존 값을 보여주는 중)
}) {
  const d = typeof updatedAt === "number" ? (updatedAt > 0 ? new Date(updatedAt) : null)
    : updatedAt ? new Date(updatedAt) : null;
  if (!d && !fetching) return null;
  const today = new Date().toDateString() === d?.toDateString();
  const label = d
    ? d.toLocaleString("ko-KR", today
        ? { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }
        : { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })
    : null;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: error ? "var(--yellow)" : "var(--text-muted)" }}
          title={error ? `갱신 실패 — 이전 데이터 표시 중: ${error}` : undefined}>
      <RefreshCw size={11} className={fetching ? "spin" : undefined} />
      {label && `${label} 기준`}
      {fetching && (label ? " · 최신 데이터 받는 중…" : "불러오는 중…")}
      {error && !fetching && " · ⚠ 갱신 실패 (이전 데이터)"}
    </span>
  );
}
