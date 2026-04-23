'use client';

import { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';

interface InsightEvent {
  event: 'new_insights';
  farm_id: string;
  count: number;
}

interface Props {
  farmId?: string;
}

export function InsightNotificationBell({ farmId = 'demo-farm-v1' }: Props) {
  const [unreadCount, setUnreadCount] = useState(0);
  const [scanning, setScanning] = useState(false);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // Connect to SSE stream on mount
  useEffect(() => {
    const url = `/api/ai/insights/events/stream?farm_id=${farmId}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const payload: InsightEvent = JSON.parse(e.data);
        if (payload.event === 'new_insights' && payload.count > 0) {
          setUnreadCount((prev) => prev + payload.count);
        }
      } catch {
        // keepalive comment — ignore
      }
    };

    es.onerror = () => {
      // Reconnect handled by browser automatically for EventSource
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [farmId]);

  async function handleScanNow() {
    setScanning(true);
    setLastMessage(null);
    try {
      const res = await fetch(`/api/ai/insights/scan-now?farm_id=${farmId}`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setLastMessage(data.message ?? 'Готово');
        // SSE will deliver the count update automatically
      } else {
        setLastMessage('Ошибка сканирования');
      }
    } catch {
      setLastMessage('Ошибка соединения');
    } finally {
      setScanning(false);
    }
  }

  function handleBellClick() {
    setUnreadCount(0);
    // Navigate to insights page — let parent handle routing if needed
    window.location.href = '/alerts';
  }

  return (
    <div className="insight-bell" aria-label="Уведомления инсайтов">
      {/* Bell icon with badge */}
      <button
        className="insight-bell__btn"
        onClick={handleBellClick}
        aria-label={
          unreadCount > 0 ? `${unreadCount} новых инсайта` : 'Инсайты'
        }
        title="Перейти к инсайтам"
      >
        <Bell size={18} strokeWidth={2} />
        {unreadCount > 0 && (
          <span className="insight-bell__badge" aria-hidden="true">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Manual scan trigger */}
      <button
        className="insight-bell__scan-btn"
        onClick={handleScanNow}
        disabled={scanning}
        aria-label="Запустить сканирование инсайтов"
        title="Сканировать сейчас"
      >
        {scanning ? '...' : '↻'}
      </button>

      {/* Status message */}
      {lastMessage && (
        <span className="insight-bell__msg" role="status">
          {lastMessage}
        </span>
      )}
    </div>
  );
}
