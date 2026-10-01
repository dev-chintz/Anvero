import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ApiError,
  catalogApi,
  type CatalogCategories,
  type CatalogCategoryNode,
  type CatalogFlag,
  type CatalogItem,
  type ChannelSales,
  type CatalogProgress,
  type CatalogSort,
  type CatalogStatusFilter,
  type CatalogSummary,
  type CatalogSyncNote,
  type CategoryStep,
} from "../api/client";
import { ItemThumb } from "../components/ItemThumb";
import { Pagination } from "../components/Pagination";
import { usePermission } from "../hooks/usePermission";
import { useTranslation } from "../i18n";
import "../styles/CatalogPage.css";

const STATUSES: CatalogStatusFilter[] = ["current", "active", "inactive", "gone"];
const FLAGS: CatalogFlag[] = ["no_image", "no_sku", "not_on_erli", "category_differs"];
// the flags that mean something only once Erli is connected
const ERLI_FLAGS = new Set<CatalogFlag>(["not_on_erli", "category_differs"]);
const SORTS: CatalogSort[] = ["name", "price", "stock", "sold", "net"];
// the columns that start from the largest, since it is the best sellers that are looked for
const DESCENDING_FIRST = new Set<CatalogSort>(["sold", "net"]);
// the periods the sales can be shown for: the last so many days, 0 being everything held
const PERIODS = [30, 90, 0] as const;
const DEFAULT_PERIOD = 30;
const DEFAULT_LIMIT = 50;
// how long after the last key the search starts
const SEARCH_DELAY_MS = 300;
// how often a running read is asked how far it has got, and how many of those asks the list is read
// again after, so offers appear as they are stored
const PROGRESS_POLL_MS = 2000;
const LIST_REFRESH_EVERY = 5;

/** "2:05", from a number of seconds. */
function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** What a finished read did, in one line, or null when there is nothing to say (it failed: the page
 * says so on its own, or it was written before the figures were kept). */
function resultText(sync: CatalogSyncNote | null | undefined, t: ReturnType<typeof useTranslation>["t"]): string | null {
  if (!sync || sync.error || sync.items === null) return null;
  const parts = [
    t("catalog.synced", {
      items: sync.items,
      added: sync.added ?? 0,
      gone: sync.gone ?? 0,
      images: sync.images_downloaded ?? 0,
    }),
  ];
  if (sync.erli_matched !== null && sync.erli_unmatched !== null) {
    parts.push(t("catalog.syncedErli", { matched: sync.erli_matched, unmatched: sync.erli_unmatched }));
  }
  if (sync.images_pending) parts.push(t("catalog.syncedPending", { pending: sync.images_pending }));
  return parts.join(" ");
}

interface ProgressCardProps {
  progress: CatalogProgress;
  now: number;
}

/** A read in progress: the step, how far it has got as a bar and as numbers, and for how long. */
function ProgressCard({ progress, now }: ProgressCardProps) {
  const { t } = useTranslation();
  const known = progress.total !== null && progress.total > 0;
  const percent = known ? Math.min(100, Math.round((progress.done / progress.total!) * 100)) : 0;
  const started = progress.started_at ? new Date(progress.started_at).getTime() : null;
  const label = t(`catalog.progress.phase.${progress.phase ?? "starting"}` as "catalog.progress.phase.starting");
  return (
    <section className="card tone-teal catalog-progress" aria-label={t("catalog.progress.title")}>
      <div className="card-head">
        <h2>{t("catalog.progress.title")}</h2>
        {started !== null && <span className="catalog-progress-time">{t("catalog.progress.elapsed", { time: clock((now - started) / 1000) })}</span>}
      </div>
      <div className="catalog-progress-line">
        <span className="catalog-progress-phase">{label}</span>
        <span className="catalog-progress-count">
          {progress.phase === null
            ? ""
            : known
              ? t("catalog.progress.count", { done: progress.done, total: progress.total! })
              : t("catalog.progress.countOnly", { done: progress.done })}
        </span>
      </div>
      <div
        className={`catalog-progress-bar${known ? "" : " is-indeterminate"}`}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={known ? progress.total! : undefined}
        aria-valuenow={known ? progress.done : undefined}
      >
        <i style={known ? { width: `${percent}%` } : undefined} />
      </div>
      <p className="catalog-progress-hint">{t("catalog.progress.hint")}</p>
    </section>
  );
}

