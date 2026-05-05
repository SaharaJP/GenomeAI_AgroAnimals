import { Card } from '@/components/ui/card';

export function FactPackGuardrailNote({ compact = false }: { compact?: boolean }) {
  return (
    <Card>
      <h3 className="card-title">Только проверенные данные</h3>
      <p className="card-subtitle">
        Объяснения, контекст помощника и виджеты решений отображают только привязки, коды причин и версионированные факты с бэкенда.
        Браузер не вычисляет факторы и не пересчитывает логику объяснений.
      </p>
      {!compact ? (
        <ul className="bullet-list compact">
          <li>Привязка к источнику сохраняется: data_version / model_version / report_version.</li>
          <li>Помощник ограничен и управляется сервером.</li>
          <li>Неизвестные значения отображаются как н/д, а не выводятся умозрительно.</li>
        </ul>
      ) : null}
    </Card>
  );
}
