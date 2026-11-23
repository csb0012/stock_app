/**
 * 받아 온 데이터를 브라우저(localStorage)에 저장 → 새로고침·다시 접속해도 마지막 데이터를 바로 보여줌.
 * 화면은 저장된 값을 먼저 그리고, 동시에 최신 데이터를 받아 오면 자동으로 바꿔 끼운다
 * (각 화면에 "마지막 갱신 · 최신 데이터 받는 중" 표시).
 *
 * - 성공한 조회만 저장 (오류는 저장 안 함), 24시간 지난 값은 버림
 * - 검색어 자동완성·챗봇처럼 다시 볼 일 없는 것은 저장 안 함
 * - 로그아웃·로그인 만료 시 지움 (clearPersisted)
 */
import { QueryClient, dehydrate, hydrate } from "@tanstack/react-query";

const KEY = "rq-cache-v1";
const MAX_AGE = 24 * 60 * 60 * 1000;
const SKIP = new Set(["stock-search", "chat-status", "backtest-status"]);

export function restorePersisted(qc: QueryClient) {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (!saved?.ts || Date.now() - saved.ts > MAX_AGE) {
      localStorage.removeItem(KEY);
      return;
    }
    hydrate(qc, saved.state);
  } catch {
    try { localStorage.removeItem(KEY); } catch { /* 저장소 사용 불가 — 무시 */ }
  }
}

export function startPersisting(qc: QueryClient) {
  let timer: number | undefined;
  const save = () => {
    timer = undefined;
    try {
      if (!localStorage.getItem("token")) return;  // 로그아웃 상태면 저장 안 함
      const state = dehydrate(qc, {
        shouldDehydrateQuery: (q) =>
          q.state.status === "success" && !SKIP.has(String(q.queryKey[0])) && Date.now() - q.state.dataUpdatedAt < MAX_AGE,
      });
      localStorage.setItem(KEY, JSON.stringify({ ts: Date.now(), state }));
    } catch {
      // 용량 초과 등 — 저장만 못 할 뿐 화면 동작엔 영향 없음
    }
  };
  qc.getQueryCache().subscribe((e) => {
    if (e.type === "updated" && e.action.type === "success" && timer === undefined) {
      timer = window.setTimeout(save, 1000);  // 여러 조회가 한꺼번에 끝나도 1초에 한 번만 저장
    }
  });
  window.addEventListener("beforeunload", () => timer !== undefined && save());
}

export function clearPersisted(qc?: QueryClient) {
  try { localStorage.removeItem(KEY); } catch { /* 무시 */ }
  qc?.clear();
}
