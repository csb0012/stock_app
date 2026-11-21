import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { stockApi, errMsg } from "../../api/client";

function useDebounce(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/** 종목명/코드 자동완성 검색창 (KIS 공식 종목마스터) */
export default function StockSearchBox({
  market = "ALL",
  placeholder = "종목명 또는 코드 검색 (예: 삼성전자, SOL AI반도체, AAPL)",
  onSelect,
}: {
  market?: string;
  placeholder?: string;
  onSelect: (item: any) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const debounced = useDebounce(q.trim(), 250);
  const boxRef = useRef<HTMLDivElement>(null);

  const { data = [], isFetching, error } = useQuery({
    queryKey: ["stock-search", debounced, market],
    queryFn: () => stockApi.search(debounced, market).then((r) => r.data),
    enabled: debounced.length >= 1,
  });

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const rows = data as any[];

  return (
    <div ref={boxRef} style={{ position: "relative" }}>
      <Search size={14} style={{ position: "absolute", left: 11, top: 12, color: "var(--text-muted)", pointerEvents: "none" }} />
      <input
        value={q}
        placeholder={placeholder}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && rows.length > 0) { onSelect(rows[0]); setOpen(false); }
          if (e.key === "Escape") setOpen(false);
        }}
        style={{ width: "100%", padding: "10px 12px 10px 32px", background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-primary)", fontSize: 14, outline: "none", boxSizing: "border-box" }}
      />
      {open && debounced.length >= 1 && (
        <div className="card" style={{ position: "absolute", top: 44, left: 0, right: 0, zIndex: 50, padding: 4, maxHeight: 320, overflowY: "auto" }}>
          {error ? (
            <p style={{ color: "var(--red)", fontSize: 13, padding: 10 }}>{errMsg(error)}</p>
          ) : isFetching && rows.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: 13, padding: 10 }}>검색 중...</p>
          ) : rows.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: 13, padding: 10 }}>검색 결과 없음</p>
          ) : (
            rows.map((item) => (
              <div
                key={`${item.market}-${item.symbol}`}
                onClick={() => { onSelect(item); setOpen(false); setQ(""); }}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 6, cursor: "pointer" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{item.name}</span>
                {item.type !== "stock" && (
                  <span style={{ fontSize: 10, padding: "2px 5px", borderRadius: 4, background: "color-mix(in srgb, var(--yellow) 15%, transparent)", color: "var(--yellow)" }}>{item.type.toUpperCase()}</span>
                )}
                <span style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, background: item.market === "KR" ? "color-mix(in srgb, var(--accent) 15%, transparent)" : "color-mix(in srgb, var(--green) 15%, transparent)", color: item.market === "KR" ? "var(--accent)" : "var(--green)" }}>
                  {item.exchange}
                </span>
                <span style={{ color: "var(--text-muted)", fontSize: 12, minWidth: 56, textAlign: "right" }}>{item.symbol}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
