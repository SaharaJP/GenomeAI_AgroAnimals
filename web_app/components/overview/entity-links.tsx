import Link from 'next/link';
import type { ReactNode } from 'react';

export type EntityToken =
  | { type: 'text'; value: string }
  | { type: 'animal'; id: string }
  | { type: 'task'; id: string };

// Splits text into plain-text and entity tokens.
// Detects: №123 → animal link, #123 → task link.
export function splitEntityTokens(text: string): EntityToken[] {
  if (!text) return [];
  const tokens: EntityToken[] = [];
  const re = /№(\d+)|#(\d+)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      tokens.push({ type: 'text', value: text.slice(last, match.index) });
    }
    if (match[1]) {
      tokens.push({ type: 'animal', id: match[1] });
    } else {
      tokens.push({ type: 'task', id: match[2] });
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    tokens.push({ type: 'text', value: text.slice(last) });
  }
  return tokens;
}

// Renders text with entity references as clickable badges.
export function renderWithEntityLinks(text: string): ReactNode {
  const tokens = splitEntityTokens(text);
  if (tokens.length === 0) return text;
  return (
    <>
      {tokens.map((token, i) => {
        if (token.type === 'animal') {
          return (
            <Link
              key={i}
              href={`/profiles/animal/${token.id}`}
              className="badge badge-info"
              style={{ textDecoration: 'none', cursor: 'pointer', marginInline: 2 }}
              title={`Открыть карточку животного №${token.id}`}
            >
              🐄 №{token.id}
            </Link>
          );
        }
        if (token.type === 'task') {
          return (
            <Link
              key={i}
              href={`/worklists`}
              className="badge"
              style={{
                background: '#f5f3ff',
                color: '#7c3aed',
                border: '1px solid #ddd6fe',
                textDecoration: 'none',
                cursor: 'pointer',
                marginInline: 2,
              }}
              title={`Открыть задачу #${token.id}`}
            >
              ⚙ #{token.id}
            </Link>
          );
        }
        return <span key={i}>{token.value}</span>;
      })}
    </>
  );
}
