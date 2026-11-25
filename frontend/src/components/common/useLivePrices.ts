import { useQuery } from "@tanstack/react-query";
import { stockApi, marketApi } from "../../api/client";

export type Live = { price: number; change: number | null; change_rate: number | null; volume: number | null; time: string; age: number };

const LIVE_MS = 2000;

/** 국내 실시간 현재가 — 장중에만 2초마다 서버 메모리(KIS 웹소켓으로 받은 값)를 물음. 받은 게 없으면 빈 값 → 화면은 기존 가격 그대로 */
export function useLivePrices(symbols: string[]): Record<string, Live> {
  const uniq = Array.from(new Set(symbols.filter((s) => /^[0-9A-Z]{6}$/.test(s)))).sort().slice(0, 40);
  const status = useQuery({ queryKey: ["market-status"], queryFn: () => marketApi.status().then((r) => r.data), staleTime: 60_000 });
  const open = !!status.data?.KR?.open;
  const q = useQuery({
    queryKey: ["live-prices", uniq.join(",")],
    queryFn: () => stockApi.live(uniq).then((r) => r.data),
    enabled: open && uniq.length > 0,
    refetchInterval: LIVE_MS,
    refetchIntervalInBackground: false,
    staleTime: 0,
    gcTime: 10_000,
  });
  return (open && q.data?.items) || {};
}

/** 화면 행에 실시간 값 덮어쓰기 (현재가·등락률) — live 표시용 표시(live_time)도 붙임 */
export function withLive<T extends { symbol: string; market?: string }>(row: T, live: Record<string, Live>, priceKey = "current_price"): T {
  const l = (row.market === undefined || row.market === "KR") ? live[row.symbol] : undefined;
  if (!l) return row;
  return { ...row, [priceKey]: l.price, change_rate: l.change_rate ?? (row as any).change_rate, live_time: l.time };
}

export const liveTime = (t?: string) => (t && t.length >= 6 ? `${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4, 6)}` : "");
