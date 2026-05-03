import { splitEntityTokens } from '../entity-links';

describe('splitEntityTokens', () => {
  it('returns plain text as single string token', () => {
    expect(splitEntityTokens('Обычный текст')).toEqual([
      { type: 'text', value: 'Обычный текст' },
    ]);
  });

  it('detects animal reference №123', () => {
    const tokens = splitEntityTokens('Осмотреть №847 на мастит');
    expect(tokens).toEqual([
      { type: 'text', value: 'Осмотреть ' },
      { type: 'animal', id: '847' },
      { type: 'text', value: ' на мастит' },
    ]);
  });

  it('detects task reference #1042', () => {
    const tokens = splitEntityTokens('связана с задачей #1042 завтра');
    expect(tokens).toEqual([
      { type: 'text', value: 'связана с задачей ' },
      { type: 'task', id: '1042' },
      { type: 'text', value: ' завтра' },
    ]);
  });

  it('handles multiple entities in one string', () => {
    const tokens = splitEntityTokens('№847 и №391 см. #55');
    expect(tokens).toHaveLength(6);
    expect(tokens[0]).toEqual({ type: 'animal', id: '847' });
    expect(tokens[2]).toEqual({ type: 'animal', id: '391' });
    expect(tokens[4]).toEqual({ type: 'task', id: '55' });
  });

  it('returns empty array for empty string', () => {
    expect(splitEntityTokens('')).toEqual([]);
  });
});
