import type { PropsWithChildren } from 'react';
export function Badge({children,tone='default'}:PropsWithChildren<{tone?:'default'|'success'|'warning'|'danger'}>){const cls=tone==='default'?'badge':`badge badge-${tone}`;return <span className={cls}>{children}</span>}
