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

// how long after the last key the search starts, so a nick is not looked up per letter
const SEARCH_DELAY_MS = 300;

export function InboxPage() {
  const { t, formatRelative, formatDateTime } = useTranslation();
  const [filter, setFilter] = useState<Filter>('active');
  const [threads, setThreads] = useState<MessageThread[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [thread, setThread] = useState<MessageThreadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  // what is typed in the search box, and what was typed a moment ago and is
  // searched for: the search follows the typing after a short pause
  const [query, setQuery] = useState('');
  const [searched, setSearched] = useState('');
  const searching = searched !== '';

  useEffect(() => {
    const timer = setTimeout(() => setSearched(query.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [query]);

  // A search looks through every thread, set aside or not, so the tabs do not
  // apply to it; without one the tab decides what is listed.
  const fetchThreads = () =>
    messagesApi.threads(searching ? { search: searched } : { aside: filter === 'aside' });

  const loadThreads = () => {
    fetchThreads()
      .then(setThreads)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : t('error.network')));
  };

  useEffect(() => {
    let cancelled = false;
    setThreads(null);
    fetchThreads()
      .then((next) => {
        if (!cancelled) setThreads(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t('error.network'));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, searched]);

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
      loadThreads();
      if (selectedId) messagesApi.thread(selectedId).then(setThread);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('error.network'));
    } finally {
      setSyncing(false);
    }
  };

  const toggleAside = async (target: MessageThread) => {
    const updated = await messagesApi.setAside(target.id, !target.aside);
    // a tab only ever shows threads matching it, and toggling always flips a
    // thread out of it; a search shows both kinds, so the thread stays and is marked
    setThreads((prev) =>
      searching
        ? (prev ?? []).map((item) => (item.id === updated.id ? updated : item))
        : (prev ?? []).filter((item) => item.id !== updated.id),
    );
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
          <div className="inbox-search">
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('inbox.search')}
              aria-label={t('inbox.search')}
              maxLength={100}
            />
            {query && (
              <button
                type="button"
                className="inbox-search-clear"
                onClick={() => {
                  setQuery('');
                  setSearched('');
                }}
                aria-label={t('inbox.searchClear')}
                title={t('inbox.searchClear')}
              >
                ✕
              </button>
            )}
          </div>

          {searching ? (
            threads && <p className="inbox-search-summary">{t('inbox.searchResults', { count: threads.length })}</p>
          ) : (
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
          )}

          {!threads && <p role="status">{t('orders.loading')}</p>}
          {threads && threads.length === 0 && (
            <p role="status" className="inbox-empty">
              {searching
                ? t('inbox.searchEmpty', { query: searched })
                : filter === 'aside'
                  ? t('inbox.asideEmpty')
                  : t('inbox.empty')}
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
                    {searching && item.aside && (
                      <span className="inbox-aside-tag">{t('inbox.filter.aside')}</span>
                    )}
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
