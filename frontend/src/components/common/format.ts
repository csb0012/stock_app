export function fmtPrice(v: number | null | undefined, market: string): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  return market === "KR"
    ? `₩${Math.round(v).toLocaleString()}`
    : `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 순매수 수량: +9.0만주 / -2,500주 */
export function fmtShares(q: number | null | undefined): string {
  if (q == null) return "-";
  const sign = q > 0 ? "+" : q < 0 ? "−" : "";
  const a = Math.abs(q);
  return a >= 10000 ? `${sign}${(a / 10000).toFixed(1)}만주` : `${sign}${Math.round(a).toLocaleString()}주`;
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

/** 예측 대상 거래일 라벨: "내일" / "오늘" / "월요일(11/23)" (휴장일 반영, 백엔드 계산) */
export function sessionLabel(pred: any): string {
  return pred?.target_label || "다음 거래일";
}
