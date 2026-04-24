'use client';

interface ToggleProps {
  on: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}

export function Toggle({ on, onChange, label }: ToggleProps) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={`toggle-track${on ? ' toggle-on' : ''}`}
    >
      <span className="toggle-thumb" />
    </button>
  );
}
