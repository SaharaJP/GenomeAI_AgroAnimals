import { Info } from 'lucide-react';

export function InfoBanner() {
  return (
    <div className="overview-info-banner">
      <Info size={16} style={{ flexShrink: 0, marginTop: 1 }} />
      <span>
        Это демо-ферма с тестовыми данными. Она показывает, что приложение делает, как только ваши данные будут подключены.
      </span>
    </div>
  );
}
