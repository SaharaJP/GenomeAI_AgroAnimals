interface Props {
  displayName?: string;
  email?: string;
}

export function AccountDetails({ displayName = 'Андрей Жиров', email = 'icreem714@gmail.com' }: Props) {
  return (
    <section className="settings-section">
      <h2 className="settings-section-title">Account details</h2>
      <div className="settings-card">
        <div className="settings-field-row">
          <div className="settings-field-label">Имя</div>
          <div className="settings-field-value">{displayName}</div>
        </div>
        <div className="settings-field-row">
          <div className="settings-field-label">Email</div>
          <div className="settings-field-value">{email}</div>
        </div>
        <div className="settings-field-row" style={{ borderBottom: 'none' }}>
          <div className="settings-field-label">Language and units</div>
          <div className="settings-field-dropdown">
            <span>🇷🇺</span>
            <span>Русский — кг/°C</span>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
              <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>
      </div>
    </section>
  );
}
