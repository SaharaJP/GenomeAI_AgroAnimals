import test from 'node:test';
import assert from 'node:assert/strict';
import { validateWorklistInput } from '../lib/api/worklists';

test('validateWorklistInput: blocks empty title', () => {
  const errs = validateWorklistInput({ title: '   ', assignee_team: 'team-health' });
  assert.ok(errs.find((e) => e.field === 'title'));
});

test('validateWorklistInput: accepts valid team task', () => {
  const errs = validateWorklistInput({ title: 'Check cows', assignee_team: 'team-health', priority: 2 });
  assert.equal(errs.length, 0);
});

test('validateWorklistInput: accepts valid personal task', () => {
  const errs = validateWorklistInput({ title: 'Call vet', owner_user_id: 42 });
  assert.equal(errs.length, 0);
});

test('validateWorklistInput: blocks task with neither owner nor team', () => {
  const errs = validateWorklistInput({ title: 'Floating task' });
  assert.ok(errs.find((e) => e.field === 'assignment'));
});

test('validateWorklistInput: blocks priority out of range', () => {
  const errs = validateWorklistInput({ title: 'X', assignee_team: 'team-health', priority: 9 });
  assert.ok(errs.find((e) => e.field === 'priority'));
});

test('validateWorklistInput: priority defaults to 3 when omitted', () => {
  const errs = validateWorklistInput({ title: 'X', assignee_team: 'team-health' });
  assert.equal(errs.length, 0);
});
