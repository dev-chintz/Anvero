export enum OrderSource {
  ALLEGRO = "ALLEGRO",
  ERLI = "ERLI",
}

export enum OrderStatus {
  NEW = "NEW",
  CONFIRMED = "CONFIRMED",
  SHIPPED = "SHIPPED",
  DELIVERED = "DELIVERED",
  CANCELLED = "CANCELLED",
}

export interface Order {
  id: string;
  external_id: string;
  source: OrderSource;
  status: OrderStatus;
  customer_email: string;
  total_amount: string;
  currency: string;
  /** When the buyer placed the order; for imports, the marketplace's time. */
  ordered_at: string;
  /** When the row was created in Anvero. */
  created_at: string;
  updated_at: string;
  marketplace_cancelled_at: string | null;
}

export enum PaymentType {
  ONLINE = "ONLINE",
  BANK_TRANSFER = "BANK_TRANSFER",
  CASH_ON_DELIVERY = "CASH_ON_DELIVERY",
  DEFERRED = "DEFERRED",
  OTHER = "OTHER",
}

export interface Address {
  first_name: string | null;
  last_name: string | null;
  company_name: string | null;
  street: string | null;
  postal_code: string | null;
  city: string | null;
  country_code: string | null;
  phone: string | null;
  /** Company tax number, on invoice addresses. */
  tax_id: string | null;
}

export interface OrderItem {
  id: string;
  external_id: string | null;
  offer_id: string | null;
  sku: string | null;
  name: string;
  quantity: number;
  /** Per unit, in the order's currency. */
  unit_price: string;
}

/**
 * A single order with its details, as GET /orders/{id} returns it. Every
 * detail may be null: hand-entered orders and older imports have none.
 */
export interface OrderWithDetails extends Order {
  customer: {
    login: string | null;
    first_name: string | null;
    last_name: string | null;
    company_name: string | null;
    phone: string | null;
  };
  items: OrderItem[];
  delivery: {
    method: string | null;
    cost: string | null;
    address: Address | null;
    pickup_point: {
      id: string | null;
      name: string | null;
      address: Address | null;
    } | null;
  };
  payment: {
    type: PaymentType | null;
    provider: string | null;
    /** Null means unknown; "0.00" means known to be unpaid. */
    paid_amount: string | null;
    paid_at: string | null;
  };
  invoice: {
    required: boolean;
    address: Address | null;
  };
  buyer_message: string | null;
}

/**
 * Cancelled on the marketplace while still active in Anvero.
 *
 * Mirrors the backend's definition, which drives the list filter and the
 * dashboard count, so a flagged row and the counts never disagree.
 */
export function hasCancellationWarning(order: Order): boolean {
  return (
    order.marketplace_cancelled_at !== null &&
    order.status !== OrderStatus.CANCELLED
  );
}

export interface OrderListResponse {
  items: Order[];
  total: number;
  skip: number;
  limit: number;
}

export interface OrderStatusChange {
  id: string;
  from_status: OrderStatus;
  to_status: OrderStatus;
  changed_at: string;
  /** Email of the user who made the change; null for older entries. */
  changed_by: string | null;
}

export interface OrderStats {
  total_orders: number;
  total_revenue: string;
  this_week: number;
  pending: number;
  cancellation_warnings: number;
  by_status: Record<string, number>;
  by_source: Record<string, number>;
}

export interface OrderCreate {
  external_id: string;
  source: OrderSource;
  customer_email: string;
  total_amount: string;
  currency?: string;
  status?: OrderStatus;
}
