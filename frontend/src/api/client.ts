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
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { authenticated = true, headers, ...init } = options;
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

export const integrationsApi = {
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
