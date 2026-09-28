export type Role = "admin" | "user";

/** Where the interface groups actions for a permission: a business owner grants
 * access by the part of the application someone works in, not by API call. */
export type PermissionArea =
  | "orders"
  | "messages"
  | "after_sales"
  | "labels"
  | "finance"
  | "integrations";

export type PermissionLevel = "view" | "manage";

export interface PermissionGrant {
  area: PermissionArea;
  level: PermissionLevel;
}

export interface User {
  id: number;
  email: string;
  role: Role;
  is_active: boolean;
  /** Empty for an admin: it can do everything already. */
  permissions: PermissionGrant[];
  created_at: string;
  updated_at: string;
}

export interface UserCreateInput {
  email: string;
  password: string;
  role: Role;
  permissions: PermissionGrant[];
}

/** Every field is optional; a field left out is unchanged. `permissions`,
 * when given, replaces the whole set. */
export interface UserUpdateInput {
  role?: Role;
  is_active?: boolean;
  password?: string;
  permissions?: PermissionGrant[];
}

export interface Token {
  access_token: string;
  token_type: string;
}
