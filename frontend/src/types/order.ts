export enum OrderSource {
  ALLEGRO = "ALLEGRO",
  ERLI = "ERLI",
}

export enum OrderStatus {
  NEW = "NEW",
  /** Being made or prepared ("in progress"); Allegro's PROCESSING. */
  CONFIRMED = "CONFIRMED",
  /** Made and packed, waiting for the carrier. */
  READY_FOR_SHIPMENT = "READY_FOR_SHIPMENT",
  SHIPPED = "SHIPPED",
  DELIVERED = "DELIVERED",
  CANCELLED = "CANCELLED",
}

export interface Order {
  id: string;
  /** Anvero's own number for the order: continuous, never reused. */
  order_number: number;
  /** The number as it is shown and searched, e.g. AN-000123. */
  order_label: string;
  /** The marketplace's own order id. */
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
   * replacing it: it is what the next import compares against, and a
   * status set by hand stands until it moves. Optional in the type because a
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
   * cost. Optional because a backend older than the field omits them.
   */
  customer_login?: string | null;
  customer_first_name?: string | null;
  customer_last_name?: string | null;
  payment_type?: PaymentType | null;
  payment_provider?: string | null;
  /**
   * The latest moment the parcel must be handed over, as the marketplace
   * states it; null when it states none. Optional because a backend older
   * than the field omits it.
   */
  dispatch_by?: string | null;
  /** Optional because a backend older than the field omits it. */
  shipments?: Shipment[];
  /** When the status last changed; null for an order that has kept its first status. */
  status_changed_at?: string | null;
  /** The operator's own marks, for finding an order again. */
  starred?: boolean;
  flagged?: boolean;
  /** The list's small facts, from which its icons are drawn. */
  delivery_country_code?: string | null;
  /** What has been paid; null when unknown. */
  paid_amount?: string | null;
  invoice_required?: boolean;
  has_buyer_message?: boolean;
  has_seller_note?: boolean;
  /**
   * Set while an operator has deleted the order: it is in no list unless the
   * deleted ones were asked for, and is kept to be restored. Optional because a
   * backend older than the field omits it.
   */
  deleted_at?: string | null;
  /** The email of whoever deleted it. */
  deleted_by?: string | null;
  /**
   * What was bought, in short: the list shows it in its Items column. Only
   * these four fields are on the list; `OrderWithDetails` has the whole item.
   * Optional because a backend older than the field omits it.
   */
  items?: OrderItemSummary[];
}

/**
 * Whether the buyer has paid what is due before shipping, as far as the list can
 * tell: "paid", "unpaid", or null when it cannot (no payment recorded, or one paid
 * after delivery). The same rule as the backend's "unpaid" queue.
 */
export function paymentState(order: Order): "paid" | "unpaid" | null {
  const paid = order.paid_amount == null ? null : Number(order.paid_amount);
  const total = Number(order.total_amount);
  const paysLater =
    order.payment_type === PaymentType.CASH_ON_DELIVERY ||
    order.payment_type === PaymentType.DEFERRED;
  if (paysLater) return null;
  if (paid !== null) return paid >= total ? "paid" : "unpaid";
  return order.payment_type ? "unpaid" : null;
}

/** One item as the order list carries it: enough to recognise the product. */
export interface OrderItemSummary {
  name: string;
  sku: string | null;
  quantity: number;
  /** The offer's picture, or null when there is none. */
  image_url: string | null;
}

/** Statuses of an order still waiting on the seller. */
export const PENDING_STATUSES: readonly OrderStatus[] = [
  OrderStatus.NEW,
  OrderStatus.CONFIRMED,
  OrderStatus.READY_FOR_SHIPMENT,
];

/** The work queues `GET /orders?queue=` knows; the backend defines what is in each. */
export enum OrderQueue {
  TO_MAKE = "to_make",
  UNPAID = "unpaid",
  TO_SHIP = "to_ship",
  /** To make or to ship, past the dispatch deadline; overlaps both. */
  LATE = "late",
}

export enum OrderSort {
  NEWEST = "newest",
  OLDEST = "oldest",
  /** Closest dispatch deadline first, orders without one last. */
  AT_RISK = "at_risk",
}

/**
 * How the dispatch deadline stands for a waiting order: null when there is
 * none to watch (no deadline, or the order is past waiting).
 */
export function dispatchUrgency(
  order: Order,
  now: Date = new Date(),
): "late" | "soon" | "later" | null {
  if (!PENDING_STATUSES.includes(order.status)) return null;
  return deadlineUrgency(order.dispatch_by, now);
}

/** How near a dispatch deadline is: past, within a day, or further; null without one. */
export function deadlineUrgency(
  dispatchBy: string | null | undefined,
  now: Date = new Date(),
): "late" | "soon" | "later" | null {
  if (!dispatchBy) return null;
  const left = new Date(dispatchBy).getTime() - now.getTime();
  if (left < 0) return "late";
  return left < 24 * 60 * 60 * 1000 ? "soon" : "later";
}

/** One order needing some of a production line's product. */
export interface ProductionOrder {
  id: string;
  order_label: string;
  source: OrderSource;
  status: OrderStatus;
  /** How many of the line's product this order takes. */
  quantity: number;
  dispatch_by: string | null;
}

/** One product to make: everything the waiting orders need of it. */
export interface ProductionLine {
  /** What the line groups by: "sku:…", "offer:…" or "name:…". */
  key: string;
  sku: string | null;
  offer_id: string | null;
  name: string;
  image_url: string | null;
  quantity: number;
  /** The earliest dispatch deadline among its orders. */
  dispatch_by: string | null;
  /** Most urgent first. */
  orders: ProductionOrder[];
}

/** `GET /orders/production`: the to-make queue, by product, most urgent first. */
export interface ProductionList {
  lines: ProductionLine[];
  order_count: number;
}

export enum PaymentType {
  ONLINE = "ONLINE",
  BANK_TRANSFER = "BANK_TRANSFER",
  CASH_ON_DELIVERY = "CASH_ON_DELIVERY",
  DEFERRED = "DEFERRED",
  OTHER = "OTHER",
}

/** A parcel sent for an order. Owned by the marketplace, like the items. */
export interface Shipment {
  id: string;
  external_id: string | null;
  /** The carrier as the marketplace names it, e.g. DHL. */
  carrier_id: string | null;
  carrier_name: string | null;
  waybill: string;
  shipped_at: string | null;
  /** The carrier's latest tracking code (IN_TRANSIT, DELIVERED, ...); null when none was read. */
  tracking_status: string | null;
  tracking_updated_at: string | null;
}

/** What to call the carrier: its own name when it gave one, else the marketplace's id for it. */
export function carrierLabel(shipment: Shipment): string {
  return shipment.carrier_name ?? shipment.carrier_id ?? "";
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

/** One operation on the seller's marketplace account: a fee, a correction, a refunded fee. */
export interface BillingEntry {
  id: string;
  occurred_at: string;
  type_id: string;
  type_name: string | null;
  /** Signed: a charge is negative. */
  amount: string;
  currency: string;
}

/** What the marketplace has charged, and credited back, for one order. */
export interface OrderBilling {
  entries: BillingEntry[];
  /** The entries added up in the order's currency; negative is a net charge. */
  total: string;
  currency: string;
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
  /** Orders in each work queue. Optional because an older backend omits it. */
  queues?: Record<OrderQueue, number>;
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
