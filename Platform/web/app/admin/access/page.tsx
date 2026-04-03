"use client";

import { Dispatch, FormEvent, SetStateAction, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  RoleRecord,
  UserRecord,
  assignUserRole,
  createRole,
  createUser,
  deleteRole,
  deleteUser,
  getMe,
  isUnauthorizedError,
  listRoles,
  listUsers,
  removeUserRole,
  updateRole,
  updateUserPermissions,
} from "../../../lib/api";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
  hasPermission,
} from "../../../lib/admin-access";
import { clearStoredAdminSession, getStoredAdminAccessToken, getStoredAdminEmail } from "../../../lib/auth";
import { UI_CLASSES } from "../../../lib/ui-classes";
import { AVAILABLE_PERMISSIONS, resolveRolePermissionIds } from "../../../lib/permissions";
import { DashboardShell } from "../../../components/dashboard-shell";
import { TableFrame } from "../../../components/panels";
import { AppModal } from "../../../components/ui/modal";

type TabType = "users" | "roles";

export default function UserManagementPage() {
  const router = useRouter();
  const [token, setToken] = useState<string>("");
  const [status, setStatus] = useState("Signed out");
  const [error, setError] = useState("");
  const [authChecked, setAuthChecked] = useState(false);
  const [profileResolved, setProfileResolved] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>("users");

  const [me, setMe] = useState<UserRecord | null>(null);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const navItems = useMemo(() => getAdminNavItems(me), [me]);
  const fallbackHref = useMemo(() => getFirstAccessibleAdminPath(me), [me]);
  const canManageUsers = hasPermission(me, "manage_users");
  const canManageRoles = hasPermission(me, "manage_roles");
  const canViewAccess = canAccessAdminPath(me, "/admin/access");

  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");

  // Role CRUD state
  const [newRoleName, setNewRoleName] = useState("");
  const [newRoleDescription, setNewRoleDescription] = useState("");
  const [newRolePermissions, setNewRolePermissions] = useState<string[]>([]);
  const [editingRoleId, setEditingRoleId] = useState<string | null>(null);
  const [editingRoleName, setEditingRoleName] = useState("");
  const [editingRoleDescription, setEditingRoleDescription] = useState("");
  const [editingRolePermissions, setEditingRolePermissions] = useState<string[]>([]);

  // Modal states
  const [assignRoleModalUser, setAssignRoleModalUser] = useState<UserRecord | null>(null);
  const [assignRoleModalRoleName, setAssignRoleModalRoleName] = useState("");
  const [deleteConfirmUser, setDeleteConfirmUser] = useState<UserRecord | null>(null);
  const [permissionEditorUser, setPermissionEditorUser] = useState<UserRecord | null>(null);


  const clearAdminSession = useCallback((reason = "Signed out", redirectToLogin = false) => {
    clearStoredAdminSession();
    setToken("");
    setStatus(reason);
    setError("");
    setProfileResolved(false);
    setMe(null);
    setUsers([]);
    setRoles([]);
    if (redirectToLogin) {
      router.replace("/login?next=/admin/access");
    }
  }, [router]);

  const loadUserManagementData = useCallback(
    async (authToken: string) => {
      const meData = await getMe(authToken);
      setMe(meData);
      if (!canAccessAdminPath(meData, "/admin/access")) {
        setUsers([]);
        setRoles([]);
        return;
      }
      const canLoadUsers = hasPermission(meData, "manage_users");
      const canLoadRoles = canLoadUsers || hasPermission(meData, "manage_roles");
      const [usersData, rolesData] = await Promise.all([
        canLoadUsers ? listUsers(authToken) : Promise.resolve([] as UserRecord[]),
        canLoadRoles ? listRoles(authToken) : Promise.resolve([] as RoleRecord[]),
      ]);
      setUsers(usersData);
      setRoles(rolesData);
    },
    [],
  );

  useEffect(() => {
    const stored = getStoredAdminAccessToken();
    if (!stored) {
      setAuthChecked(true);
      router.replace("/login?next=/admin/access");
      return;
    }
    const storedEmail = getStoredAdminEmail();
    setToken(stored);
    setStatus("Loading access...");
    setAuthChecked(true);
    setProfileResolved(false);
    if (storedEmail) {
      const fallbackMe: UserRecord = {
        id: "",
        email: storedEmail,
        is_active: false,
        permissions: [],
        roles: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setMe((prev) => (prev ? { ...prev, email: storedEmail } : fallbackMe));
    }
    loadUserManagementData(stored)
      .then(() => {
        setStatus("Session restored");
      })
      .catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearAdminSession("Session expired. Please sign in again.", true);
          setError("Session expired. Please sign in again.");
          return;
        }
        const msg = err instanceof Error ? err.message : "Failed loading user management";
        setError(msg);
      })
      .finally(() => setProfileResolved(true));
  }, [clearAdminSession, loadUserManagementData, router]);

  useEffect(() => {
    if (!profileResolved || !me || canViewAccess) {
      return;
    }
    setUsers([]);
    setRoles([]);
    if (fallbackHref && fallbackHref !== "/admin/access") {
      setStatus("Redirecting");
      setError("Access management permissions are not enabled for your account.");
      router.replace(fallbackHref);
    }
  }, [canViewAccess, fallbackHref, me, profileResolved, router]);

  useEffect(() => {
    if (canManageUsers) {
      setActiveTab((prev) => (prev === "roles" && !canManageRoles ? "users" : prev));
      return;
    }
    if (canManageRoles) {
      setActiveTab("roles");
      return;
    }
  }, [canManageUsers, canManageRoles]);

  async function handleCreateUser(e: FormEvent) {
    e.preventDefault();
    if (!token || !canManageUsers || !newUserEmail || !newUserPassword) return;

    setBusy(true);
    setError("");
    try {
      await createUser(token, {
        email: newUserEmail,
        password: newUserPassword,
      });
      setNewUserEmail("");
      setNewUserPassword("");
      setStatus("User created");
      await loadUserManagementData(token);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Create user failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveRole(userId: string, roleNameToRemove: string) {
    if (!token || (!canManageUsers && !canManageRoles)) return;

    setBusy(true);
    setError("");
    try {
      await removeUserRole(token, userId, roleNameToRemove);
      setStatus("Role removed");
      await loadUserManagementData(token);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Remove role failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteUser(userId: string) {
    if (!token || !canManageUsers) return;

    setBusy(true);
    setError("");
    try {
      await deleteUser(token, userId);
      setDeleteConfirmUser(null);
      setStatus("User deleted");
      await loadUserManagementData(token);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Delete user failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleAssignRoleFromModal(e: FormEvent) {
    e.preventDefault();
    if (!token || (!canManageUsers && !canManageRoles) || !assignRoleModalUser || !assignRoleModalRoleName) return;

    setBusy(true);
    setError("");
    try {
      await assignUserRole(token, assignRoleModalUser.id, assignRoleModalRoleName);
      setAssignRoleModalUser(null);
      setAssignRoleModalRoleName("");
      setStatus("Role assigned");
      await loadUserManagementData(token);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Assign role failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateRole(e: FormEvent) {
    e.preventDefault();
    if (!token || !canManageRoles || !newRoleName) return;

    setBusy(true);
    setError("");
    try {
      await createRole(token, {
        name: newRoleName,
        description: newRoleDescription,
        permissions: newRolePermissions,
      });
      setNewRoleName("");
      setNewRoleDescription("");
      setNewRolePermissions([]);
      setStatus("Role created");
      await loadUserManagementData(token);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Create role failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdateRole(e: FormEvent) {
    e.preventDefault();
    if (!token || !canManageRoles || !editingRoleId || !editingRoleName) return;

    setBusy(true);
    setError("");
    try {
      await updateRole(token, editingRoleId, {
        name: editingRoleName,
        description: editingRoleDescription,
        permissions: editingRolePermissions,
      });
      resetRoleEditor();
      setStatus("Role updated");
      await loadUserManagementData(token);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Update role failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteRole(roleId: string, roleName: string) {
    if (!token || !canManageRoles || !confirm(`Are you sure you want to delete the role "${roleName}"?`)) return;

    setBusy(true);
    setError("");
    try {
      await deleteRole(token, roleId);

      setStatus("Role deleted");
      await loadUserManagementData(token);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Delete role failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  function getUserPermissions(user: UserRecord): string[] {
    return [...(user.permissions || [])];
  }

  function getRolePermissions(user: UserRecord): string[] {
    const rolePerms: string[] = [];
    user.roles.forEach((role) => {
      rolePerms.push(...resolveRolePermissionIds(role.name, role.permissions));
    });
    return [...new Set(rolePerms)];
  }

  function getSavedRolePermissions(role: RoleRecord): string[] {
    return resolveRolePermissionIds(role.name, role.permissions);
  }

  function applyUpdatedUserRecord(updatedUser: UserRecord) {
    setUsers((prev) => prev.map((user) => (user.id === updatedUser.id ? updatedUser : user)));
    setMe((prev) => (prev?.id === updatedUser.id ? updatedUser : prev));
    setAssignRoleModalUser((prev) => (prev?.id === updatedUser.id ? updatedUser : prev));
    setDeleteConfirmUser((prev) => (prev?.id === updatedUser.id ? updatedUser : prev));
    setPermissionEditorUser((prev) => (prev?.id === updatedUser.id ? updatedUser : prev));
  }

  async function handleToggleUserPermission(user: UserRecord, permissionId: string) {
    if (!token || !canManageUsers) return;

    const currentPermissions = getUserPermissions(user);
    const hasCustomPermission = currentPermissions.includes(permissionId);
    const nextPermissions = hasCustomPermission
      ? currentPermissions.filter((id) => id !== permissionId)
      : [...currentPermissions, permissionId];

    setBusy(true);
    setError("");
    try {
      const updatedUser = await updateUserPermissions(token, user.id, nextPermissions);
      applyUpdatedUserRecord(updatedUser);
      setStatus(`Permission ${hasCustomPermission ? "removed" : "added"}`);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Update user permissions failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  function toggleRolePermission(
    permissionId: string,
    selectedPermissions: string[],
    setSelectedPermissions: Dispatch<SetStateAction<string[]>>,
  ) {
    setSelectedPermissions((prev) =>
      prev.includes(permissionId)
        ? prev.filter((id) => id !== permissionId)
        : [...prev, permissionId],
    );
    setStatus(
      `${selectedPermissions.includes(permissionId) ? "Removed" : "Added"} role permission ${permissionId}`,
    );
  }

  function beginRoleEdit(role: RoleRecord) {
    setEditingRoleId(role.id);
    setEditingRoleName(role.name);
    setEditingRoleDescription(role.description || "");
    setEditingRolePermissions(getSavedRolePermissions(role));
  }

  function resetRoleEditor() {
    setEditingRoleId(null);
    setEditingRoleName("");
    setEditingRoleDescription("");
    setEditingRolePermissions([]);
  }

  const secondaryButtonClasses = UI_CLASSES.secondaryButton;
  const primaryButtonClasses = UI_CLASSES.primaryButton;
  const sectionCardClasses = UI_CLASSES.sectionCard;

  if (!authChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">Checking admin session...</p>
      </div>
    );
  }

  if (!token) {
    return null;
  }

  if (profileResolved && me && !canViewAccess && !fallbackHref) {
    return (
      <DashboardShell
        title="User Management"
        subtitle="Manage users, roles, and permissions."
        status="Access restricted"
        activeHref="/admin/access"
        navItems={navItems}
        auth={{
          email: me.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
          hasToken: Boolean(token),
        }}
      >
        <div className="grid gap-4">
          <section className={sectionCardClasses}>
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-white/90">User Management</h1>
            <p className="mt-2 text-sm text-error-600 dark:text-error-400">Access management permissions are not enabled for this account.</p>
          </section>
        </div>
      </DashboardShell>
    );
  }

  if (token && !profileResolved) {
    return (
      <DashboardShell
        title="User Management"
        subtitle="Manage users, roles, and permissions."
        status={status}
        activeHref="/admin/access"
        navItems={navItems}
        auth={{
          email: me?.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
          hasToken: Boolean(token),
        }}
      >
        <div className="grid gap-4">
          <section className={sectionCardClasses}>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-500">Access</p>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{status}</p>
            </div>
          </section>
        </div>
      </DashboardShell>
    );
  }

  const tabButtonClass = (isActive: boolean) =>
    `px-4 py-2 font-medium text-sm ${
      isActive
        ? "border-b-2 border-brand-500 text-brand-600 dark:text-brand-400"
        : "border-b-2 border-transparent text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-300"
    }`;

  return (
    <DashboardShell
      title="User Management"
      subtitle="Manage users, roles, and permissions."
      status={status}
      activeHref="/admin/access"
      navItems={navItems}
      auth={{
        email: me?.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
        hasToken: Boolean(token),
      }}
    >
      <div className="grid gap-4">
        <section className={sectionCardClasses}>
          <div className="border-b border-gray-200 dark:border-gray-700">
            <div className="flex gap-8">
              {canManageUsers ? (
                <button
                  onClick={() => setActiveTab("users")}
                  className={tabButtonClass(activeTab === "users")}
                >
                  Users
                </button>
              ) : null}
              {canManageRoles ? (
                <button
                  onClick={() => setActiveTab("roles")}
                  className={tabButtonClass(activeTab === "roles")}
                >
                  Roles
                </button>
                ) : null}
            </div>
          </div>

          {error ? <p className="mt-4 text-sm text-error-600 dark:text-error-400">{error}</p> : null}

          <div className="mt-6">
            {activeTab === "users" && canManageUsers && (
              <div>
                <div className="mb-4">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">User Management</h3>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Create new users and manage their roles and permissions.</p>
                </div>

                {/* Create User Form */}
                <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
                  <h4 className="mb-3 text-sm font-semibold text-gray-900 dark:text-white/90">Create New User</h4>
                  <form onSubmit={handleCreateUser} className="flex flex-wrap items-center gap-2">
                    <input
                      value={newUserEmail}
                      onChange={(e) => setNewUserEmail(e.target.value)}
                      placeholder="email"
                      required
                      className="rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                    />
                    <input
                      value={newUserPassword}
                      onChange={(e) => setNewUserPassword(e.target.value)}
                      placeholder="password"
                      type="password"
                      required
                      className="rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                    />
                    <button type="submit" disabled={busy} className={primaryButtonClasses}>
                      Create User
                    </button>
                  </form>
                </div>

                {/* Users List */}
                <TableFrame compact>
                  <table>
                    <thead>
                      <tr>
                        <th>Email</th>
                        <th>Active</th>
                        <th>Roles</th>
                        <th>Permissions</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((user) => (
                        <tr key={user.id}>
                          <td className="font-medium">{user.email}</td>
                          <td>{user.is_active ? "yes" : "no"}</td>
                          <td>
                            <div className="flex flex-wrap items-center gap-1.5">
                              {user.roles.length > 0 ? (
                                user.roles.map((role) => (
                                  <button
                                    key={`${user.id}-${role.name}`}
                                    className="inline-flex items-center rounded-full border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                                    onClick={() => handleRemoveRole(user.id, role.name)}
                                    disabled={busy}
                                  >
                                    {role.name} x
                                  </button>
                                ))
                              ) : (
                                <span className="text-xs text-gray-400">—</span>
                              )}
                            </div>
                          </td>
                          <td>
                            <div className="flex flex-wrap gap-1.5">
                              <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-1 text-[11px] font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                                role {getRolePermissions(user).length}
                              </span>
                              <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-1 text-[11px] font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                                custom {getUserPermissions(user).length}
                              </span>
                            </div>
                          </td>
                          <td>
                            <div className="flex gap-2">
                              <button
                                onClick={() => setPermissionEditorUser(user)}
                                className="text-xs text-violet-600 hover:text-violet-700 dark:text-violet-400 dark:hover:text-violet-300"
                                disabled={busy}
                              >
                                Permissions
                              </button>
                              <button
                                onClick={() => setAssignRoleModalUser(user)}
                                className="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                                disabled={busy}
                              >
                                Assign Role
                              </button>
                              <button
                                onClick={() => setDeleteConfirmUser(user)}
                                className="text-xs text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                                disabled={busy}
                              >
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {!users.length ? (
                        <tr>
                          <td colSpan={5} className="text-sm text-gray-500 dark:text-gray-400">
                            No users found.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </TableFrame>

                <AppModal
                  open={Boolean(assignRoleModalUser)}
                  title={assignRoleModalUser ? `Assign Role to ${assignRoleModalUser.email}` : "Assign Role"}
                  description="Choose one of the existing roles for this user."
                  size="sm"
                  onClose={() => {
                    setAssignRoleModalUser(null);
                    setAssignRoleModalRoleName("");
                  }}
                  footer={
                    <div className="flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={() => {
                          setAssignRoleModalUser(null);
                          setAssignRoleModalRoleName("");
                        }}
                        className={secondaryButtonClasses}
                      >
                        Cancel
                      </button>
                      <button type="submit" form="assign-role-form" disabled={busy} className={primaryButtonClasses}>
                        Assign Role
                      </button>
                    </div>
                  }
                >
                  <form id="assign-role-form" onSubmit={handleAssignRoleFromModal} className="space-y-4">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      Role
                      <select
                        value={assignRoleModalRoleName}
                        onChange={(e) => setAssignRoleModalRoleName(e.target.value)}
                        className="mt-2 w-full rounded-2xl border border-gray-300 bg-white px-4 py-3 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-3 focus:ring-brand-500/15 dark:border-gray-700 dark:bg-gray-800 dark:text-white/90"
                        required
                      >
                        <option value="">Select role</option>
                        {roles.map((role) => (
                          <option key={role.id} value={role.name}>
                            {role.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  </form>
                </AppModal>

                <AppModal
                  open={Boolean(deleteConfirmUser)}
                  title="Delete User"
                  description={
                    deleteConfirmUser
                      ? `This will permanently remove ${deleteConfirmUser.email} from the platform.`
                      : "This action cannot be undone."
                  }
                  size="sm"
                  onClose={() => setDeleteConfirmUser(null)}
                  footer={
                    <div className="flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={() => setDeleteConfirmUser(null)}
                        className={secondaryButtonClasses}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteConfirmUser && handleDeleteUser(deleteConfirmUser.id)}
                        disabled={busy}
                        className="inline-flex items-center rounded-xl border border-red-300 bg-red-50 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-100 disabled:opacity-70 dark:border-red-900 dark:bg-red-950/20 dark:text-red-300 dark:hover:bg-red-950/40"
                      >
                        Delete User
                      </button>
                    </div>
                  }
                >
                  <div className="rounded-2xl border border-red-100 bg-red-50/70 p-4 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300">
                    User roles and custom permissions will be removed together with this account.
                  </div>
                </AppModal>

                <AppModal
                  open={Boolean(permissionEditorUser)}
                  title={permissionEditorUser ? `Manage Permissions for ${permissionEditorUser.email}` : "Manage Permissions"}
                  description="Role-granted permissions are read-only here. Use add and remove for user-specific overrides."
                  size="md"
                  onClose={() => setPermissionEditorUser(null)}
                  footer={
                    <div className="flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={() => setPermissionEditorUser(null)}
                        className={secondaryButtonClasses}
                      >
                        Done
                      </button>
                    </div>
                  }
                >
                  {permissionEditorUser ? (
                    <div className="space-y-5">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
                          From Roles
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {getRolePermissions(permissionEditorUser).length > 0 ? (
                            getRolePermissions(permissionEditorUser).map((permId) => {
                              const perm = AVAILABLE_PERMISSIONS.find((p) => p.id === permId);
                              return (
                                <span
                                  key={permId}
                                  className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 dark:border-blue-900 dark:bg-blue-950/20 dark:text-blue-300"
                                >
                                  {perm?.label || permId}
                                </span>
                              );
                            })
                          ) : (
                            <span className="text-sm text-gray-400">No role permissions</span>
                          )}
                        </div>
                      </div>

                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
                          Custom Permissions
                        </p>
                        <div className="mt-3 grid gap-3">
                          {AVAILABLE_PERMISSIONS.map((perm) => {
                            const fromRole = getRolePermissions(permissionEditorUser).includes(perm.id);
                            const hasCustomPermission = getUserPermissions(permissionEditorUser).includes(perm.id);
                            return (
                              <div
                                key={`${permissionEditorUser.id}-${perm.id}`}
                                className="flex items-start justify-between gap-4 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
                              >
                                <div className="min-w-0">
                                  <p className="text-sm font-semibold text-gray-900 dark:text-white/90">{perm.label}</p>
                                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{perm.description}</p>
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {fromRole ? (
                                      <span className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] font-medium text-blue-700 dark:border-blue-900 dark:bg-blue-950/20 dark:text-blue-300">
                                        granted by role
                                      </span>
                                    ) : null}
                                    {hasCustomPermission ? (
                                      <span className="inline-flex items-center rounded-full border border-green-200 bg-green-50 px-2.5 py-1 text-[11px] font-medium text-green-700 dark:border-green-900 dark:bg-green-950/20 dark:text-green-300">
                                        custom override
                                      </span>
                                    ) : null}
                                    {!fromRole && !hasCustomPermission ? (
                                      <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-[11px] font-medium text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                                        not assigned
                                      </span>
                                    ) : null}
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => handleToggleUserPermission(permissionEditorUser, perm.id)}
                                  disabled={busy || fromRole}
                                  className={
                                    fromRole
                                      ? "inline-flex items-center rounded-xl border border-gray-200 bg-gray-50 px-3.5 py-2 text-xs font-medium text-gray-500 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400"
                                      : hasCustomPermission
                                        ? "inline-flex items-center rounded-xl border border-red-300 bg-red-50 px-3.5 py-2 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-60 dark:border-red-900 dark:bg-red-950/20 dark:text-red-300 dark:hover:bg-red-950/40"
                                        : "inline-flex items-center rounded-xl border border-brand-300 bg-brand-50 px-3.5 py-2 text-xs font-medium text-brand-700 hover:bg-brand-100 disabled:opacity-60 dark:border-brand-900 dark:bg-brand-950/20 dark:text-brand-300 dark:hover:bg-brand-950/40"
                                  }
                                >
                                  {fromRole ? "From Role" : hasCustomPermission ? "Remove" : "Add"}
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  ) : null}
                </AppModal>
              </div>
            )}

            {activeTab === "roles" && canManageRoles && (
              <div>
                <div className="mb-4">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Role Management</h3>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Create, edit, and manage roles with custom permissions.</p>
                </div>

                {/* Create Role Form */}
                <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
                  <h4 className="mb-4 text-sm font-semibold text-gray-900 dark:text-white/90">
                    {editingRoleId ? "Edit Role" : "Create New Role"}
                  </h4>
                  <form
                    onSubmit={editingRoleId ? handleUpdateRole : handleCreateRole}
                    className="flex flex-col gap-3"
                  >
                    <input
                      value={editingRoleId ? editingRoleName : newRoleName}
                      onChange={(e) =>
                        editingRoleId
                          ? setEditingRoleName(e.target.value)
                          : setNewRoleName(e.target.value)
                      }
                      placeholder="Role name (e.g., analyst, operator)"
                      required
                      className="rounded border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                    />
                    <textarea
                      value={editingRoleId ? editingRoleDescription : newRoleDescription}
                      onChange={(e) =>
                        editingRoleId
                          ? setEditingRoleDescription(e.target.value)
                          : setNewRoleDescription(e.target.value)
                      }
                      placeholder="Role description (optional)"
                      rows={2}
                      className="rounded border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                    />
                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900/40">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-gray-900 dark:text-white/90">Role Permissions</p>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {(editingRoleId ? editingRolePermissions : newRolePermissions).length} selected
                        </span>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        {AVAILABLE_PERMISSIONS.map((perm) => {
                          const selectedPermissions = editingRoleId ? editingRolePermissions : newRolePermissions;
                          const isChecked = selectedPermissions.includes(perm.id);
                          return (
                            <label
                              key={perm.id}
                              className="flex items-start gap-3 rounded-lg border border-gray-200 bg-white p-3 text-sm dark:border-gray-700 dark:bg-gray-800"
                            >
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() =>
                                  toggleRolePermission(
                                    perm.id,
                                    selectedPermissions,
                                    editingRoleId ? setEditingRolePermissions : setNewRolePermissions,
                                  )
                                }
                                className="mt-0.5 h-4 w-4 rounded border-gray-300 dark:border-gray-600"
                              />
                              <span className="min-w-0">
                                <span className="block font-medium text-gray-900 dark:text-white/90">{perm.label}</span>
                                <span className="block text-xs text-gray-500 dark:text-gray-400">{perm.description}</span>
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button type="submit" disabled={busy} className={primaryButtonClasses}>
                        {editingRoleId ? "Update Role" : "Create Role"}
                      </button>
                      {editingRoleId && (
                        <button
                          type="button"
                          onClick={resetRoleEditor}
                          className={secondaryButtonClasses}
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                  </form>
                </div>


                {/* Roles List */}
                <div className="mb-6">
                  <h4 className="mb-3 text-sm font-semibold text-gray-900 dark:text-white/90">All Roles</h4>
                  <TableFrame compact>
                    <table>
                      <thead>
                        <tr>
                          <th>Role Name</th>
                          <th>Users Assigned</th>
                          <th>Permissions</th>
                          <th>Description</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {roles.map((role) => {
                          const usersWithRole = users.filter((user) =>
                            user.roles.some((r) => r.name === role.name)
                          );
                          return (
                            <tr key={role.id}>
                              <td className="font-mono text-sm font-medium">{role.name}</td>
                              <td className="text-sm">{usersWithRole.length}</td>
                              <td>
                                <div className="flex max-w-[360px] flex-wrap gap-1">
                                  {getSavedRolePermissions(role).length > 0 ? (
                                    getSavedRolePermissions(role).map((permId) => {
                                      const perm = AVAILABLE_PERMISSIONS.find((row) => row.id === permId);
                                      return (
                                        <span
                                          key={`${role.id}-${permId}`}
                                          className="inline-flex items-center rounded-full bg-blue-100 px-2 py-1 text-[11px] font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                        >
                                          {perm?.label || permId}
                                        </span>
                                      );
                                    })
                                  ) : (
                                    <span className="text-xs text-gray-400">No permissions</span>
                                  )}
                                </div>
                              </td>
                              <td className="text-xs text-gray-600 dark:text-gray-400">
                                {role.description || "—"}
                              </td>
                              <td>
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => beginRoleEdit(role)}
                                    className="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                                    disabled={busy}
                                  >
                                    Edit
                                  </button>

                                  {role.name !== "admin" && role.name !== "trader" && role.name !== "viewer" && (
                                    <button
                                      onClick={() => handleDeleteRole(role.id, role.name)}
                                      className="text-xs text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                                      disabled={busy}
                                    >
                                      Delete
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                        {!roles.length ? (
                          <tr>
                            <td colSpan={5} className="text-sm text-gray-500 dark:text-gray-400">
                              No roles found.
                            </td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </TableFrame>
                </div>

                {/* Role Permissions Management */}

              </div>
            )}

          </div>
        </section>
      </div>
    </DashboardShell>
  );
}
