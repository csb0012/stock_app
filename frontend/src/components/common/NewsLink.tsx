/** 뉴스 제목 → 클릭하면 새 탭에서 원문 기사 열기 (http/https 링크만) */
export function safeUrl(url?: string): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

/** 출처 표시: [Reuters] 처럼 매체 이름, 국내 기사(확률 반영 안 함)는 "참고" 표시 */
export function NewsSource({ item }: { item: any }) {
  if (!item?.press && item?.weighted !== false) return null;
  return (
    <span style={{ flexShrink: 0, fontSize: 10, color: "var(--text-muted)", whiteSpace: "nowrap" }}
          title={item?.weighted === false ? "국내 기사 — 확률에 반영하지 않고 참고로만 보여줌" : item?.weighted ? "해외 주요 매체 — 확률에 반영" : undefined}>
      {item?.press && `[${item.press}]`}{item?.weighted === false && " 참고"}
    </span>
  );
}

export default function NewsLink({ item, style }: { item: any; style?: React.CSSProperties }) {
  const href = safeUrl(item?.url);
  const title = [item?.press, item?.date, item?.weighted === false ? "국내 기사 · 확률 미반영(참고)" : item?.weighted ? "해외 기사 · 확률 반영" : ""]
    .filter(Boolean).join(" · ");
  if (!href) return <span style={style} title={title}>{item?.title}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={`${title ? title + " · " : ""}새 탭에서 기사 열기`}
      className="news-link"
      style={style}
      onClick={(e) => e.stopPropagation()}
    >
      {item?.title}
    </a>
  );
}
