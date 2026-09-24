import { SESSION_EXPIRED_EVENT, clearToken, getToken } from "../auth/session";
import type {
  Order,
  OrderBilling,
  OrderListResponse,
  OrderStats,
  OrderStatusChange,
  OrderWithDetails,
  ProductionList,
} from "../types/order";
import type { OrderQueue, OrderSort, OrderSource, OrderStatus } from "../types/order";
import type { Token, User } from "../types/user";
import { translate } from "../i18n";

// Vite's dev server proxies "/api" to the FastAPI backend (see vite.config.ts),
// so this relative base works in both dev and behind a same-origin reverse
// proxy in production.
const API_BASE_URL = "/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions extends Omit<RequestInit, "headers"> {
  // a plain object only: a Headers instance spreads to nothing
  headers?: Record<string, string>;
  /**
   * Send the login token, and treat a 401 as an expired session. Off only for
   * the login call itself, where a 401 means a wrong password, not a session
   * that has run out.
   */
  authenticated?: boolean;
  /** Read the body as a Blob (a PDF) rather than JSON. */
  blob?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { authenticated = true, blob = false, headers, ...init } = options;
  const token = authenticated ? getToken() : null;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      // merged, not replaced: spreading `init` over a headers object used to
      // drop Content-Type whenever a caller passed headers of its own
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });
  } catch {
    throw new ApiError(0, translate("error.network"));
  }

  if (!response.ok) {
    if (response.status === 401 && authenticated) {
      clearToken();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
      throw new ApiError(401, translate("error.sessionEnded"));
    }
    if (response.status === 401) {
      throw new ApiError(401, translate("error.badCredentials"));
    }
    const message = await extractErrorMessage(response);
    throw new ApiError(response.status, message);
  }

  if (blob) return (await response.blob()) as T;
  return (await response.json()) as T;
}

async function extractErrorMessage(response: Response): Promise<string> {
  switch (response.status) {
    case 404:
      return translate("error.notFound");
    case 429:
      return translate("error.tooManyRequests");
    case 500:
      return translate("error.server");
    default:
      break;
  }

  try {
    const body = (await response.json()) as { detail?: string; error?: string };
    return body.detail ?? body.error ?? translate("error.requestFailed", { status: response.status });
  } catch {
    return translate("error.requestFailed", { status: response.status });
  }
}

export interface ListOrdersParams {
  skip?: number;
  limit?: number;
  source?: OrderSource;
  status?: OrderStatus;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  cancellationWarning?: boolean;
  queue?: OrderQueue;
  sort?: OrderSort;
  /** List the deleted orders instead of the ones in use. */
  deleted?: boolean;
}

function buildQuery(params: ListOrdersParams): string {
  const query = new URLSearchParams();
  if (params.skip !== undefined) query.set("skip", String(params.skip));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.source) query.set("source", params.source);
  if (params.status) query.set("status", params.status);
  if (params.search) query.set("search", params.search);
  if (params.dateFrom) query.set("date_from", params.dateFrom);
  if (params.dateTo) query.set("date_to", params.dateTo);
  if (params.cancellationWarning) query.set("cancellation_warning", "true");
  if (params.queue) query.set("queue", params.queue);
  if (params.sort) query.set("sort", params.sort);
  if (params.deleted) query.set("deleted", "true");
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export const authApi = {
  login(email: string, password: string): Promise<Token> {
    return request<Token>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      authenticated: false,
    });
  },

  me(): Promise<User> {
    return request<User>("/users/me");
  },
};

export type AllegroEnvironment = "sandbox" | "production";

export interface AllegroStatus {
  /** Ready to import: the application's credentials and a token are both there. */
  configured: boolean;
  /** A seller account has been connected. */
  connected: boolean;
  /** Client id, client secret and User-Agent are all set. */
  application_complete: boolean;
  client_id: string | null;
  user_agent: string | null;
  environment: AllegroEnvironment;
  /** Entered in Settings, or read from backend/.env. */
  source: "settings" | "environment";
  /** The connected seller's login, when known. */
  account_login: string | null;
  /**
   * How the last import ended, whether the button or the schedule ran it.
   * Optional because a backend older than the field omits them.
   */
  last_import_at?: string | null;
  last_import_created?: number | null;
  last_import_updated?: number | null;
  /** Set when the last import failed. */
  last_import_error?: string | null;
  /** Minutes between imports the backend runs by itself; 0 means none. */
  auto_import_interval_minutes?: number;
}

