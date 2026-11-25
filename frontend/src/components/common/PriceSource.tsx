/** 미국 현재가 출처 — KIS 해외 현재가를 못 받아 Yahoo 가격을 쓸 때만 표시 (최대 15분 늦을 수 있음) */
export default function PriceSource({ src }: { src?: string | null }) {
  if (!src || !src.startsWith("Yahoo (KIS")) return null;
  return (
    <span data-testid="price-source" title="KIS 해외 현재가를 못 받아 Yahoo 가격을 표시 중 — 최대 15분 늦을 수 있음"
      style={{ fontSize: 10.5, color: "var(--yellow)", whiteSpace: "nowrap" }}>Yahoo·지연 가능</span>
  );
}
