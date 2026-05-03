import { Leaf } from 'lucide-react';
import { LoginForm } from '@/components/auth/login-form';

function LogoMark({ size = 32, bg = '#2dd4bf' }: { size?: number; bg?: string }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.22),
      background: bg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    }}>
      <Leaf size={Math.round(size * 0.44)} strokeWidth={2} color="white" />
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="login-shell">

      {/* ── Left hero panel ── */}
      <div className="login-hero">
        <div className="login-hero-inner">
          <div className="login-hero-logo">
            <LogoMark size={44} bg="rgba(255,255,255,0.18)" />
            <span className="login-hero-wordmark">genomeai агро</span>
          </div>
          <h1 className="login-hero-title">AgroAnimals</h1>
          <p className="login-hero-sub">Система управления молочным стадом</p>
        </div>

        {/* Pastoral illustration */}
        <div className="login-hero-scene">
          <svg viewBox="0 0 560 220" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
            {/* Moon */}
            <circle cx="460" cy="48" r="36" fill="rgba(255,255,255,0.06)"/>
            <circle cx="476" cy="41" r="32" fill="#0d5a52"/>
            {/* Stars */}
            <circle cx="60"  cy="30" r="1.5" fill="white" opacity="0.5"/>
            <circle cx="140" cy="18" r="1"   fill="white" opacity="0.4"/>
            <circle cx="220" cy="38" r="1.5" fill="white" opacity="0.45"/>
            <circle cx="310" cy="14" r="1"   fill="white" opacity="0.5"/>
            <circle cx="390" cy="28" r="1.5" fill="white" opacity="0.4"/>
            <circle cx="510" cy="22" r="1"   fill="white" opacity="0.45"/>
            <circle cx="30"  cy="55" r="1"   fill="white" opacity="0.3"/>
            <circle cx="175" cy="52" r="1"   fill="white" opacity="0.35"/>
            {/* Hills */}
            <ellipse cx="280" cy="260" rx="420" ry="140" fill="rgba(255,255,255,0.05)"/>
            <ellipse cx="60"  cy="280" rx="320" ry="120" fill="rgba(255,255,255,0.07)"/>
            <ellipse cx="500" cy="290" rx="300" ry="110" fill="rgba(255,255,255,0.06)"/>
            <ellipse cx="280" cy="300" rx="500" ry="130" fill="rgba(0,0,0,0.18)"/>
            {/* Cow */}
            <g transform="translate(220,130)" fill="rgba(255,255,255,0.13)">
              <ellipse cx="0" cy="0" rx="55" ry="30"/>
              <rect x="42" y="-22" width="18" height="22" rx="4" transform="rotate(-10 51 -11)"/>
              <ellipse cx="66" cy="-24" rx="20" ry="16"/>
              <ellipse cx="72" cy="-36" rx="7" ry="4" transform="rotate(-20 72 -36)"/>
              <ellipse cx="84" cy="-18" rx="8" ry="5"/>
              <rect x="-35" y="26" width="9" height="32" rx="3"/>
              <rect x="-18" y="26" width="9" height="32" rx="3"/>
              <rect x="14"  y="26" width="9" height="32" rx="3"/>
              <rect x="31"  y="26" width="9" height="32" rx="3"/>
              <ellipse cx="-2" cy="28" rx="18" ry="9"/>
              <path d="M-55,0 Q-75,-8 -70,22 Q-68,32 -62,28" stroke="rgba(255,255,255,0.13)" strokeWidth="4" fill="none" strokeLinecap="round"/>
            </g>
            {/* Second cow */}
            <g transform="translate(410,148) scale(0.55)" fill="rgba(255,255,255,0.08)">
              <ellipse cx="0" cy="0" rx="55" ry="30"/>
              <rect x="42" y="-22" width="18" height="22" rx="4" transform="rotate(-10 51 -11)"/>
              <ellipse cx="66" cy="-24" rx="20" ry="16"/>
              <rect x="-35" y="26" width="9" height="32" rx="3"/>
              <rect x="-18" y="26" width="9" height="32" rx="3"/>
              <rect x="14"  y="26" width="9" height="32" rx="3"/>
              <rect x="31"  y="26" width="9" height="32" rx="3"/>
            </g>
            {/* Fence */}
            <g stroke="rgba(255,255,255,0.1)" strokeWidth="2" strokeLinecap="round">
              <line x1="30"  y1="175" x2="30"  y2="210"/>
              <line x1="75"  y1="173" x2="75"  y2="210"/>
              <line x1="120" y1="172" x2="120" y2="210"/>
              <line x1="165" y1="172" x2="165" y2="210"/>
              <line x1="30"  y1="185" x2="165" y2="183"/>
              <line x1="30"  y1="198" x2="165" y2="196"/>
            </g>
          </svg>
        </div>
      </div>

      {/* ── Right form panel ── */}
      <div className="login-panel">
        <div className="login-card">
          <div className="login-card-logo">
            <LogoMark size={36} bg="#2dd4bf" />
            <span className="login-card-wordmark">genomeai агро</span>
          </div>
          <h2 className="login-card-title">Войти в систему</h2>
          <LoginForm />
        </div>
      </div>

    </div>
  );
}
