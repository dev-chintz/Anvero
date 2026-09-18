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
  /**
   * What the marketplace's own status mapped to at the last import. Null for
   * an order no import has touched. It is kept beside `status` rather than
   * replacing it: `status` is the operator's. Optional in the type because a
   * backend older than the field omits it.
   */
  marketplace_status?: OrderStatus | null;
  /**
   * The same status in the marketplace's own words, e.g. Allegro's
   * `READY_FOR_SHIPMENT`. Anvero's five statuses collapse distinctions the
   * marketplace's panel shows, so this is what to display.
   */
  marketplace_status_label?: string | null;
  marketplace_cancelled_at: string | null;
  /**
   * Flat columns on `orders`, so the list carries them at no extra query
   * cost — unlike items, which need a join `GET /orders` does not do.
   * Optional because a backend older than the field omits them.
   */
  customer_login?: string | null;
  customer_first_name?: string | null;
  customer_last_name?: string | null;
  payment_type?: PaymentType | null;
  payment_provider?: string | null;
}

export enum PaymentType {
  ONLINE = "ONLINE",
  BANK_TRANSFER = "BANK_TRANSFER",
  CASH_ON_DELIVERY = "CASH_ON_DELIVERY",
  DEFERRED = "DEFERRED",
  OTHER = "OTHER",
}

export const PAYMENT_TYPE_LABELS: Record<PaymentType, string> = {
  [PaymentType.ONLINE]: "Online payment",
  [PaymentType.BANK_TRANSFER]: "Bank transfer",
  [PaymentType.CASH_ON_DELIVERY]: "Cash on delivery",
  [PaymentType.DEFERRED]: "Deferred payment",
  [PaymentType.OTHER]: "Other",
};

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
  /** The offer's picture, fetched from Allegro at import time; null for a
   * hand-entered order, an older import, or an offer whose picture could
   * not be read. */
  image_url: string | null;
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
  /** The seller's own note on the order, e.g. Allegro's checkout-form note. */
  seller_note: string | null;
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

/**
 * The marketplace has moved the order somewhere Anvero has not followed.
 *
 * A cancellation is left out: it has its own, louder warning, and showing
 * both would say the same thing twice.
 */
export function marketplaceStatusDiffers(order: Order): boolean {
  // `!= null` on purpose, so a response without the field at all — an older
  // backend, or a page still holding one fetched before a deploy — reads as
  // "nothing to show" rather than rendering an empty badge
  return (
    order.marketplace_status != null &&
    order.marketplace_status !== order.status &&
    order.marketplace_status !== OrderStatus.CANCELLED
  );
}

/** What the marketplace calls the order's status, for showing to the operator. */
export function marketplaceStatusText(order: Order): string {
  return order.marketplace_status_label ?? order.marketplace_status ?? "";
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
