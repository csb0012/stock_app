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

export default function NewsLink({ item, style }: { item: any; style?: React.CSSProperties }) {
  const href = safeUrl(item?.url);
  const title = [item?.press, item?.date].filter(Boolean).join(" · ");
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
