import { useState } from "react";
import { ApiError, messagesApi, type MessageThreadDetail } from "../api/client";
import { useTranslation } from "../i18n";
import "../styles/InboxPage.css";

interface ThreadConversationProps {
  thread: MessageThreadDetail;
  onThreadChange: (thread: MessageThreadDetail) => void;
}

/**
 * The messages of one thread, oldest first, and the form to answer it. Shared by the inbox
 * and the order page, so a reply is written and reported the same way in both.
 */
export function ThreadConversation({ thread, onThreadChange }: ThreadConversationProps) {
  const { t, formatDateTime } = useTranslation();
  const [draft, setDraft] = useState("");
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
      setDraft("");
      setStatus(
        result.marketplace_write.outcome === "DRY_RUN"
          ? t("inbox.reply.dryRun")
          : result.marketplace_write.outcome === "SENT"
            ? t("inbox.reply.sent")
            : t("inbox.reply.failed", { detail: result.marketplace_write.detail ?? "" }),
      );
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : t("error.network"));
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <div className="inbox-message-list">
        {thread.messages.map((message) => (
          <div key={message.id} className={`inbox-message inbox-message-${message.direction}`}>
            <div className="inbox-message-meta">
              <span>
                {message.direction === "OUT" && message.created_in_anvero ? t("inbox.you") : message.author_login ?? ""}
              </span>
              <span>{formatDateTime(message.sent_at)}</span>
            </div>
            <p>{message.text}</p>
          </div>
        ))}
      </div>

      {thread.source === "ALLEGRO" ? (
        <form className="inbox-reply-form" onSubmit={send}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={t("inbox.reply.placeholder")}
            rows={3}
            disabled={sending}
          />
          <button type="submit" disabled={sending || !draft.trim()}>
            {sending ? t("inbox.reply.sending") : t("inbox.reply.send")}
          </button>
          {status && (
            <p role="status" className="inbox-reply-status">
              {status}
            </p>
          )}
        </form>
      ) : (
        <p role="status" className="inbox-reply-status">
          {t("inbox.erliUnsupported")}
        </p>
      )}
    </>
  );
}
