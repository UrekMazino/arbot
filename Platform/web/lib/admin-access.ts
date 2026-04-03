import type { UserRecord } from "./api";
import { resolveRolePermissionIds } from "./permissions";
import type { SidebarIconName } from "../components/layout/sidebar-icons";

export type AdminNavItem = {
  href: string;
  label: string;
  hint?: string;
  group?: string;
  icon?: SidebarIconName;
  requiredPermissions?: string[];
};

export const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  {
    href: "/admin/dashboard",
    label: "Dashboard",
    hint: "Runs, quality, reports",
    group: "Monitor",
    icon: "dashboard",
    requiredPermissions: ["view_dashboard"],
  },
  {
    href: "/admin/console",
    label: "Console",
    hint: "Control plane",
    group: "Operate",
    icon: "console",
    requiredPermissions: ["view_logs", "manage_bot"],
  },
  {
    href: "/admin/settings",
    label: "Settings",
    hint: "Configuration & credentials",
    group: "Operate",
    icon: "settings",
    requiredPermissions: ["edit_settings", "manage_api"],
  },
  {
    href: "/admin/access",
    label: "Access",
    hint: "Users, roles, permissions",
    group: "Operate",
    icon: "access",
    requiredPermissions: ["manage_users", "manage_roles"],
  },
];

export function getUserPermissionIds(user: UserRecord | null | undefined): string[] {
  const permissions = new Set<string>();
  for (const permissionId of user?.permissions || []) {
    permissions.add(permissionId);
  }
  for (const role of user?.roles || []) {
    for (const permissionId of resolveRolePermissionIds(role.name, role.permissions)) {
      permissions.add(permissionId);
    }
  }
  return Array.from(permissions);
}

export function hasPermission(user: UserRecord | null | undefined, permissionId: string): boolean {
  return getUserPermissionIds(user).includes(permissionId);
}

export function hasAnyPermission(user: UserRecord | null | undefined, permissionIds: string[] | undefined): boolean {
  if (!permissionIds || permissionIds.length === 0) {
    return true;
  }
  const granted = new Set(getUserPermissionIds(user));
  return permissionIds.some((permissionId) => granted.has(permissionId));
}

export function canAccessAdminPath(user: UserRecord | null | undefined, href: string): boolean {
  const navItem = ADMIN_NAV_ITEMS.find((item) => item.href === href);
  if (!navItem) {
    return false;
  }
  return hasAnyPermission(user, navItem.requiredPermissions);
}

export function getAdminNavItems(user: UserRecord | null | undefined): Omit<AdminNavItem, "requiredPermissions">[] {
  return ADMIN_NAV_ITEMS.filter((item) => hasAnyPermission(user, item.requiredPermissions)).map(
    ({ requiredPermissions: _requiredPermissions, ...item }) => item,
  );
}

export function getFirstAccessibleAdminPath(user: UserRecord | null | undefined): string | null {
  return getAdminNavItems(user)[0]?.href || null;
}

export function hasAnyAdminAccess(user: UserRecord | null | undefined): boolean {
  return getFirstAccessibleAdminPath(user) !== null;
}
