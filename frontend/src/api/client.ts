import type { Order, OrderListResponse, OrderStats } from "../types/order";
import type { OrderSource, OrderStatus } from "../types/order";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(0, "Network error: could not reach the server");
  }

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
}

async function extractErrorMessage(response: Response): Promise<string> {
  switch (response.status) {
    case 401:
      return "Unauthorized: please sign in again";
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
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export const ordersApi = {
  list(params: ListOrdersParams = {}): Promise<OrderListResponse> {
    return request<OrderListResponse>(`/orders${buildQuery(params)}`);
  },

  get(orderId: string): Promise<Order> {
    return request<Order>(`/orders/${orderId}`);
  },

  stats(): Promise<OrderStats> {
    return request<OrderStats>("/orders/stats");
  },
};
