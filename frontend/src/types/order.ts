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
  created_at: string;
  updated_at: string;
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
}

export interface OrderStats {
  total_orders: number;
  total_revenue: string;
  this_week: number;
  pending: number;
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
