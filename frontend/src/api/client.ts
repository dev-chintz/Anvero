import { SESSION_EXPIRED_EVENT, clearToken, getToken } from "../auth/session";
import type {
  OrderListResponse,
  OrderStats,
  OrderStatusChange,
  OrderWithDetails,
} from "../types/order";
import type { OrderSource, OrderStatus } from "../types/order";
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

  history(orderId: string): Promise<OrderStatusChange[]> {
    return request<OrderStatusChange[]>(`/orders/${orderId}/history`);
  },

  updateStatus(orderId: string, status: OrderStatus): Promise<OrderWithDetails> {
    return request<OrderWithDetails>(`/orders/${orderId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  },

  stats(): Promise<OrderStats> {
    return request<OrderStats>("/orders/stats");
  },
};
