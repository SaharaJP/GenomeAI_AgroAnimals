import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    integrations: [
      {
        id: 'bovSync',
        system: 'BoviSync',
        dataTypes: 'Данные коров, Доильная система, Тест молока',
        lastUpdated: 'Суббота, 21 марта 2026, 01:02',
      },
      {
        id: 'datamars',
        system: 'Datamars Livestock Active Tag',
        dataTypes: 'Поведение',
        lastUpdated: 'Суббота, 21 марта 2026, 12:04',
      },
      {
        id: 'dfa',
        system: 'DFA',
        dataTypes: 'Вывоз молока',
        lastUpdated: 'Суббота, 21 марта 2026, 13:00',
      },
    ],
  });
}