function pathText(path: CategoryStep[]): string {
  return path.map((step) => step.name).join(" › ");
}

/** The ids of the categories above `id` in the tree and `id` itself, or none if it is not in it. */
function ancestors(nodes: CatalogCategoryNode[], id: string): string[] | null {
  for (const node of nodes) {
    if (node.id === id) return [node.id];
    const below = ancestors(node.children, id);
    if (below) return [node.id, ...below];
  }
  return null;
}

const number = (value: string | number) => Number(value) || 0;

/** The offer's sales on both marketplaces added: pieces, sales, fees and what is left. */
function together(item: CatalogItem) {
  const channels: ChannelSales[] = [item.sales_allegro, ...(item.sales_erli ? [item.sales_erli] : [])];
  const sum = (pick: (c: ChannelSales) => string | number) => channels.reduce((total, c) => total + number(pick(c)), 0);
  return { quantity: sum((c) => c.quantity), sales: sum((c) => c.sales), fees: sum((c) => c.fees), net: sum((c) => c.net) };
}

function stockTone(stock: number | null): string {
  if (stock === null) return "";
  if (stock <= 0) return "catalog-chip-red";
  if (stock <= 3) return "catalog-chip-amber";
  return "catalog-chip-green";
}

interface CategoryTreeProps {
  nodes: CatalogCategoryNode[];
  selected: string | null;
  expanded: Set<string>;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  depth?: number;
}

