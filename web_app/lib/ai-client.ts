/**
 * AI client for ask-farm SSE streaming.
 * Uses fetch() + ReadableStream since POST SSE cannot use EventSource.
 */

export type EvidenceItem = {
  id: string;
  name: string;
  description: string;
  evidenceType: string;
  cowId?: string | null;
  cowName?: string | null;
};

export type AskFarmEvent =
  | { type: 'start'; sessionId: string; model: string }
  | { type: 'token'; text: string }
  | { type: 'evidence'; item: EvidenceItem }
  | { type: 'done'; totalTokens: { input: number; output: number }; evidenceIds: string[] }
  | { type: 'error'; message: string };

export async function* askFarm(
  question: string,
  sessionId?: string,
): AsyncGenerator<AskFarmEvent> {
  let response: Response;
  try {
    response = await fetch('/api/ai/ask-farm', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ question, session_id: sessionId }),
    });
  } catch {
    yield { type: 'error', message: 'Не удалось подключиться к AI-сервису.' };
    return;
  }

  if (!response.ok || !response.body) {
    yield { type: 'error', message: `Ошибка сервера: ${response.status}` };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  let pendingEvent = '';
  let pendingData = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        pendingEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        pendingData = line.slice(6).trim();
      } else if (line === '') {
        if (pendingEvent && pendingData) {
          const parsed = tryParseJson(pendingData);
          if (parsed !== null) {
            const ev = mapEvent(pendingEvent, parsed);
            if (ev) yield ev;
          }
          pendingEvent = '';
          pendingData = '';
        }
      }
    }
  }
}

function tryParseJson(raw: string): Record<string, unknown> | null {
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function mapEvent(
  event: string,
  data: Record<string, unknown>,
): AskFarmEvent | null {
  switch (event) {
    case 'start':
      return {
        type: 'start',
        sessionId: String(data.session_id ?? ''),
        model: String(data.model ?? ''),
      };
    case 'token':
      return { type: 'token', text: String(data.text ?? '') };
    case 'evidence':
      return {
        type: 'evidence',
        item: {
          id: String(data.id ?? ''),
          name: String(data.name ?? data.id ?? ''),
          description: String(data.description ?? ''),
          evidenceType: String(data.type ?? 'event'),
          cowId: (data.cow_id as string | null | undefined) ?? null,
          cowName: (data.cow_name as string | null | undefined) ?? null,
        },
      };
    case 'done':
      return {
        type: 'done',
        totalTokens: {
          input: Number((data.total_tokens as Record<string, unknown>)?.input ?? 0),
          output: Number((data.total_tokens as Record<string, unknown>)?.output ?? 0),
        },
        evidenceIds: (data.evidence_ids as string[] | undefined) ?? [],
      };
    case 'error':
      return { type: 'error', message: String(data.message ?? 'Неизвестная ошибка') };
    default:
      return null;
  }
}

/**
 * Parses response text and splits it into segments:
 * - plain text segments
 * - evidence marker segments (to render as chips)
 */
export type TextSegment =
  | { kind: 'text'; text: string }
  | { kind: 'evidence'; evidenceId: string };

export function parseTextSegments(text: string): TextSegment[] {
  const segments: TextSegment[] = [];
  const re = /\[evidence:\s*(\w+)\]/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      segments.push({ kind: 'text', text: text.slice(last, match.index) });
    }
    segments.push({ kind: 'evidence', evidenceId: match[1] });
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    segments.push({ kind: 'text', text: text.slice(last) });
  }

  return segments;
}
