'use client';

type DateRangePickerProps = {
  start: string;
  end: string;
  onStartChange: (v: string) => void;
  onEndChange: (v: string) => void;
};

export function DateRangePicker({ start, end, onStartChange, onEndChange }: DateRangePickerProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500 }}>
          Начальная дата
        </label>
        <input
          type="date"
          value={start}
          onChange={(e) => onStartChange(e.target.value)}
          className="input"
          style={{ minWidth: 160 }}
        />
      </div>
      <span style={{ color: 'var(--text-muted)', paddingBottom: 9, fontSize: 16 }}>→</span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500 }}>
          Конечная дата
        </label>
        <input
          type="date"
          value={end}
          onChange={(e) => onEndChange(e.target.value)}
          className="input"
          style={{ minWidth: 160 }}
        />
      </div>
    </div>
  );
}
