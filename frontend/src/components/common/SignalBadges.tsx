/** 투자 신호 (AI 추천 카드·종목 상세): 투자 대가(13F) · 가치·재무 · 수급(쌍끌이) + 장기 점수 보정 내역
 *  점수 보정은 검증된 신호만 (서버 signals.py) — 나머지는 '참고'로 흐리게 */
import { fmtNum, fmtWon } from "./format";

const CHANGE: Record<string, string> = { new: "신규 매수", add: "추가 매수", reduce: "일부 매도", sold: "전량 매도", same: "유지" };

export function changeLabel(c: string | null | undefined, pct?: number | null): string {
  if (!c) return "-";
  if ((c === "add" || c === "reduce") && pct != null) return `${CHANGE[c]} ${pct > 0 ? "+" : ""}${pct}%`;
  return CHANGE[c] || c;
}

export function changeColor(c: string | null | undefined): string {
  return c === "new" || c === "add" ? "var(--green)" : c === "reduce" || c === "sold" ? "var(--red)" : "var(--text-muted)";
}

function Pill({ children, color, title, testid }: { children: React.ReactNode; color: string; title?: string; testid?: string }) {
  return (
    <span className="badge" data-testid={testid} title={title}
      style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color, whiteSpace: "nowrap", fontSize: 11 }}>
      {children}
    </span>
  );
}

export default function SignalBadges({ s, compact = false }: { s?: any; compact?: boolean }) {
  if (!s) return null;
  const g = s.guru, v = s.value, f = s.flow;
  const parts: any[] = s.score_parts || [];
  const hasAny = g || v || f?.label;
  if (!hasAny) return null;
  const partTip = parts.length
    ? "장기 점수 보정: " + parts.map((p) => `${p.label} ${p.points > 0 ? "+" : ""}${p.points} (${p.note})`).join(" · ")
    : "";
  return (
    <div data-testid="signal-badges" style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", fontSize: 11.5 }}>
      {g && (
        <Pill testid="guru-badge" color={g.n_buyers > 0 ? "var(--green)" : g.n_sellers > g.n_holders ? "var(--red)" : "var(--accent)"}
          title={`SEC 13F (${g.period ?? "-"} 기준, 최대 45일 늦게 공개)\n` +
            `보유: ${g.holders.map((h: any) => `${h.name} ${h.weight}% ${changeLabel(h.change, h.share_change_pct)}`).join(", ") || "-"}\n` +
            (g.sellers.length ? `판 대가: ${g.sellers.map((h: any) => `${h.name}(${changeLabel(h.change)})`).join(", ")}\n` : "") +
            (g.validation?.n ? `따라 사기 검증: 공시 다음 날 사서 ${g.validation.horizon_days}거래일, S&P500 대비 평균 ${g.validation.avg_excess > 0 ? "+" : ""}${g.validation.avg_excess}%p · 이긴 비율 ${g.validation.beat_rate}% (${g.validation.n}건)` : "따라 사기 검증 표본 부족") +
            (g.validated ? ` → 장기 점수 +${g.points}` : " → 검증 미달이라 점수엔 안 넣음")}>
          🧑‍💼 대가 {g.n_holders}명 보유{g.n_buyers ? ` · ${g.buyers[0]?.name}${g.n_buyers > 1 ? ` 외 ${g.n_buyers - 1}명` : ""} 매수` : ""}
          {g.n_sellers ? ` · ${g.n_sellers}명 매도` : ""}
        </Pill>
      )}
      {g?.n_recent_buys > 0 && (
        <Pill testid="guru-recent-badge" color="var(--green)"
          title={"13F 이후 최근 공시 (Form 4 · 13D/13G · ARK 매일):\n" + (g.recent || []).map((x: any) => `${x.date} ${x.name} ${x.form} ${x.kind}`).join("\n")}>
          대가 최근 매수 {g.n_recent_buys}명 ({g.recent?.[0]?.form})
        </Pill>
      )}
      {v && (v.per != null || v.pbr != null) && (
        <Pill testid="value-badge" color="var(--text-secondary)"
          title={`최근 4분기 실적(${v.q?.slice(0, 4)}.${v.q?.slice(4)} 까지, 네이버 증권) 기준\n` +
            `PER ${fmtNum(v.per)} · PBR ${fmtNum(v.pbr, 2)} · ROE ${fmtNum(v.roe, 1, "%")} · 영업이익률 ${fmtNum(v.op_margin, 1, "%")}\n` +
            `매출 성장 ${fmtNum(v.sales_yoy, 1, "%")} · 영업이익 성장 ${fmtNum(v.op_yoy, 1, "%")} (전년 같은 분기) · 배당 ${fmtNum(v.div_yield, 1, "%")} · 부채비율 ${fmtNum(v.debt, 0, "%")}`}>
          PER {fmtNum(v.per)} · PBR {fmtNum(v.pbr, 2)}{v.roe != null && ` · ROE ${fmtNum(v.roe, 0, "%")}`}
          {!compact && v.div_yield > 0 && ` · 배당 ${fmtNum(v.div_yield, 1, "%")}`}
        </Pill>
      )}
      {f?.label && (
        <Pill testid="flow-badge" color={f.streak > 0 || (f.frgn5 + f.orgn5 > 0 && f.prsn5 < 0) ? "var(--green)" : "var(--red)"}
          title={`${f.date} 까지 ${f.days}거래일 순매수 (금액은 수량×종가 어림)\n외국인 ${fmtWon(f.frgn_amt5)} · 기관 ${fmtWon(f.orgn_amt5)} · 개인 ${fmtWon(f.prsn_amt5)}`}>
          {f.label}
        </Pill>
      )}
      {parts.some((p) => p.points) && (
        <span title={partTip} style={{ color: s.bonus > 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
          장기 {s.bonus > 0 ? "+" : ""}{s.bonus}
        </span>
      )}
    </div>
  );
}
