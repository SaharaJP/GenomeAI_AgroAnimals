import type { ReactNode } from 'react';
export type TableColumn<T> = { key: string; header: string; render: (row: T) => ReactNode };
export function DataTable<T>({
  rows,
  columns,
  onRowClick,
}: {
  rows: T[];
  columns: TableColumn<T>[];
  onRowClick?: (row: T) => void;
}) {
  return (
    <div className="card table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className={onRowClick ? 'clickable' : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((c) => (
                <td key={c.key}>{c.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
