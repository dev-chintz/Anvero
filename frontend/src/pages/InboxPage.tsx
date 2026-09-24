import { useEffect, useState } from 'react';
import {
  ApiError,
  messagesApi,
  type MessageThread,
  type MessageThreadDetail,
} from '../api/client';
import { useTranslation } from '../i18n';
import '../styles/InboxPage.css';

type Filter = 'active' | 'aside';

export function InboxPage() {
  const { t, formatRelative, formatDateTime } = useTranslation();
  const [filter, setFilter] = useState<Filter>('active');
  const [threads, setThreads] = useState<MessageThread[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [thread, setThread] = useState<MessageThreadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const loadThreads = (which: Filter) => {
    messagesApi
      .threads({ aside: which === 'aside' })
      .then(setThreads)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : t('error.network')));
  };

  useEffect(() => {
    setThreads(null);
    loadThreads(filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  useEffect(() => {
    if (!selectedId) {
      setThread(null);
      return;
    }
    let cancelled = false;
    messagesApi
      .thread(selectedId)
      .then((next) => {
        if (!cancelled) setThread(next);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : t('error.network')));
    return () => {
      cancelled = true;
    };
  }, [selectedId, t]);

  const sync = async () => {
    setSyncing(true);
    try {
      await messagesApi.syncAllegro();
      loadThreads(filter);
      if (selectedId) messagesApi.thread(selectedId).then(setThread);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('error.network'));
    } finally {
      setSyncing(false);
    }
  };

  const toggleAside = async (target: MessageThread) => {
    const updated = await messagesApi.setAside(target.id, !target.aside);
    // the list only ever shows threads matching the current filter, and
    // toggling always flips a thread out of it, never into it
    setThreads((prev) => (prev ?? []).filter((item) => item.id !== updated.id));
    if (thread?.id === updated.id) setThread({ ...thread, aside: updated.aside });
  };

  return (
    <div className="inbox-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('inbox.title')}</h1>
          <p className="subtitle">{t('inbox.subtitle')}</p>
        </div>
        <button type="button" className="print-button" onClick={sync} disabled={syncing}>
          {syncing ? t('inbox.syncing') : t('inbox.sync')}
        </button>
      </header>

      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      <div className="inbox-body">
        <div className="inbox-list-pane">
          <div className="inbox-filters" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={filter === 'active'}
              className={filter === 'active' ? 'active' : ''}
              onClick={() => setFilter('active')}
            >
              {t('inbox.filter.active')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={filter === 'aside'}
              className={filter === 'aside' ? 'active' : ''}
              onClick={() => setFilter('aside')}
            >
              {t('inbox.filter.aside')}
            </button>
          </div>

          {!threads && <p role="status">{t('orders.loading')}</p>}
          {threads && threads.length === 0 && (
            <p role="status" className="inbox-empty">
              {filter === 'aside' ? t('inbox.asideEmpty') : t('inbox.empty')}
            </p>
          )}

          <ul className="inbox-thread-list">
            {threads?.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={`inbox-thread-item ${item.id === selectedId ? 'selected' : ''} ${!item.read ? 'unread' : ''}`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <div className="inbox-thread-item-top">
                    <span className="inbox-source-badge">{item.source}</span>
                    <span className="inbox-thread-buyer">{item.interlocutor_login ?? '—'}</span>
                    {!item.read && <span className="inbox-unread-dot" aria-hidden="true" />}
                  </div>
                  <p className="inbox-thread-excerpt">{item.last_message_text ?? ''}</p>
                  <div className="inbox-thread-item-bottom">
                    <span>{item.order_external_id ? t('inbox.order', { order: item.order_external_id }) : t('inbox.noOrder')}</span>
                    {item.last_message_at && <span>{formatRelative(item.last_message_at)}</span>}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="inbox-detail-pane">
          {!thread && <p role="status" className="inbox-select-hint">{t('inbox.selectThread')}</p>}
          {thread && (
            <ThreadDetail
              thread={thread}
              onThreadChange={setThread}
              onAsideToggle={() => toggleAside(thread)}
              formatDateTime={formatDateTime}
              t={t}
            />
          )}
        </div>
      </div>
    </div>
  );
}

interface ThreadDetailProps {
  thread: MessageThreadDetail;
  onThreadChange: (thread: MessageThreadDetail) => void;
  onAsideToggle: () => void;
  formatDateTime: ReturnType<typeof useTranslation>['formatDateTime'];
  t: ReturnType<typeof useTranslation>['t'];
}

function ThreadDetail({ thread, onThreadChange, onAsideToggle, formatDateTime, t }: ThreadDetailProps) {
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.trim()) return;
    setSending(true);
    setStatus(null);
    try {
      const result = await messagesApi.reply(thread.id, draft.trim());
      onThreadChange(result.thread);
      setDraft('');
      setStatus(
        result.marketplace_write.outcome === 'DRY_RUN'
          ? t('inbox.reply.dryRun')
          : result.marketplace_write.outcome === 'SENT'
            ? t('inbox.reply.sent')
            : t('inbox.reply.failed', { detail: result.marketplace_write.detail ?? '' }),
      );
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : t('error.network'));
    } finally {
      setSending(false);
    }
  };

  const canReply = thread.source === 'ALLEGRO';

  return (
    <div className="inbox-thread-detail">
      <div className="inbox-thread-detail-header">
        <div>
          <strong>{thread.interlocutor_login ?? '—'}</strong>
          <span className="inbox-source-badge">{thread.source}</span>
        </div>
        <button type="button" className="print-button" onClick={onAsideToggle}>
          {thread.aside ? t('inbox.bringBack') : t('inbox.putAside')}
        </button>
      </div>

      <div className="inbox-message-list">
        {thread.messages.map((message) => (
          <div key={message.id} className={`inbox-message inbox-message-${message.direction}`}>
            <div className="inbox-message-meta">
              <span>{message.direction === 'OUT' && message.created_in_anvero ? t('inbox.you') : message.author_login ?? ''}</span>
              <span>{formatDateTime(message.sent_at)}</span>
            </div>
            <p>{message.text}</p>
          </div>
        ))}
      </div>

      {canReply ? (
        <form className="inbox-reply-form" onSubmit={send}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={t('inbox.reply.placeholder')}
            rows={3}
            disabled={sending}
          />
          <button type="submit" disabled={sending || !draft.trim()}>
            {sending ? t('inbox.reply.sending') : t('inbox.reply.send')}
          </button>
          {status && <p role="status" className="inbox-reply-status">{status}</p>}
        </form>
      ) : (
        <p role="status" className="inbox-reply-status">{t('inbox.erliUnsupported')}</p>
      )}
    </div>
  );
}
