import { Fragment, type ReactNode } from "react";

/** 챗봇 답변용 가벼운 마크다운 표시: 제목(#), 목록(- / 1.), 표(| a | b |), 굵게(**), 코드(`) — HTML 은 그대로 글자로 (주입 없음) */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m: RegExpExecArray | null, k = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    out.push(t.startsWith("**")
      ? <strong key={k++}>{t.slice(2, -2)}</strong>
      : <code key={k++} style={{ background: "var(--bg-secondary)", padding: "0 4px", borderRadius: 4 }}>{t.slice(1, -1)}</code>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export default function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    // 표
    if (line.trim().startsWith("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]));
      blocks.push(
        <div key={blocks.length} style={{ overflowX: "auto", margin: "6px 0" }}>
          <table style={{ borderCollapse: "collapse", fontSize: 12, minWidth: "100%" }}>
            <thead><tr>{head.map((h, j) => <th key={j} style={{ textAlign: "left", padding: "5px 8px", borderBottom: "1px solid var(--border)", color: "var(--text-muted)", whiteSpace: "nowrap" }}>{inline(h)}</th>)}</tr></thead>
            <tbody>{rows.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j} style={{ padding: "5px 8px", borderBottom: "1px solid var(--border)" }}>{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
      continue;
    }
    // 목록
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const items: { text: string; indent: number }[] = [];
      const ordered = /^\s*\d+\./.test(line);
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        const l = lines[i++];
        items.push({ text: l.replace(/^\s*([-*]|\d+\.)\s+/, ""), indent: (l.match(/^\s*/)?.[0].length || 0) >= 2 ? 1 : 0 });
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(
        <Tag key={blocks.length} style={{ margin: "4px 0", paddingLeft: 20, display: "flex", flexDirection: "column", gap: 2, listStyle: ordered ? "decimal" : "disc" }}>
          {items.map((it, j) => <li key={j} style={{ marginLeft: it.indent * 16 }}>{inline(it.text)}</li>)}
        </Tag>
      );
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) {
      blocks.push(<p key={blocks.length} style={{ fontWeight: 700, fontSize: h[1].length <= 2 ? 15 : 14, margin: "8px 0 2px" }}>{inline(h[2])}</p>);
    } else if (/^\s*---+\s*$/.test(line)) {
      blocks.push(<hr key={blocks.length} style={{ border: "none", borderTop: "1px solid var(--border)", margin: "8px 0" }} />);
    } else if (line.trim()) {
      blocks.push(<p key={blocks.length} style={{ margin: "2px 0" }}>{inline(line)}</p>);
    } else {
      blocks.push(<div key={blocks.length} style={{ height: 6 }} />);
    }
    i++;
  }
  return <Fragment>{blocks}</Fragment>;
}
