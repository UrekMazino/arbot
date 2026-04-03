/**
 * Permission management constants and utilities
 * Centralized location for all available permissions and role-permission mappings
 */

export interface Permission {
  id: string;
  label: string;
  description: string;
}

export const AVAILABLE_PERMISSIONS: Permission[] = [
  { id: "view_dashboard", label: "View Dashboard", description: "Access dashboard and metrics" },
  { id: "view_logs", label: "View Logs", description: "View bot logs and terminal output" },
  { id: "manage_bot", label: "Manage Bot", description: "Start/stop bot and control execution" },
  { id: "view_reports", label: "View Reports", description: "Access generated reports" },
  { id: "edit_settings", label: "Edit Settings", description: "Modify configuration and environment variables" },
  { id: "manage_api", label: "Manage API Credentials", description: "View and edit API keys" },
  { id: "manage_users", label: "Manage Users", description: "Create and modify user accounts" },
  { id: "manage_roles", label: "Manage Roles", description: "Assign and remove user roles" },
];

/**
 * Role to permissions mapping
 * Defines what permissions each role grants by default
 */
export const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: AVAILABLE_PERMISSIONS.map((p) => p.id),
  trader: ["view_dashboard", "view_logs", "manage_bot", "view_reports"],
  viewer: ["view_dashboard", "view_logs", "view_reports"],
};

/**
 * Check if a user has a specific permission
 * @param userPermissions - Array of permission IDs the user has
 * @param permissionId - The permission ID to check
 * @returns True if user has the permission, false otherwise
 */
export function hasPermission(userPermissions: string[], permissionId: string): boolean {
  return userPermissions.includes(permissionId);
}

/**
 * Get the human-readable label for a permission ID
 * @param permissionId - The permission ID to look up
 * @returns The permission label, or the permissionId if not found
 */
export function getPermissionLabel(permissionId: string): string {
  const permission = AVAILABLE_PERMISSIONS.find((p) => p.id === permissionId);
  return permission?.label || permissionId;
}

/**
 * Get all permissions for a role
 * @param roleName - The name of the role
 * @returns Array of permission IDs for the role
 */
export function getRolePermissionIds(roleName: string): string[] {
  return ROLE_PERMISSIONS[roleName] || [];
}

export function resolveRolePermissionIds(roleName: string, storedPermissions?: string[] | null): string[] {
  if (storedPermissions && storedPermissions.length > 0) {
    return [...storedPermissions];
  }
  return getRolePermissionIds(roleName);
}

/**
 * Find a permission by its ID
 * @param permissionId - The permission ID to find
 * @returns The permission object, or undefined if not found
 */
export function findPermissionById(permissionId: string): Permission | undefined {
  return AVAILABLE_PERMISSIONS.find((p) => p.id === permissionId);
}
