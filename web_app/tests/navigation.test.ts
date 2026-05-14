import test from 'node:test';
import assert from 'node:assert/strict';
import { getNavigationSections, pathLabels } from '../lib/navigation';
import type { NavigationItem, NavigationSection } from '../lib/navigation';

function allHrefs(sections: NavigationSection[]): string[] {
  const out: string[] = [];
  for (const s of sections) {
    for (const item of s.items) {
      if (item.kind === 'item') out.push(item.href);
      else for (const c of item.items) out.push(c.href);
    }
  }
  return out;
}

function findGroup(sections: NavigationSection[], label: string) {
  for (const s of sections) {
    for (const item of s.items) {
      if (item.kind === 'group' && item.label === label) return item;
    }
  }
  return null;
}

const meWith = (perms: string[]) => ({
  schema: 'x',
  user: { user_id: 1, username: 'u', role: 'admin', permissions: perms },
  session: { session_id: 's', client_kind: 'web', auth_transport: 'bearer', status: 'active', created_at: '', updated_at: '' },
  scope: { tenant_id: 'default', allowed_farm_ids: [], allowed_site_ids: [] },
});

test('viewer navigation excludes support when permission missing', () => {
  const sections = getNavigationSections(meWith(['reports.read']));
  const hrefs = allHrefs(sections);
  assert.equal(hrefs.includes('/support'), false);
  assert.equal(hrefs.includes('/analytics'), true);
});

test('admin navigation includes support section', () => {
  const sections = getNavigationSections(
    meWith(['support.read', 'alerts.read', 'tasks.read', 'planner.read', 'reports.read', 'assistant.ask', 'decisions.read', 'economics.read']),
  );
  const hrefs = allHrefs(sections);
  assert.equal(hrefs.includes('/support'), true);
  assert.equal(hrefs.includes('/insights'), true);
});

test('canonical labels are renamed', () => {
  assert.equal(pathLabels['/daily-summary'], 'Брифинг');
  assert.equal(pathLabels['/worklists'], 'Задачи');
  assert.equal(pathLabels['/profiles/animal'], 'Животные');
});

test('treatments stays addressable but is hidden from sidebar', () => {
  const sections = getNavigationSections(
    meWith(['support.read', 'alerts.read', 'tasks.read', 'planner.read', 'reports.read', 'assistant.ask', 'decisions.read', 'economics.read', 'kpi.view', 'audit.view', 'jobs.view']),
  );
  const hrefs = allHrefs(sections);
  assert.equal(hrefs.includes('/treatments'), false);
  assert.equal(pathLabels['/treatments'], 'Лечение');
});

test('Стадо group contains four children for kpi.view user', () => {
  const sections = getNavigationSections(meWith(['kpi.view']));
  const stado = findGroup(sections, 'Стадо');
  assert.ok(stado, 'Стадо group must be present');
  const childHrefs = stado.items.map((c) => c.href).sort();
  assert.deepEqual(childHrefs, ['/feeding', '/profiles/animal', '/reproduction', '/vet']);
});

test('Стадо group keeps Животные when user lacks kpi.view', () => {
  const sections = getNavigationSections(meWith([]));
  const stado = findGroup(sections, 'Стадо');
  assert.ok(stado, 'Стадо group must be present (Животные has no permission gate)');
  const childHrefs = stado.items.map((c) => c.href);
  assert.deepEqual(childHrefs, ['/profiles/animal']);
});

test('Стадо children resolve via pathLabels', () => {
  assert.equal(pathLabels['/profiles/animal'], 'Животные');
  assert.equal(pathLabels['/reproduction'], 'Воспроизводство');
  assert.equal(pathLabels['/vet'], 'Ветеринария');
  assert.equal(pathLabels['/feeding'], 'Кормление');
});

test('Управление section no longer contains Repro/Vet', () => {
  const sections = getNavigationSections(
    meWith(['support.read', 'alerts.read', 'tasks.read', 'planner.read', 'reports.read', 'assistant.ask', 'decisions.read', 'economics.read', 'kpi.view']),
  );
  const mgmt = sections.find((s) => s.title === 'Управление');
  assert.ok(mgmt, 'Управление section must exist');
  const hrefs: string[] = [];
  for (const it of mgmt.items) {
    if (it.kind === 'item') hrefs.push(it.href);
    else for (const c of it.items) hrefs.push(c.href);
  }
  assert.equal(hrefs.includes('/reproduction'), false);
  assert.equal(hrefs.includes('/vet'), false);
  assert.deepEqual(hrefs.sort(), ['/decisions', '/economics', '/worklists']);
});

test('Стадо group exposes defaultHref for collapsed sidebar', () => {
  const sections = getNavigationSections(meWith(['kpi.view']));
  const stado = findGroup(sections, 'Стадо');
  assert.ok(stado, 'Стадо group must be present');
  assert.equal(stado.defaultHref, '/profiles/animal');
});
