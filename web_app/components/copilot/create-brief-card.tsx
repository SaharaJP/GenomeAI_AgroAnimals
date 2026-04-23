'use client';

import { DateRangePicker } from '@/lib/date-range-picker';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

type Props = {
  dateStart: string;
  dateEnd: string;
  onDateStartChange: (v: string) => void;
  onDateEndChange: (v: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
};

export function CreateBriefCard({
  dateStart,
  dateEnd,
  onDateStartChange,
  onDateEndChange,
  onSubmit,
  isLoading,
}: Props) {
  const canSubmit = !isLoading && !!dateStart && !!dateEnd && dateStart <= dateEnd;

  return (
    <Card>
      <h2 className="card-title">
        Используйте Помощника для анализа всех данных вашей фермы
      </h2>
      <p className="card-subtitle" style={{ marginBottom: 20, lineHeight: 1.6 }}>
        Выберите начальную и конечную даты, чтобы задать период анализа. Помощник соберёт все
        недельные тренды, которые происходили в этом периоде. Вы получите брифинг на email, как
        только он будет готов. Это может занять до 10 минут.
      </p>
      <DateRangePicker
        start={dateStart}
        end={dateEnd}
        onStartChange={onDateStartChange}
        onEndChange={onDateEndChange}
      />
      <div style={{ marginTop: 20 }}>
        <Button className="button-primary" onClick={onSubmit} disabled={!canSubmit}>
          {isLoading ? 'Генерируется…' : 'Создать брифинг фермы'}
        </Button>
      </div>
    </Card>
  );
}
