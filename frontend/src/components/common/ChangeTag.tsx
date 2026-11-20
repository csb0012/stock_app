interface Props {
  value: number;
  suffix?: string;
  prefix?: string;
}

export default function ChangeTag({ value, suffix = "%", prefix = "" }: Props) {
  const isUp = value > 0;
  const isDown = value < 0;
  const cls = isUp ? "badge-up" : isDown ? "badge-down" : "badge-neutral";
  const sign = isUp ? "+" : "";
  return (
    <span className={`badge ${cls}`}>
      {prefix}{sign}{value.toFixed(2)}{suffix}
    </span>
  );
}
