import test from 'node:test';
import assert from 'node:assert/strict';
import { buildPersonnelPatch, validatePersonnelUpdate } from '../lib/api/personnel';

test('validatePersonnelUpdate: blocks empty full_name', () => {
  const errs = validatePersonnelUpdate({ full_name: '  ' });
  assert.ok(errs.find((e) => e.field === 'full_name'));
});

test('validatePersonnelUpdate: blocks empty position', () => {
  const errs = validatePersonnelUpdate({ position: '' });
  assert.ok(errs.find((e) => e.field === 'position'));
});

test('validatePersonnelUpdate: accepts null position (no-op patch)', () => {
  const errs = validatePersonnelUpdate({ position: null });
  assert.equal(errs.length, 0);
});

test('validatePersonnelUpdate: blocks invalid email', () => {
  const errs = validatePersonnelUpdate({ email: 'not-an-email' });
  assert.ok(errs.find((e) => e.field === 'email'));
});

test('validatePersonnelUpdate: accepts valid update', () => {
  const errs = validatePersonnelUpdate({ full_name: 'A B', position: 'Vet', email: 'a@b.c' });
  assert.equal(errs.length, 0);
});

test('buildPersonnelPatch: emits only changed fields', () => {
  const initial = { full_name: 'A', position: 'Vet', phone: '+7' };
  const next = { full_name: 'A', position: 'Senior Vet', phone: '+7' };
  const patch = buildPersonnelPatch(initial, next);
  assert.deepEqual(patch, { position: 'Senior Vet' });
});

test('buildPersonnelPatch: trims strings when comparing', () => {
  const initial = { position: 'Vet' };
  const next = { position: '  Vet  ' };
  const patch = buildPersonnelPatch(initial, next);
  assert.deepEqual(patch, {});
});

test('buildPersonnelPatch: detects null -> value', () => {
  const initial = { phone: null };
  const next = { phone: '+79991234567' };
  const patch = buildPersonnelPatch(initial, next);
  assert.deepEqual(patch, { phone: '+79991234567' });
});

test('buildPersonnelPatch: detects value -> null (unlink)', () => {
  const initial = { user_id: 42 };
  const next = { user_id: null };
  const patch = buildPersonnelPatch(initial, next);
  assert.deepEqual(patch, { user_id: null });
});
