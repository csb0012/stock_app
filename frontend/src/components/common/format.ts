export function fmtPrice(v: number | null | undefined, market: string): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  return market === "KR"
    ? `₩${Math.round(v).toLocaleString()}`
    : `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtSigned(v: number, digits = 2): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;
}

export function probColor(p: number): string {
  return p >= 65 ? "var(--green)" : p >= 45 ? "var(--yellow)" : "var(--red)";
}

export function probLabel(p: number): string {
  return p >= 65 ? "상승 유력" : p >= 55 ? "약상승" : p >= 45 ? "중립" : p >= 35 ? "약하락" : "하락 주의";
}
