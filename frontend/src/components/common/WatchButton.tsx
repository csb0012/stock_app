import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Star } from "lucide-react";
import { watchlistApi, errMsg } from "../../api/client";

/** 관심종목 추가 버튼 (이미 있으면 "추가됨") — 목록 행 안에서 써도 행 클릭과 겹치지 않음 */
export default function WatchButton({ item }: { item: { symbol: string; market: string; name: string } }) {
  const qc = useQueryClient();
  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list().then((r) => r.data),
  });
  const add = useMutation({
    mutationFn: () => watchlistApi.add(item.symbol, item.market, item.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  const inList = (watchlist as any[]).some((w) => w.symbol === item.symbol && w.market === item.market);
  return (
    <button
      onClick={(e) => { e.stopPropagation(); if (!inList) add.mutate(); }}
      disabled={inList || add.isPending}
      title={add.error ? `추가 실패: ${errMsg(add.error)}` : undefined}
      style={{
        display: "flex", alignItems: "center", gap: 4, padding: "5px 10px", borderRadius: 6, border: "none",
        cursor: inList ? "default" : "pointer", whiteSpace: "nowrap", fontSize: 12, fontWeight: 500,
        background: inList ? "color-mix(in srgb, var(--green) 10%, transparent)"
          : add.error ? "color-mix(in srgb, var(--red) 10%, transparent)" : "color-mix(in srgb, var(--accent) 10%, transparent)",
        color: inList ? "var(--green)" : add.error ? "var(--red)" : "var(--accent)",
      }}
    >
      {inList ? <Check size={13} /> : <Star size={13} />}
      {inList ? "추가됨" : add.error ? "실패" : "관심"}
    </button>
  );
}