function CategoryTree({ nodes, selected, expanded, onSelect, onToggle, depth = 0 }: CategoryTreeProps) {
  const { t } = useTranslation();
  return (
    <ul className="catalog-tree" role={depth === 0 ? "tree" : "group"}>
      {nodes.map((node) => {
        const open = expanded.has(node.id);
        const hasChildren = node.children.length > 0;
        return (
          <li key={node.id} role="treeitem" aria-expanded={hasChildren ? open : undefined} aria-selected={selected === node.id}>
            <div className={`catalog-tree-row${selected === node.id ? " is-on" : ""}`}>
              {hasChildren ? (
                <button
                  type="button"
                  className="catalog-tree-caret"
                  onClick={() => onToggle(node.id)}
                  aria-label={t(open ? "catalog.categories.collapse" : "catalog.categories.expand", { name: node.name })}
                >
                  {open ? "▾" : "▸"}
                </button>
              ) : (
                <span className="catalog-tree-caret" aria-hidden="true" />
              )}
              <button type="button" className="catalog-tree-name" onClick={() => onSelect(node.id)}>
                <span>{node.name}</span>
                <span className="catalog-tree-count">{node.count}</span>
              </button>
            </div>
            {hasChildren && open && (
              <CategoryTree
                nodes={node.children}
                selected={selected}
                expanded={expanded}
                onSelect={onSelect}
                onToggle={onToggle}
                depth={depth + 1}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The assortment: every offer in the seller's Allegro account, with its pictures, and for each how
 * the same product stands on Erli. Read only. A compact list with the category tree beside it
 * (DECISIONS.md, 2026-10-01, "The assortment"); a row opens to show all its pictures, with their
 * addresses on Allegro and the copies kept on this server, and the category in both marketplaces.
 */
export function CatalogPage() {
  const { t, formatDateTime, formatMoney, formatNumber, formatDate } = useTranslation();
  const canSync = usePermission("orders", "manage");
  const [searchParams, setSearchParams] = useSearchParams();

  // what is shown is kept in the address, so going back to the list restores it
  const statusParam = searchParams.get("status");
  const status = STATUSES.find((s) => s === statusParam) ?? "current";
  const flagParam = searchParams.get("flag");
  const flag = FLAGS.find((f) => f === flagParam);
  const category = searchParams.get("category");
  const sortParam = searchParams.get("sort");
  const sort = SORTS.find((s) => s === sortParam) ?? "name";
  const descending = searchParams.get("desc") === "true";
  const periodParam = searchParams.get("sales");
  const salesDays = periodParam === "all" ? 0 : PERIODS.find((p) => String(p) === periodParam && p !== 0) ?? DEFAULT_PERIOD;
  const limit = Number(searchParams.get("limit")) || DEFAULT_LIMIT;
  const skip = Number(searchParams.get("skip")) || 0;

  // the search is typed here and only asked for a moment after the last key
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => {
    if (typed === query) return;
    const timer = setTimeout(() => {
      setQuery(typed);
      // a new search starts from the first page
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.delete("skip");
          return next;
        },
        { replace: true },
      );
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typed]);

  const choose = (updates: Record<string, string | undefined>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    // any change of what is shown, but a page's own, starts from the first page
    if (!("skip" in updates)) next.delete("skip");
    setSearchParams(next);
  };

  const [list, setList] = useState<{ items: CatalogItem[]; total: number; sales_from: string | null } | null>(null);
  const [tree, setTree] = useState<CatalogCategories | null>(null);
  const [summary, setSummary] = useState<CatalogSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  // the read starting (the request is out), and the read going on in the backend, whoever started it
  const [starting, setStarting] = useState(false);
  const [progress, setProgress] = useState<CatalogProgress | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [opened, setOpened] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // raised after a read from Allegro, so the list asks again whatever its filters are
  const [reloadKey, setReloadKey] = useState(0);

  const loadSides = useCallback(() => {
    catalogApi
      .summary()
      .then(setSummary)
      .catch(() => undefined);
    catalogApi
      .categories()
      .then(setTree)
      .catch(() => undefined);
  }, []);

  useEffect(loadSides, [loadSides]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    catalogApi
      .list({ q: query.trim() || undefined, category: category ?? undefined, status, flag, sort, descending, salesDays, limit, offset: skip })
      .then((next) => {
        if (!cancelled) setList(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t("catalog.loadFailed"));
      });
    return () => {
      cancelled = true;
    };
  }, [t, query, category, status, flag, sort, descending, salesDays, limit, skip, reloadKey]);

  // the path to the chosen category is open, so it is seen where it sits
  useEffect(() => {
    if (!tree || !category) return;
    const path = ancestors(tree.tree, category);
    if (path) setExpanded((current) => new Set([...current, ...path.slice(0, -1)]));
  }, [tree, category]);

  const toggle = (set: Set<string>, id: string) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  };

  // a read already going on (one the schedule started, or one from before this page was opened) is seen at once
  useEffect(() => {
    let cancelled = false;
    catalogApi
      .progress()
      .then((next) => {
        if (!cancelled) setProgress(next);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // while it goes on it is asked how far it has got, and the offers stored so far are shown
  const running = progress?.running === true;
  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    let asked = 0;
    const timer = setInterval(() => {
      asked += 1;
      catalogApi
        .progress()
        .then((next) => {
          if (cancelled) return;
          setNow(Date.now());
          setProgress(next);
          if (next.running && asked % LIST_REFRESH_EVERY === 0) {
            loadSides();
            setReloadKey((key) => key + 1);
          }
        })
        .catch(() => undefined);
    }, PROGRESS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [running, loadSides]);

  // when it ends: the list, the counts and the tree are read again, and what it did is said
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) {
      catalogApi
        .summary()
        .then((next) => {
          setSummary(next);
          const text = resultText(next.last_sync, t);
          if (text) setNote({ text, error: false });
        })
        .catch(() => undefined);
      catalogApi
        .categories()
        .then(setTree)
        .catch(() => undefined);
      setReloadKey((key) => key + 1);
    }
    wasRunning.current = running;
  }, [running, t]);

  const sync = async () => {
    setStarting(true);
    setNote(null);
    try {
      await catalogApi.sync();
      // running from now: the backend answered after it had begun
      setNow(Date.now());
      setProgress({ running: true, phase: null, done: 0, total: null, started_at: new Date().toISOString() });
    } catch (err) {
      setNote({ text: err instanceof ApiError ? err.message : t("catalog.syncFailed"), error: true });
    } finally {
      setStarting(false);
    }
  };

  const erliConnected = summary?.erli_connected ?? false;
  const statusCount = (s: CatalogStatusFilter): number | null =>
    summary ? { current: summary.total, active: summary.active, inactive: summary.inactive, gone: summary.gone }[s] : null;
  const flagCount = (f: CatalogFlag): number | null => (summary ? summary[f] : null);

  const sortBy = (column: CatalogSort) =>
    choose(
      column === sort
        ? { desc: descending ? undefined : "true" }
        : { sort: column === "name" ? undefined : column, desc: DESCENDING_FIRST.has(column) ? "true" : undefined },
    );
  const sortHead = (column: CatalogSort, label: string) => (
    <th scope="col" aria-sort={sort === column ? (descending ? "descending" : "ascending") : "none"}>
      <button type="button" className="catalog-sort" onClick={() => sortBy(column)} title={t("catalog.sortBy", { column: label })}>
        {label}
        {sort === column && <span aria-hidden="true">{descending ? " ▼" : " ▲"}</span>}
      </button>
    </th>
  );

  const stockText = (stock: number | null) => (stock === null ? "—" : t("catalog.stock.pieces", { count: stock }));
  const offerStatusLabel = (item: CatalogItem) =>
    item.gone ? t("catalog.offerStatus.gone") : t(`catalog.offerStatus.${item.status}` as "catalog.offerStatus.ACTIVE");
  const colCount = erliConnected ? 7 : 6;
  const periodName = (days: number) => (days === 0 ? t("catalog.period.all") : t("catalog.period.days", { days }));
  const pieces = (count: number) => t("catalog.stock.pieces", { count });
  const percent = (part: number, whole: number) =>
    whole > 0 ? `${formatNumber(Math.round((part / whole) * 100))}%` : "—";
  const last = summary?.last_sync;

  return (
    <div className="catalog-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t("catalog.title")}</h1>
          <p className="subtitle">{t("catalog.subtitle")}</p>
        </div>
        {canSync && (
          <button type="button" className="catalog-sync" onClick={sync} disabled={starting || running}>
            {starting || running ? t("catalog.syncing") : t("catalog.sync")}
          </button>
        )}
      </header>

      <div className="catalog-body">
        {progress?.running && <ProgressCard progress={progress} now={now} />}
        {note && (
          <p role={note.error ? "alert" : "status"} className={note.error ? "error-message" : "catalog-note"}>
            {note.text}
          </p>
        )}
        {summary && !last && summary.total === 0 && <p className="catalog-note">{t("catalog.neverRead")}</p>}
        {last?.error && (
          <p role="alert" className="error-message">
            {t("catalog.lastSyncFailed", { error: last.error })}
          </p>
        )}
        {last?.erli_error && (
          <p role="alert" className="error-message">
            {t("catalog.erliFailed", { error: last.erli_error })}
          </p>
        )}

        <div className="catalog-layout">
          <aside className="card tone-blue catalog-categories" aria-label={t("catalog.categories")}>
            <h2>{t("catalog.categories")}</h2>
            <button
              type="button"
              className={`catalog-tree-all${category ? "" : " is-on"}`}
              onClick={() => choose({ category: undefined })}
            >
              <span>{t("catalog.categories.all")}</span>
              {summary && <span className="catalog-tree-count">{summary.total}</span>}
            </button>
            {tree && (
              <CategoryTree
                nodes={tree.tree}
                selected={category}
                expanded={expanded}
                onSelect={(id) => choose({ category: id })}
                onToggle={(id) => setExpanded((current) => toggle(current, id))}
              />
            )}
            {tree && tree.uncategorized > 0 && (
              <p className="catalog-uncategorized">
                {t("catalog.categories.none")}
                <span className="catalog-tree-count">{tree.uncategorized}</span>
              </p>
            )}
          </aside>

          <section className="catalog-main">
            <div className="card catalog-toolbar">
              <div className="catalog-search">
                <input
                  type="search"
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                  placeholder={t("catalog.search")}
                  aria-label={t("catalog.search")}
                  maxLength={100}
                />
                {typed && (
                  <button
                    type="button"
                    className="catalog-search-clear"
                    onClick={() => {
                      setTyped("");
                      setQuery("");
                    }}
                    aria-label={t("catalog.searchClear")}
                    title={t("catalog.searchClear")}
                  >
                    ✕
                  </button>
                )}
              </div>
              <div className="catalog-filters" role="group" aria-label={t("catalog.statusFilter")}>
                {STATUSES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={status === s ? "is-on" : undefined}
                    aria-pressed={status === s}
                    onClick={() => choose({ status: s === "current" ? undefined : s })}
                  >
                    {t(`catalog.status.${s}`)}{" "}
                    {statusCount(s) !== null && <span className="catalog-filter-count">{statusCount(s)}</span>}
                  </button>
                ))}
              </div>
              <div className="catalog-filters" role="group" aria-label={t("catalog.period.label")}>
                <span className="label-caps catalog-filters-label">{t("catalog.period.label")}</span>
                {PERIODS.map((days) => (
                  <button
                    key={days}
                    type="button"
                    className={salesDays === days ? "is-on" : undefined}
                    aria-pressed={salesDays === days}
                    onClick={() => choose({ sales: days === DEFAULT_PERIOD ? undefined : days === 0 ? "all" : String(days) })}
                  >
                    {periodName(days)}
                  </button>
                ))}
              </div>
              <div className="catalog-filters" role="group" aria-label={t("catalog.flagFilter")}>
                {FLAGS.filter((f) => erliConnected || !ERLI_FLAGS.has(f)).map((f) => (
                  <button
                    key={f}
                    type="button"
                    className={flag === f ? "is-on" : undefined}
                    aria-pressed={flag === f}
                    onClick={() => choose({ flag: flag === f ? undefined : f })}
                  >
                    {t(`catalog.flag.${f}`)}{" "}
                    {flagCount(f) !== null && <span className="catalog-filter-count">{flagCount(f)}</span>}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <p role="alert" className="error-message">
                {error}
              </p>
            )}
            {!list && !error && <p role="status">{t("catalog.loading")}</p>}
            {list && list.items.length === 0 && (
              <p role="status">{summary && summary.total === 0 && !category && !query && !flag ? t("catalog.emptyNone") : t("catalog.empty")}</p>
            )}

            {list && list.items.length > 0 && (
              <div className="table-wrapper">
                <table className="catalog-table">
                  <thead>
                    <tr>
                      {sortHead("name", t("catalog.col.offer"))}
                      {sortHead("price", t("catalog.col.price"))}
                      {sortHead("stock", t("catalog.col.stock"))}
                      {sortHead("sold", t("catalog.col.sold"))}
                      {sortHead("net", t("catalog.col.net"))}
                      {erliConnected && <th scope="col">{t("catalog.col.erli")}</th>}
                      <th scope="col" className="sr-only">
                        {t("catalog.detail.pictures")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.items.map((item) => {
                      const open = opened.has(item.id);
                      return (
                        <Fragment key={item.id}>
                          <tr className={open ? "is-open" : undefined}>
                            <td>
                              <div className="catalog-offer">
                                {item.thumbnail_url ? (
                                  <ItemThumb src={item.thumbnail_url} className="catalog-thumb" />
                                ) : (
                                  <div className="catalog-thumb" role="img" aria-label={t("catalog.noPicture")} />
                                )}
                                <div className="catalog-text">
                                  <div className="catalog-name">
                                    <span>{item.name}</span>
                                    {(item.gone || item.status !== "ACTIVE") && (
                                      <span className="catalog-chip catalog-chip-gray">{offerStatusLabel(item)}</span>
                                    )}
                                  </div>
                                  <div className="cell-sub">
                                    {item.sku ?? t("catalog.noSku")}
                                    {item.category_path.length > 0 && ` · ${item.category_path[item.category_path.length - 1].name}`}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="catalog-price">{item.price !== null && item.currency ? formatMoney(item.price, item.currency) : "—"}</td>
                            <td>
                              <span className={`catalog-chip ${stockTone(item.stock)}`.trim()}>{stockText(item.stock)}</span>
                            </td>
                            <SoldCell item={item} erliConnected={erliConnected} pieces={pieces} />
                            <NetCell item={item} formatMoney={formatMoney} percent={percent} perPiece={(amount) => t("catalog.net.perPiece", { amount })} />
                            {erliConnected && (
                              <td>
                                {item.erli ? (
                                  <span className="catalog-erli">
                                    <span className="source-mark source-erli" title="Erli">
                                      E
                                    </span>
                                    <span>
                                      {item.erli.status ? t(`catalog.erli.status.${item.erli.status}` as "catalog.erli.status.ACTIVE") : "—"}
                                    </span>
                                    {item.erli.category_match === "DIFFERENT" && (
                                      <span className="catalog-chip catalog-chip-amber">{t("catalog.erli.differs")}</span>
                                    )}
                                  </span>
                                ) : (
                                  <span className="order-muted">{t("catalog.erli.absent")}</span>
                                )}
                              </td>
                            )}
                            <td className="catalog-toggle">
                              <button
                                type="button"
                                aria-expanded={open}
                                aria-label={t(open ? "catalog.collapse" : "catalog.expand", { name: item.name })}
                                onClick={() => setOpened((current) => toggle(current, item.id))}
                              >
                                {open ? "▾" : "▸"}
                              </button>
                            </td>
                          </tr>
                          {open && (
                            <tr className="catalog-detail-row">
                              <td colSpan={colCount}>
                                <ItemDetail item={item} erliConnected={erliConnected} formatMoney={formatMoney} stockText={stockText} formatNumber={formatNumber} period={salesDays === 0 ? t("catalog.period.allHeld") : periodName(salesDays)} />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {list && list.total > 0 && (
              <Pagination
                skip={skip}
                limit={limit}
                count={list.total}
                onPageChange={(next) => choose({ skip: next ? String(next) : undefined })}
                onLimitChange={(next) => choose({ limit: next === DEFAULT_LIMIT ? undefined : String(next) })}
              />
            )}

            <p className="catalog-footnote catalog-footnote-sales">
              <span>
                {t("catalog.sales.note", {
                  period:
                    salesDays === 0
                      ? t("catalog.period.allHeld")
                      : list?.sales_from
                        ? t("catalog.period.since", { date: formatDate(list.sales_from) })
                        : periodName(salesDays),
                })}
              </span>
            </p>

            <p className="catalog-footnote">
              {summary && summary.images_total > 0 && (
                <span>{t("catalog.picturesKept", { local: summary.images_local, total: summary.images_total })}</span>
              )}
              {last && <span>{t("catalog.lastSync", { when: formatDateTime(last.at) })}</span>}
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

interface SoldCellProps {
  item: CatalogItem;
  erliConnected: boolean;
  pieces: (count: number) => string;
}

/** Pieces sold in the period, on each marketplace: the letter of the marketplace and its figure. */
function SoldCell({ item, erliConnected, pieces }: SoldCellProps) {
  const { t } = useTranslation();
  const all = together(item);
  const channels = [
    { key: "allegro", mark: "A", className: "source-allegro", sales: item.sales_allegro },
    ...(erliConnected ? [{ key: "erli", mark: "E", className: "source-erli", sales: item.sales_erli }] : []),
  ];
  return (
    <td className="catalog-sold">
      {all.quantity === 0 ? (
        <span className="order-muted">0</span>
      ) : (
        <span className="catalog-sold-line">
          {channels.map(({ key, mark, className, sales }) => (
            <span key={key} className="catalog-sold-channel" title={key === "allegro" ? "Allegro" : "Erli"}>
              <span className={`source-mark ${className}`}>{mark}</span>
              <b>{sales ? sales.quantity : "—"}</b>
            </span>
          ))}
        </span>
      )}
      {all.quantity > 0 && channels.length > 1 && <span className="cell-sub">{t("catalog.sold.total", { total: pieces(all.quantity) })}</span>}
    </td>
  );
}

interface NetCellProps {
  item: CatalogItem;
  formatMoney: (amount: string | number, currency: string) => string;
  percent: (part: number, whole: number) => string;
  perPiece: (amount: string) => string;
}

/** What is left of what sold after the marketplaces' fees: on a piece, and in all with its share of the sales. */
function NetCell({ item, formatMoney, percent, perPiece }: NetCellProps) {
  const all = together(item);
  const currency = item.currency ?? "PLN";
  if (all.quantity === 0) {
    return (
      <td className="catalog-net">
        <span className="order-muted">—</span>
      </td>
    );
  }
  const loss = all.net < 0;
  return (
    <td className="catalog-net">
      <span className={`catalog-net-main${loss ? " is-loss" : ""}`}>{perPiece(formatMoney((all.net / all.quantity).toFixed(2), currency))}</span>
      <span className="cell-sub">
        {formatMoney(all.net.toFixed(2), currency)} · {percent(all.net, all.sales)}
      </span>
    </td>
  );
}

interface ItemDetailProps {
  item: CatalogItem;
  erliConnected: boolean;
  formatMoney: (amount: string | number, currency: string) => string;
  stockText: (stock: number | null) => string;
  formatNumber: (value: number, options?: Intl.NumberFormatOptions) => string;
  /** The period the sales are of, in words. */
  period: string;
}

/** What an offer sold on each marketplace in the period, and what was left of it. */
function SalesTable({ item, erliConnected, formatMoney, formatNumber, period }: ItemDetailProps) {
  const { t } = useTranslation();
  const currency = item.currency ?? "PLN";
  const rows = [
    { key: "allegro", name: "Allegro", sales: item.sales_allegro },
    ...(erliConnected ? [{ key: "erli", name: "Erli", sales: item.sales_erli }] : []),
  ];
  const money = (amount: number) => formatMoney(amount.toFixed(2), currency);
  const share = (net: number, sales: number) => (sales > 0 ? `${formatNumber(Math.round((net / sales) * 100))}%` : "—");
  return (
    <section className="catalog-detail-block catalog-detail-sales">
      <h3 className="label-caps">{t("catalog.detail.sales", { period })}</h3>
      <table className="catalog-sales-table">
        <thead>
          <tr>
            <th scope="col" />
            <th scope="col">{t("catalog.sales.pieces")}</th>
            <th scope="col">{t("catalog.sales.orders")}</th>
            <th scope="col">{t("catalog.sales.revenue")}</th>
            <th scope="col">{t("catalog.sales.fees")}</th>
            <th scope="col">{t("catalog.sales.net")}</th>
            <th scope="col">{t("catalog.sales.perPiece")}</th>
            <th scope="col">{t("catalog.sales.margin")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, name, sales }) => {
            const net = sales ? number(sales.net) : 0;
            const revenue = sales ? number(sales.sales) : 0;
            return (
              <tr key={key}>
                <th scope="row">
                  <span className={`source-mark source-${key}`}>{name.charAt(0)}</span> {name}
                </th>
                {sales ? (
                  <>
                    <td>{sales.quantity}</td>
                    <td>{sales.orders}</td>
                    <td>{money(revenue)}</td>
                    <td>{money(number(sales.fees))}</td>
                    <td className={net < 0 ? "catalog-net-main is-loss" : "catalog-net-main"}>{money(net)}</td>
                    <td>{sales.quantity > 0 ? money(net / sales.quantity) : "—"}</td>
                    <td>{share(net, revenue)}</td>
                  </>
                ) : (
                  <td colSpan={7} className="order-muted">
                    {t("catalog.detail.notOnErli")}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

/** What a row opens to: every picture, and the offer beside its Erli product. */
function ItemDetail(props: ItemDetailProps) {
  const { item, erliConnected, formatMoney, stockText } = props;
  const { t } = useTranslation();
  const { erli } = item;
  return (
    <div className="catalog-detail">
      <SalesTable {...props} />
      <section className="catalog-detail-block catalog-detail-pictures">
        <h3 className="label-caps">{t("catalog.detail.pictures")}</h3>
        {item.images.length === 0 ? (
          <p className="order-muted">{t("catalog.detail.noPictures")}</p>
        ) : (
          <ul className="catalog-pictures">
            {item.images.map((image) => (
              <li key={image.position}>
                <a
                  href={image.local_url ?? image.url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={t("catalog.detail.openPicture", { number: image.position + 1 })}
                >
                  <img src={image.local_url ?? image.url} alt="" loading="lazy" className="catalog-picture" />
                </a>
                <span className="cell-sub">
                  {image.local_url ? t("catalog.detail.copyKept") : t("catalog.detail.copyPending")}
                  {" · "}
                  <a href={image.url} target="_blank" rel="noreferrer">
                    {t("catalog.detail.allegroPicture")}
                  </a>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="catalog-detail-block">
        <h3 className="label-caps">{t("catalog.detail.allegro")}</h3>
        <dl>
          <dt>{t("catalog.detail.offerNumber")}</dt>
          <dd>
            <a href={item.allegro_url} target="_blank" rel="noreferrer">
              {item.offer_id} ↗
            </a>
          </dd>
          <dt>{t("catalog.detail.category")}</dt>
          <dd>{item.category_path.length > 0 ? pathText(item.category_path) : t("catalog.detail.noCategory")}</dd>
        </dl>
      </section>

      <section className="catalog-detail-block">
        <h3 className="label-caps">{t("catalog.detail.erli")}</h3>
        {!erliConnected ? (
          <p className="order-muted">{t("catalog.detail.erliNotConnected")}</p>
        ) : !erli ? (
          <p className="order-muted">{t("catalog.detail.notOnErli")}</p>
        ) : (
          <dl>
            <dt>{t("catalog.detail.erliId")}</dt>
            <dd>
              {erli.external_id}
              <span className="cell-sub">{t(`catalog.matchedBy.${erli.matched_by}` as "catalog.matchedBy.SKU")}</span>
            </dd>
            <dt>{t("catalog.col.price")}</dt>
            <dd>{erli.price !== null && erli.currency ? formatMoney(erli.price, erli.currency) : "—"}</dd>
            <dt>{t("catalog.col.stock")}</dt>
            <dd>{stockText(erli.stock)}</dd>
            <dt>{t("catalog.detail.category")}</dt>
            <dd>
              {erli.category_path.length > 0 ? pathText(erli.category_path) : t("catalog.detail.noCategory")}
              <span
                className={`catalog-chip ${
                  erli.category_match === "SAME" ? "catalog-chip-green" : erli.category_match === "DIFFERENT" ? "catalog-chip-amber" : "catalog-chip-gray"
                }`}
              >
                {t(`catalog.categoryMatch.${erli.category_match}`)}
              </span>
            </dd>
          </dl>
        )}
      </section>
    </div>
  );
}