export interface AllegroSettingsInput {
  client_id: string;
  /** Blank keeps the stored secret; it is never sent back. */
  client_secret: string;
  user_agent: string;
  environment: AllegroEnvironment;
}

export interface AllegroConnectStart {
  flow_id: string;
  verification_uri: string;
  user_code: string;
  interval: number;
  expires_in: number;
}

export interface AllegroConnectPoll {
  status: "pending" | "connected";
  account_login: string | null;
}

export interface AllegroImportResult {
  created: number;
  updated: number;
  cancellation_warnings: number;
}

export interface ErliStatus {
  /** A key is set, in Settings or in backend/.env. */
  configured: boolean;
  source: "settings" | "environment" | "none";
  /** The key's last characters, never the key itself. */
  key_hint: string | null;
  /** How the last import ended, by the button or the script. */
  last_import_at: string | null;
  last_import_created: number | null;
  last_import_updated: number | null;
  /** Set when the last import failed. */
  last_import_error: string | null;
}

export const integrationsApi = {
  erliStatus(): Promise<ErliStatus> {
    return request<ErliStatus>("/integrations/erli");
  },

  /** Saved only once Erli has accepted the key. */
  saveErliKey(apiKey: string): Promise<ErliStatus> {
    return request<ErliStatus>("/integrations/erli/settings", {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    });
  },

  forgetErliKey(): Promise<ErliStatus> {
    return request<ErliStatus>("/integrations/erli/settings", { method: "DELETE" });
  },

  importErli(): Promise<AllegroImportResult> {
    return request<AllegroImportResult>("/integrations/erli/import", { method: "POST" });
  },

  allegroStatus(): Promise<AllegroStatus> {
    return request<AllegroStatus>("/integrations/allegro");
  },

  saveAllegroSettings(input: AllegroSettingsInput): Promise<AllegroStatus> {
    return request<AllegroStatus>("/integrations/allegro/settings", {
      method: "PUT",
      body: JSON.stringify({
        ...input,
        client_secret: input.client_secret || null,
      }),
    });
  },

  startAllegroConnection(): Promise<AllegroConnectStart> {
    return request<AllegroConnectStart>("/integrations/allegro/connect", {
      method: "POST",
    });
  },

  pollAllegroConnection(flowId: string): Promise<AllegroConnectPoll> {
    return request<AllegroConnectPoll>(`/integrations/allegro/connect/${flowId}`);
  },

  disconnectAllegro(): Promise<AllegroStatus> {
    return request<AllegroStatus>("/integrations/allegro/connection", {
      method: "DELETE",
    });
  },

  importAllegro(): Promise<AllegroImportResult> {
    return request<AllegroImportResult>("/integrations/allegro/import", {
      method: "POST",
    });
  },
};

