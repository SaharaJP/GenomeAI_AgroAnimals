// Design tokens — GenomeAI Агро v2 (Connecterra-style, light theme)
// These mirror the CSS variables in globals.css; use in TypeScript where needed.

export const colors = {
  bg: '#ffffff',
  bgMuted: '#f7f9fa',
  panel: '#ffffff',
  panelSubtle: '#f7f9fa',

  border: '#e5e7eb',
  borderStrong: '#d1d5db',

  sidebarBg: '#ffffff',
  sidebarLogoBg: '#2dd4bf',
  sidebarActive: '#e6fff9',
  sidebarActiveText: '#0d9488',
  sidebarHover: '#f7f9fa',

  topbarBg: '#2a3440',
  topbarText: '#ffffff',
  topbarBreadcrumbActive: '#2dd4bf',

  text: '#0f172a',
  textSecondary: '#475569',
  textMuted: '#64748b',
  textOnTeal: '#0d5a52',

  accent: '#2dd4bf',
  accentHover: '#14b8a6',
  accentSoft: '#ccfbf1',
  accentSubtle: '#f0fdfa',
  accentText: '#0f766e',

  success: '#10b981',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#3b82f6',

  withdrawal: '#dc2626',
  freshCow: '#a855f7',
  inHeat: '#ec4899',
  highProducer: '#06b6d4',
} as const;

export const radii = {
  sm: '4px',
  base: '6px',
  lg: '8px',
  pill: '999px',
} as const;

export const shadows = {
  none: 'none',
  sm: '0 1px 2px rgba(0,0,0,0.04)',
  base: '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
  lg: '0 4px 16px rgba(0,0,0,0.08)',
} as const;

export const motion = {
  fast: '120ms',
  base: '200ms',
  ease: 'cubic-bezier(0.2, 0, 0.38, 0.9)',
} as const;

export const layout = {
  sidebarWidth: '220px',
  sidebarCollapsed: '60px',
  topbarHeight: '56px',
  fabSize: '56px',
  mobileTabBarHeight: '56px',
} as const;
