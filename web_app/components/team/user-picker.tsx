'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { listActiveUsers, type AuthUserSummary } from '@/lib/api/users-v2';

type Props = {
  value: number | null;
  onChange: (userId: number | null) => void;
  disabled?: boolean;
  placeholder?: string;
};

export function UserPicker({ value, onChange, disabled, placeholder }: Props) {
  const [users, setUsers] = useState<AuthUserSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    listActiveUsers()
      .then((list) => {
        if (alive) setUsers(list);
      })
      .catch((e: unknown) => {
        if (alive) setLoadError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const selected = useMemo<AuthUserSummary | null>(() => {
    if (value == null || !users) return null;
    return users.find((u) => u.id === value) ?? null;
  }, [value, users]);

  const filtered = useMemo<AuthUserSummary[]>(() => {
    if (!users) return [];
    const q = query.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        u.username.toLowerCase().includes(q) ||
        String(u.id).includes(q) ||
        (u.role ?? '').toLowerCase().includes(q),
    );
  }, [query, users]);

  if (loadError) {
    return (
      <div className="user-picker user-picker--fallback">
        <input
          type="number"
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
          disabled={disabled}
          placeholder={placeholder ?? 'пусто = отвязать'}
        />
        <span className="task-create-form__hint">
          Список auth-пользователей недоступен ({loadError}). Введите id вручную.
        </span>
      </div>
    );
  }

  const displayLabel =
    users === null
      ? 'Загружаю пользователей…'
      : value == null
        ? (placeholder ?? 'не привязан')
        : selected
          ? `${selected.username} · id=${selected.id}${selected.role ? ` · ${selected.role}` : ''}`
          : `user_id=${value} · не найден среди активных`;

  return (
    <div className="user-picker" ref={rootRef} style={{ position: 'relative' }}>
      <button
        type="button"
        className="user-picker__display"
        onClick={() => !disabled && users !== null && setOpen((o) => !o)}
        disabled={disabled || users === null}
        aria-haspopup="listbox"
        aria-expanded={open}
        style={{
          width: '100%',
          textAlign: 'left',
          padding: '6px 10px',
          border: '1px solid var(--border, #d0d5dd)',
          borderRadius: 6,
          background: disabled ? 'var(--surface-muted, #f5f5f5)' : 'var(--surface, white)',
          cursor: disabled || users === null ? 'default' : 'pointer',
        }}
      >
        {displayLabel}
      </button>
      {open && users && (
        <div
          className="user-picker__popover"
          role="listbox"
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 30,
            background: 'var(--surface, white)',
            border: '1px solid var(--border, #d0d5dd)',
            borderRadius: 6,
            boxShadow: '0 6px 24px rgba(15, 23, 42, 0.12)',
            maxHeight: 320,
            overflowY: 'auto',
          }}
        >
          <input
            type="search"
            autoFocus
            className="user-picker__search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск по username / роли / id…"
            style={{ width: '100%', padding: '8px 10px', border: 'none', borderBottom: '1px solid var(--border, #e4e7ec)' }}
          />
          <button
            type="button"
            className="user-picker__option user-picker__option--clear"
            onClick={() => {
              onChange(null);
              setOpen(false);
              setQuery('');
            }}
            style={{ width: '100%', textAlign: 'left', padding: '8px 10px', border: 'none', background: 'transparent', color: 'var(--text-muted, #667085)', cursor: 'pointer' }}
          >
            — отвязать —
          </button>
          {filtered.length === 0 ? (
            <div className="user-picker__empty" style={{ padding: '8px 10px', color: 'var(--text-muted, #667085)' }}>
              Ничего не найдено
            </div>
          ) : (
            filtered.slice(0, 50).map((u) => {
              const isSelected = u.id === value;
              return (
                <button
                  key={u.id}
                  type="button"
                  className={`user-picker__option${isSelected ? ' is-selected' : ''}`}
                  onClick={() => {
                    onChange(u.id);
                    setOpen(false);
                    setQuery('');
                  }}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    padding: '8px 10px',
                    border: 'none',
                    background: isSelected ? 'var(--surface-accent, #eef4ff)' : 'transparent',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                >
                  <span>{u.username}</span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted, #667085)' }}>
                    id={u.id}
                    {u.role ? ` · ${u.role}` : ''}
                  </span>
                </button>
              );
            })
          )}
          {filtered.length > 50 ? (
            <div className="user-picker__hint" style={{ padding: '6px 10px', fontSize: 12, color: 'var(--text-muted, #667085)' }}>
              …ещё {filtered.length - 50}. Уточните поиск.
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
