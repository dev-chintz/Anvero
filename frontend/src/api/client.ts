import { SESSION_EXPIRED_EVENT, clearToken, getToken } from "../auth/session";
import type {
  OrderListResponse,
  OrderStats,
  OrderStatusChange,
  OrderWithDetails,
} from "../types/order";
import type { OrderSource, OrderStatus } from "../types/order";
import type { Token, User } from "../types/user";

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
    throw new ApiError(0, "Network error: could not reach the server");
  }

  if (!response.ok) {
    if (response.status === 401 && authenticated) {
      clearToken();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
      throw new ApiError(401, "Your session has ended. Please log in again.");
    }
    if (response.status === 401) {
      throw new ApiError(401, "Incorrect email or password");
    }
    const message = await extractErrorMessage(response);
    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
}

async function extractErrorMessage(response: Response): Promise<string> {
  switch (response.status) {
    case 404:
      return "Not found";
    case 429:
      return "Too many requests: please slow down and try again shortly";
    case 500:
      return "Server error: something went wrong on our end";
    default:
      break;
  }

  try {
    const body = (await response.json()) as { detail?: string; error?: string };
    return body.detail ?? body.error ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
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

export interface AllegroStatus {
  configured: boolean;
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