export const ordersApi = {
  list(params: ListOrdersParams = {}): Promise<OrderListResponse> {
    return request<OrderListResponse>(`/orders${buildQuery(params)}`);
  },

  get(orderId: string): Promise<OrderWithDetails> {
    return request<OrderWithDetails>(`/orders/${orderId}`);
  },

  buyerOrders(orderId: string): Promise<Order[]> {
    return request<Order[]>(`/orders/${orderId}/buyer-orders`);
  },

  billing(orderId: string): Promise<OrderBilling> {
    return request<OrderBilling>(`/orders/${orderId}/billing`);
  },

  history(orderId: string): Promise<OrderStatusChange[]> {
    return request<OrderStatusChange[]>(`/orders/${orderId}/history`);
  },

  updateStatus(orderId: string, status: OrderStatus): Promise<OrderChangeResult> {
    return request<OrderChangeResult>(`/orders/${orderId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  },

  addShipment(
    orderId: string,
    shipment: { carrier_id: string; carrier_name?: string; waybill: string },
  ): Promise<OrderChangeResult> {
    return request<OrderChangeResult>(`/orders/${orderId}/shipments`, {
      method: "POST",
      body: JSON.stringify(shipment),
    });
  },

  /**
   * Take an order out of every list. The row is kept, so it can be restored and
   * an import does not bring it back; an order with a bought label is refused.
   */
  delete(orderId: string): Promise<OrderWithDetails> {
    return request<OrderWithDetails>(`/orders/${orderId}`, { method: "DELETE" });
  },

  restore(orderId: string): Promise<OrderWithDetails> {
    return request<OrderWithDetails>(`/orders/${orderId}/restore`, { method: "POST" });
  },

  production(): Promise<ProductionList> {
    return request<ProductionList>("/orders/production");
  },

  stats(): Promise<OrderStats> {
    return request<OrderStats>("/orders/stats");
  },
};

/** Safe mode: while on, nothing Anvero would change on a marketplace is sent. */
export interface SafeMode {
  enabled: boolean;
  /** When and by whom it was last switched; null while it never has been. */
  changed_at: string | null;
  changed_by: string | null;
}

/** "off": not set up; "warning": works but needs attention; "error": does not work. */
export type HealthState = "off" | "ok" | "warning" | "error";

/** This backend's own import schedule. */
export interface ScheduleStatus {
  interval_minutes: number;
  running: boolean;
  started_at: string | null;
  next_run_at: string | null;
  last_run_at: string | null;
}

/** How the last import ended, whoever ran it; all null before the first. */
export interface LastImport {
  at: string | null;
  created: number | null;
  updated: number | null;
  error: string | null;
}

export interface AllegroHealth {
  state: HealthState;
  /** Codes for what makes the state less than "ok"; worded by the page. */
  problems: string[];
  application_complete: boolean;
  connected: boolean;
  environment: AllegroEnvironment;
  account_login: string | null;
  token_issued_at: string | null;
  token_expires_at: string | null;
  last_import: LastImport;
  schedule: ScheduleStatus;
  /** This backend's schedule for reading buyer messages into the inbox. */
  message_schedule: ScheduleStatus;
}

export interface ErliHealth {
  state: HealthState;
  problems: string[];
  configured: boolean;
  last_import: LastImport;
  /** Null: Erli has no schedule yet, only the import script. */
  schedule: ScheduleStatus | null;
}

export interface AppStatus {
  checked_at: string;
  version: string;
  safe_mode: boolean;
  allegro: AllegroHealth;
  erli: ErliHealth;
}

export const statusApi = {
  get(): Promise<AppStatus> {
    return request<AppStatus>("/status");
  },
};

export interface ShippingSender {
  name: string;
  company: string | null;
  street: string;
  postal_code: string;
  city: string;
  country_code: string;
  email: string;
  phone: string;
}

/** Centimetres and kilograms, as decimal strings from the backend. */
export interface PackageSize {
  length_cm: string;
  width_cm: string;
  height_cm: string;
  weight_kg: string;
}

export interface ShippingSettings {
  sender: ShippingSender | null;
  default_package: PackageSize | null;
}

export type LabelStatus = "PENDING" | "CREATED" | "FAILED" | "CANCELLED";

export interface ShippingLabel extends PackageSize {
  id: string;
  created_at: string;
  status: LabelStatus;
  shipment_id: string | null;
  carrier_id: string | null;
  waybill: string | null;
  error: string | null;
  /** When its label was last fetched for printing; null until then. */
  printed_at?: string | null;
}

export type PickupStatus = "PENDING" | "ORDERED" | "FAILED";

/** A courier ordered through Wysyłam z Allegro to collect parcels. */
export interface CourierPickup {
  id: string;
  created_at: string;
  status: PickupStatus;
  pickup_id: string | null;
  carrier_id: string | null;
  /** YYYY-MM-DD */
  ready_date: string;
  /** The slot chosen, as it was shown. */
  proposal_label: string;
  error: string | null;
}

/** A bought label on the Labels page, with what identifies its order. */
export interface PrintableLabel extends ShippingLabel {
  order_id: string;
  order_label: string;
  buyer: string | null;
  delivery_method: string | null;
  pickup?: CourierPickup | null;
}

/** Which bought labels the Labels page lists. */
export type LabelView = "to_print" | "no_pickup" | "all";

export interface PickupOption {
  id: string;
  label: string;
}

export interface PickupChangeResult {
  /** Null when nothing was ordered: held back by safe mode, or refused. */
  pickup: CourierPickup | null;
  marketplace_write: MarketplaceWrite;
}

export interface LabelChangeResult {
  /** Null when nothing was bought: held back by safe mode, or refused. */
  label: ShippingLabel | null;
  marketplace_write: MarketplaceWrite;
}

export const shippingApi = {
  settings(): Promise<ShippingSettings> {
    return request<ShippingSettings>("/settings/shipping");
  },

  saveSettings(settings: ShippingSettings): Promise<ShippingSettings> {
    return request<ShippingSettings>("/settings/shipping", {
      method: "PUT",
      body: JSON.stringify(settings),
    });
  },

  labels(orderId: string): Promise<ShippingLabel[]> {
    return request<ShippingLabel[]>(`/orders/${orderId}/labels`);
  },

  buy(orderId: string, pkg: PackageSize): Promise<LabelChangeResult> {
    return request<LabelChangeResult>(`/orders/${orderId}/labels`, {
      method: "POST",
      body: JSON.stringify(pkg),
    });
  },

  refresh(orderId: string, labelId: string): Promise<ShippingLabel> {
    return request<ShippingLabel>(`/orders/${orderId}/labels/${labelId}/refresh`, {
      method: "POST",
    });
  },

  cancel(orderId: string, labelId: string): Promise<LabelChangeResult> {
    return request<LabelChangeResult>(`/orders/${orderId}/labels/${labelId}/cancel`, {
      method: "POST",
    });
  },

  /** Bought labels across every order, oldest first. */
  printable(view: LabelView = "to_print"): Promise<PrintableLabel[]> {
    return request<PrintableLabel[]>(`/labels?view=${view}`);
  },

  /** When a courier could come for these parcels that day; changes nothing. */
  pickupProposals(labelIds: string[], readyDate: string): Promise<PickupOption[]> {
    return request<PickupOption[]>("/pickups/proposals", {
      method: "POST",
      body: JSON.stringify({ label_ids: labelIds, ready_date: readyDate }),
    });
  },

  orderPickup(labelIds: string[], readyDate: string, option: PickupOption): Promise<PickupChangeResult> {
    return request<PickupChangeResult>("/pickups", {
      method: "POST",
      body: JSON.stringify({
        label_ids: labelIds,
        ready_date: readyDate,
        proposal_id: option.id,
        proposal_label: option.label,
      }),
    });
  },

  refreshPickup(pickupId: string): Promise<CourierPickup> {
    return request<CourierPickup>(`/pickups/${pickupId}/refresh`, { method: "POST" });
  },

  /** Several labels as one A6 PDF, in the order given; notes them printed. */
  pdfMany(labelIds: string[]): Promise<Blob> {
    return request<Blob>("/labels/pdf", {
      method: "POST",
      body: JSON.stringify({ label_ids: labelIds }),
      blob: true,
    });
  },

  /**
   * A sample A6 label drawn by Anvero: nothing is bought and nothing is sent,
   * so it works with safe mode on and without an Allegro account.
   */
  testLabel(): Promise<Blob> {
    return request<Blob>("/labels/test-pdf", { blob: true });
  },

  /** The A6 label as a PDF; it needs the login token, so it cannot be a plain link. */
  pdf(orderId: string, labelId: string): Promise<Blob> {
    return request<Blob>(`/orders/${orderId}/labels/${labelId}/pdf`, { blob: true });
  },
};

export const safeModeApi = {
  get(): Promise<SafeMode> {
    return request<SafeMode>("/settings/safe-mode");
  },

  set(enabled: boolean): Promise<SafeMode> {
    return request<SafeMode>("/settings/safe-mode", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    });
  },
};

/** One change sent to a marketplace, or held back by safe mode. */
export interface MarketplaceWrite {
  id: string;
  created_at: string;
  source: OrderSource;
  order_id: string | null;
  action: string;
  /** JSON text, as the marketplace would get it. */
  payload: string;
  outcome: "DRY_RUN" | "SENT" | "FAILED";
  /** The marketplace's answer, or the error. */
  detail: string | null;
  user: string | null;
}

export const marketplaceWritesApi = {
  list(params: { orderId?: string; limit?: number } = {}): Promise<MarketplaceWrite[]> {
    const query = new URLSearchParams();
    if (params.orderId) query.set("order_id", params.orderId);
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    const queryString = query.toString();
    return request<MarketplaceWrite[]>(`/marketplace-writes${queryString ? `?${queryString}` : ""}`);
  },
};

/**
 * An order after a change made in Anvero, and what became of sending it to
 * the marketplace; `marketplace_write` is null when nothing was for it.
 */
export type OrderChangeResult = OrderWithDetails & {
  marketplace_write?: MarketplaceWrite | null;
};

/** One message in a thread, read from the marketplace or sent from Anvero. */
export interface ThreadMessage {
  id: string;
  direction: "IN" | "OUT";
  author_login: string | null;
  text: string;
  sent_at: string;
  /** A reply written in Anvero, as opposed to read from the marketplace. */
  created_in_anvero: boolean;
}

/** One buyer-seller conversation on a marketplace's Message Center. */
export interface MessageThread {
  id: string;
  source: OrderSource;
  interlocutor_login: string | null;
  /** The marketplace's own order id the thread names, if any. */
  order_external_id: string | null;
  last_message_at: string | null;
  last_message_text: string | null;
  /** The marketplace's own read flag, mirrored at the last sync. */
  read: boolean;
  /** Set aside by an operator to come back to later. */
  aside: boolean;
}

export interface MessageThreadDetail extends MessageThread {
  messages: ThreadMessage[];
}

export interface MessageSyncResult {
  threads_synced: number;
  messages_added: number;
}

export const messagesApi = {
  /**
   * Threads, newest activity first. A `search` looks through every thread (set
   * aside or not) for a buyer's nick, an order id or a word of a message.
   */
  threads(
    params: { aside?: boolean; unreadOnly?: boolean; search?: string } = {},
  ): Promise<MessageThread[]> {
    const query = new URLSearchParams();
    if (params.aside !== undefined) query.set("aside", String(params.aside));
    if (params.unreadOnly) query.set("unread_only", "true");
    if (params.search) query.set("search", params.search);
    const queryString = query.toString();
    return request<MessageThread[]>(`/messages/threads${queryString ? `?${queryString}` : ""}`);
  },

  thread(threadId: string): Promise<MessageThreadDetail> {
    return request<MessageThreadDetail>(`/messages/threads/${threadId}`);
  },

  setAside(threadId: string, aside: boolean): Promise<MessageThread> {
    return request<MessageThread>(`/messages/threads/${threadId}/aside`, {
      method: "PATCH",
      body: JSON.stringify({ aside }),
    });
  },

  reply(threadId: string, text: string): Promise<{ thread: MessageThreadDetail; marketplace_write: MarketplaceWrite }> {
    return request(`/messages/threads/${threadId}/reply`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },

  syncAllegro(): Promise<MessageSyncResult> {
    return request<MessageSyncResult>("/integrations/allegro/messages/sync", {
      method: "POST",
    });
  },
};

export type CaseKind = "RETURN" | "CLAIM" | "DISPUTE";
export type CaseAction = "NONE" | "DECIDE" | "REPLY" | "RECOVER_COMMISSION";
/** What the queue shows: what waits for the seller, everything open, or everything. */
export type CaseView = "action" | "open" | "all";

/** A return, claim or dispute, and what it asks of the seller. */
export interface AfterSalesCase {
  id: string;
  source: string;
  kind: CaseKind;
  /** The marketplace's own status (CLAIM_SUBMITTED, DELIVERED...). */
  status: string;
  is_open: boolean;
  action: CaseAction;
  /** By when the action is due; null when there is no deadline. */
  due_at: string | null;
  /** The deadline has passed while the seller still has to act. */
  overdue: boolean;
  reference_number: string | null;
  buyer_login: string | null;
  buyer_email: string | null;
  opened_at: string;
  /** The marketplace's reason code, worded by the interface. */
  reason: string | null;
  summary: string | null;
  detail: string | null;
  order_external_id: string | null;
  /** The Anvero order it belongs to, when that has been imported. */
  order_id: string | null;
  order_label: string | null;
}

export interface AfterSalesList {
  items: AfterSalesCase[];
  total: number;
}

export interface AfterSalesSummary {
  needs_action: number;
  overdue: number;
  due_soon: number;
}

export interface AfterSalesSyncResult {
  returns: number;
  claims: number;
  disputes: number;
}

export const afterSalesApi = {
  list(view: CaseView = "action", kind?: CaseKind): Promise<AfterSalesList> {
    const query = new URLSearchParams({ view });
    if (kind) query.set("kind", kind);
    return request<AfterSalesList>(`/after-sales?${query.toString()}`);
  },

  summary(): Promise<AfterSalesSummary> {
    return request<AfterSalesSummary>("/after-sales/summary");
  },

  forOrder(orderId: string): Promise<AfterSalesCase[]> {
    return request<AfterSalesCase[]>(`/orders/${orderId}/after-sales`);
  },

  /** Read returns, claims and disputes from Allegro. */
  sync(): Promise<AfterSalesSyncResult> {
    return request<AfterSalesSyncResult>("/integrations/allegro/after-sales/sync", {
      method: "POST",
    });
  },
};
