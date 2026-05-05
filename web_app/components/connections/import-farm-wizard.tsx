'use client';

import { useState } from 'react';
import { CheckCircle, ChevronLeft } from 'lucide-react';
import Link from 'next/link';

type Provider = {
  id: string;
  name: string;
  sub: string;
  icon: string;
  fields: { id: string; label: string; placeholder: string; type?: string }[];
};

const PROVIDERS: Provider[] = [
  {
    id: 'afifarm',
    name: 'AfiMilk / AfiFarm',
    sub: 'Популярная СУРС',
    icon: '🐄',
    fields: [
      { id: 'host', label: 'Адрес сервера', placeholder: 'https://afifarm.example.com' },
      { id: 'farm_id', label: 'Farm ID', placeholder: 'FARM-001' },
      { id: 'api_key', label: 'API ключ', placeholder: '••••••••••••••••', type: 'password' },
    ],
  },
  {
    id: 'lely',
    name: 'Lely Horizon',
    sub: 'Система управления роботами доения',
    icon: '🤖',
    fields: [
      { id: 'client_id', label: 'Client ID', placeholder: 'horizon-client-id' },
      { id: 'client_secret', label: 'Client Secret', placeholder: '••••••••••••••••', type: 'password' },
      { id: 'farm_guid', label: 'Farm GUID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
    ],
  },
  {
    id: 'delaval',
    name: 'DeLaval DelPro',
    sub: 'Система управления стадом',
    icon: '🏭',
    fields: [
      { id: 'server', label: 'IP / Host сервера', placeholder: '192.168.1.100' },
      { id: 'username', label: 'Логин', placeholder: 'admin' },
      { id: 'password', label: 'Пароль', placeholder: '••••••••••••••••', type: 'password' },
    ],
  },
  {
    id: 'manual',
    name: 'Ручной импорт CSV',
    sub: 'Загрузка файлов вручную',
    icon: '📂',
    fields: [
      { id: 'farm_name', label: 'Название фермы', placeholder: 'Ферма Ивановых' },
      { id: 'timezone', label: 'Часовой пояс', placeholder: 'Europe/Moscow' },
    ],
  },
];

const STEPS = ['Провайдер', 'Настройка', 'Готово'];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="import-steps">
      {STEPS.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 0, flex: i < STEPS.length - 1 ? '1 1 auto' : undefined }}>
            <div className={`import-step${active ? ' import-step--active' : done ? ' import-step--done' : ''}`}>
              <span className="import-step-num">
                {done ? <CheckCircle size={13} /> : i + 1}
              </span>
              <span>{label}</span>
            </div>
            {i < STEPS.length - 1 && <div className="import-step-divider" />}
          </div>
        );
      })}
    </div>
  );
}

export function ImportFarmWizard() {
  const [step, setStep] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const provider = PROVIDERS.find((p) => p.id === selectedId) ?? null;

  function handleFieldChange(id: string, value: string) {
    setFields((prev) => ({ ...prev, [id]: value }));
  }

  function handleNext() {
    if (step === 0 && selectedId) setStep(1);
    else if (step === 1) {
      setLoading(true);
      setTimeout(() => {
        setLoading(false);
        setStep(2);
        setDone(true);
      }, 1400);
    }
  }

  if (done) {
    return (
      <div className="import-page">
        <div className="connections-header" style={{ marginBottom: 24 }}>
          <Link href="/connections">
            <button className="btn-outline-teal" type="button" style={{ gap: 4 }}>
              <ChevronLeft size={14} />
              К фермам
            </button>
          </Link>
        </div>

        <div className="settings-card">
          <div className="empty-illustration">
            <div className="empty-illustration-icon" style={{ background: 'var(--success-bg)', color: 'var(--success-text)' }}>
              <CheckCircle size={26} />
            </div>
            <div className="empty-illustration-title">Ферма подключена!</div>
            <div className="empty-illustration-desc">
              Данные начнут поступать в течение нескольких минут. Среднее время первичной синхронизации — 5–15 минут.
            </div>
            <Link href="/connections">
              <button className="button button-primary" type="button">
                Перейти к фермам
              </button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="import-page">
      {/* Breadcrumb header */}
      <div className="connections-header" style={{ marginBottom: 8 }}>
        <div>
          <h1 className="page-title">Подключить ферму</h1>
          <p className="page-subtitle">Выберите систему управления стадом и введите учётные данные</p>
        </div>
        <Link href="/connections">
          <button className="btn-outline-teal" type="button" style={{ gap: 4 }}>
            <ChevronLeft size={14} />
            Назад
          </button>
        </Link>
      </div>

      <StepIndicator current={step} />

      {step === 0 && (
        <>
          <div className="import-provider-grid">
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`import-provider-card${selectedId === p.id ? ' import-provider-card--active' : ''}`}
                onClick={() => setSelectedId(p.id)}
              >
                <div className="import-provider-logo">{p.icon}</div>
                <div className="import-provider-name">{p.name}</div>
                <div className="import-provider-sub">{p.sub}</div>
              </button>
            ))}
          </div>

          <div className="import-footer">
            <Link href="/connections">
              <button className="button button-secondary" type="button">Отмена</button>
            </Link>
            <button
              className="button button-primary"
              type="button"
              disabled={!selectedId}
              onClick={handleNext}
            >
              Далее
            </button>
          </div>
        </>
      )}

      {step === 1 && provider && (
        <>
          <div className="settings-card" style={{ marginBottom: 16 }}>
            <div style={{ padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid var(--border)' }}>
              <span style={{ fontSize: 24 }}>{provider.icon}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{provider.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{provider.sub}</div>
              </div>
            </div>
            <div className="import-form-section" style={{ padding: 18 }}>
              {provider.fields.map((f) => (
                <div key={f.id} className="import-field">
                  <label className="import-label" htmlFor={f.id}>{f.label}</label>
                  <input
                    id={f.id}
                    className="input"
                    type={f.type ?? 'text'}
                    placeholder={f.placeholder}
                    value={fields[f.id] ?? ''}
                    onChange={(e) => handleFieldChange(f.id, e.target.value)}
                    autoComplete="off"
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="import-footer">
            <button className="button button-secondary" type="button" onClick={() => setStep(0)}>
              <ChevronLeft size={14} />
              Назад
            </button>
            <button
              className="button button-primary"
              type="button"
              disabled={loading}
              onClick={handleNext}
              style={{ minWidth: 120 }}
            >
              {loading ? 'Проверяем…' : 'Подключить'}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
