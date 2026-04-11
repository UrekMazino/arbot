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
  children?: AdminNavItem[];
};

export const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  {
    href: "/admin/dashboard",
    label: "Dashboard",
    hint: "Analytics & Portfolio",
    group: "Monitor",
    icon: "dashboard",
    requiredPermissions: ["view_dashboard"],
    children: [
      {
        href: "/admin/dashboard/analytics",
        label: "Analytics",
        group: "Monitor",
        requiredPermissions: ["view_analytics"],
      },
      {
        href: "/admin/dashboard/portfolio",
        label: "Portfolio",
        group: "Monitor",
        requiredPermissions: ["view_portfolio"],
      },
    ],
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
  const findItem = (items: AdminNavItem[]): AdminNavItem | undefined => {
    for (const item of items) {
      if (item.href === href) return item;
      if (item.children) {
        const found = findItem(item.children);
        if (found) return found;
      }
    }
    return undefined;
  };

  const navItem = findItem(ADMIN_NAV_ITEMS);
  if (!navItem) {
    return false;
  }
  return hasAnyPermission(user, navItem.requiredPermissions);
}

export function getAdminNavItems(user: UserRecord | null | undefined): Omit<AdminNavItem, "requiredPermissions">[] {
  const result: Omit<AdminNavItem, "requiredPermissions">[] = [];

  const processItems = (items: AdminNavItem[]) => {
    for (const item of items) {
      const hasPermission = hasAnyPermission(user, item.requiredPermissions);
      const accessibleChildren = item.children
        ? item.children.filter((child) => hasAnyPermission(user, child.requiredPermissions))
        : [];

      // If item has children, only include if it has accessible children
      // If item has no children, include if user has direct permission
      if (item.children && item.children.length > 0) {
        // Parent with children: only show if there are accessible children
        if (accessibleChildren.length > 0) {
          const { requiredPermissions, children, ...navItem } = item;
          result.push({
            ...navItem,
            children: accessibleChildren.map(({ requiredPermissions, ...child }) => {
              void requiredPermissions;
              return child;
            }),
          });
        }
      } else {
        // Item without children: include if user has direct permission
        if (hasPermission) {
          const { requiredPermissions, children, ...navItem } = item;
          result.push(navItem);
        }
      }
    }
  };

  processItems(ADMIN_NAV_ITEMS);
  return result;
}

export function getFirstAccessibleAdminPath(user: UserRecord | null | undefined): string | null {
  const items = getAdminNavItems(user);

  // If there are nav items, use the first one
  if (items.length > 0) {
    const first = items[0];
    // If the first item has children, return the first child's href
    if (first.children && first.children.length > 0) {
      return first.children[0].href || null;
    }
    return first.href || null;
  }

  // No nav items - check if user can access /admin/dashboard directly
  if (canAccessAdminPath(user, "/admin/dashboard")) {
    return "/admin/dashboard";
  }

  return null;
}

export function hasAnyAdminAccess(user: UserRecord | null | undefined): boolean {
  return getFirstAccessibleAdminPath(user) !== null;
}
