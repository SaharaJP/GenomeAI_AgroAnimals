import type { OtherChange } from '@/lib/api/timeline';

type Props = {
  changes: OtherChange[];
};

export function OtherChangesTable({ changes }: Props) {
  if (changes.length === 0) return null;

  return (
    <table className="other-changes-table">
      <thead>
        <tr>
          <th>Метрика</th>
          <th>До</th>
          <th>После</th>
          <th>Изменение</th>
        </tr>
      </thead>
      <tbody>
        {changes.map((c, i) => {
          const dirClass =
            c.direction === 'up'
              ? 'other-changes-delta other-changes-delta--up'
              : c.direction === 'down'
              ? 'other-changes-delta other-changes-delta--down'
              : 'other-changes-delta other-changes-delta--neutral';

          const dirWord =
            c.direction === 'up' ? 'Рост' : c.direction === 'down' ? 'Снижение' : 'Без изменений';

          return (
            <tr key={i}>
              <td>{c.metric}</td>
              <td>{c.before}</td>
              <td>{c.after}</td>
              <td>
                <span className={dirClass}>
                  {c.delta_label}{' '}
                  <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}>
                    ({dirWord})
                  </span>
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
