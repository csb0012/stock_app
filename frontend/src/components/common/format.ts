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

/** 원화 금액 (부호 포함): +1.2조 / −350억 / +3,000만 */
export function fmtWon(v: number | null | undefined, signed = true): string {
  if (v == null || Number.isNaN(v)) return "-";
  const sign = !signed ? "" : v > 0 ? "+" : v < 0 ? "−" : "";
  const a = Math.abs(v);
  if (a >= 1e12) return `${sign}${(a / 1e12).toFixed(1)}조`;
  if (a >= 1e8) return `${sign}${Math.round(a / 1e8).toLocaleString()}억`;
  if (a >= 1e4) return `${sign}${Math.round(a / 1e4).toLocaleString()}만`;
  return `${sign}${Math.round(a).toLocaleString()}`;
}

/** 달러 큰 금액: $1.2T / $350B / $40M */
export function fmtUsdBig(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "-";
  const a = Math.abs(v);
  return a >= 1e12 ? `$${(v / 1e12).toFixed(1)}T` : a >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${Math.round(v / 1e6).toLocaleString()}M`;
}

/** 소수 표시 (없으면 -): 12.3 / 12.3% */
export function fmtNum(v: number | null | undefined, digits = 1, suffix = ""): string {
  return v == null || Number.isNaN(v) ? "-" : `${v.toFixed(digits)}${suffix}`;
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
