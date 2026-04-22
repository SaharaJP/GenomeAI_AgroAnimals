type Props = {
  farmPct: number;
};

export function ComparisonScale({ farmPct }: Props) {
  const clampedPct = Math.max(0, Math.min(100, farmPct));

  const label =
    clampedPct >= 70
      ? 'Ваша ферма: низкий impact — лучше большинства'
      : clampedPct >= 40
      ? 'Ваша ферма: средний impact — около медианы'
      : 'Ваша ферма: высокий impact — требует внимания';

  return (
    <div className="comparison-scale-wrap">
      <div className="comparison-scale-gradient">
        <div
          className="comparison-scale-marker"
          style={{ left: `${clampedPct}%` }}
          title={`${clampedPct}%`}
        />
      </div>
      <div className="comparison-scale-labels">
        <span>Высокий impact</span>
        <span>Низкий impact</span>
      </div>
      <div className="comparison-scale-farm-label">{label}</div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
        Сравнение с другими фермами: фермы с высоким impact слева, с низким — справа
      </div>
    </div>
  );
}
