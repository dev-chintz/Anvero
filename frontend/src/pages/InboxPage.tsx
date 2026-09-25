import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  messagesApi,
  type MessageThread,
  type MessageThreadDetail,
} from '../api/client';
import { useTranslation } from '../i18n';
import { groupThreads, waitingHours, waitingTone } from './inbox/groupThreads';
import '../styles/InboxPage.css';

type Filter = 'active' | 'aside';

// how long after the last key the search starts, so a nick is not looked up per letter
const SEARCH_DELAY_MS = 300;

interface Counts {
  active: number | null;
  aside: number | null;
}

export function InboxPage() {
  const { t, tc, formatRelative, formatDateTime } = useTranslation();
  const [filter, setFilter] = useState<Filter>('active');
  const [threads, setThreads] = useState<MessageThread[] | null>(null);
  const [counts, setCounts] = useState<Counts>({ active: null, aside: null });
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

  // how many each tab holds, so both are known while only one is listed
  const loadCounts = () =>
    Promise.all([messagesApi.threads({ aside: false }), messagesApi.threads({ aside: true })])
      .then(([active, aside]) => setCounts({ active: active.length, aside: aside.length }))
      // the tabs simply show no figure; the list says what is wrong
      .catch(() => undefined);

  useEffect(() => {
    loadCounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
        if (cancelled) return;
        setThreads(next);
        // what a tab lists is what it holds
        if (!searching) setCounts((current) => ({ ...current, [filter]: next.length }));
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
      loadCounts();
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
    // one fewer in the tab it left, one more in the tab it joined
    setCounts((current) => {
      const step = updated.aside ? 1 : -1;
      return {
        active: current.active === null ? null : Math.max(0, current.active - step),
        aside: current.aside === null ? null : Math.max(0, current.aside + step),
      };
    });
    if (thread?.id === updated.id) setThread({ ...thread, aside: updated.aside });
  };

  // the thread as the list has it: what the detail was opened from (whether it was unread, and since when)
  const listed = threads?.find((item) => item.id === selectedId) ?? null;
  const groups = threads ? groupThreads(threads) : [];
  const now = new Date();

  const waitingChip = (item: MessageThread) => {
    const hours = waitingHours(item, now);
    if (hours === null) return null;
    return (
      <span className={`inbox-chip inbox-chip-${waitingTone(hours)}`}>
        {hours < 24
          ? tc('inbox.waiting.hours', Math.max(1, hours))
          : tc('inbox.waiting.days', Math.floor(hours / 24))}
      </span>
    );
  };

  const tabCount = (count: number | null) =>
    count === null ? null : <span className="inbox-tab-count">{count}</span>;

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

      <div className={`inbox-body${thread ? ' has-thread' : ''}`}>
        <section className="inbox-list card" aria-label={t('inbox.title')}>
          <div className="inbox-toolbar">
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
                  {tabCount(counts.active)}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={filter === 'aside'}
                  className={filter === 'aside' ? 'active' : ''}
                  onClick={() => setFilter('aside')}
                >
                  {t('inbox.filter.aside')}
                  {tabCount(counts.aside)}
                </button>
              </div>
            )}

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
          </div>

          {!threads && <p role="status" className="inbox-note">{t('orders.loading')}</p>}
          {threads && threads.length === 0 && (
            <p role="status" className="inbox-note inbox-empty">
              {searching
                ? t('inbox.searchEmpty', { query: searched })
                : filter === 'aside'
                  ? t('inbox.asideEmpty')
                  : t('inbox.empty')}
            </p>
          )}

          {groups.map((group) => (
            <div key={group.key} className="inbox-group">
              <p className="inbox-group-head">
                <span>{t(`inbox.group.${group.key}`)}</span>
                <span>{group.threads.length}</span>
              </p>
              <ul className="inbox-thread-list">
                {group.threads.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`inbox-row${item.id === selectedId ? ' selected' : ''}${!item.read ? ' unread' : ''}`}
                      onClick={() => setSelectedId(item.id)}
                    >
                      <span className="inbox-row-main">
                        <span className="inbox-row-who">
                          <span className={item.read ? 'inbox-dot-space' : 'inbox-unread-dot'} aria-hidden="true" />
                          <span className="inbox-thread-buyer">{item.interlocutor_login ?? '—'}</span>
                          <span className="inbox-source">{item.source}</span>
                          {item.order_external_id && (
                            <span
                              className="inbox-chip inbox-chip-blue"
                              title={t('inbox.order', { order: item.order_external_id })}
                            >
                              {t('inbox.hasOrder')}
                            </span>
                          )}
                          {searching && item.aside && (
                            <span className="inbox-aside-tag">{t('inbox.filter.aside')}</span>
                          )}
                        </span>
                        <span className="inbox-thread-excerpt">{item.last_message_text ?? ''}</span>
                      </span>
                      <span className="inbox-row-when">
                        {waitingChip(item) ??
                          (item.last_message_at && (
                            <span className="inbox-when">{formatRelative(item.last_message_at)}</span>
                          ))}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>

        {thread && (
          <ThreadDetail
            thread={thread}
            waiting={listed ? waitingChip(listed) : null}
            onThreadChange={setThread}
            onAsideToggle={() => toggleAside(thread)}
            onClose={() => setSelectedId(null)}
            formatDateTime={formatDateTime}
            t={t}
          />
        )}
      </div>
    </div>
  );
}

interface ThreadDetailProps {
  thread: MessageThreadDetail;
  /** How long the buyer has been waiting, as a chip, when the list knows. */
  waiting: React.ReactNode;
  onThreadChange: (thread: MessageThreadDetail) => void;
  onAsideToggle: () => void;
  onClose: () => void;
  formatDateTime: ReturnType<typeof useTranslation>['formatDateTime'];
  t: ReturnType<typeof useTranslation>['t'];
}

function ThreadDetail({
  thread,
  waiting,
  onThreadChange,
  onAsideToggle,
  onClose,
  formatDateTime,
  t,
}: ThreadDetailProps) {
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
    <section className="inbox-detail card tone-blue" aria-label={t('inbox.conversation')}>
      <div className="card-head">
        <span className="inbox-detail-title">
          <strong>{thread.interlocutor_login ?? '—'}</strong>
          <span className="inbox-source">{thread.source}</span>
          {waiting}
        </span>
        <span className="inbox-detail-actions">
          {thread.order_external_id && (
            <Link to={`/orders?search=${encodeURIComponent(thread.order_external_id)}`} className="inbox-order-link">
              {t('inbox.openOrder')}
            </Link>
          )}
          <button type="button" onClick={onAsideToggle}>
            {thread.aside ? t('inbox.bringBack') : t('inbox.putAside')}
          </button>
          <button type="button" className="inbox-close" onClick={onClose} aria-label={t('inbox.close')} title={t('inbox.close')}>
            ✕
          </button>
        </span>
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
    </section>
  );
}
