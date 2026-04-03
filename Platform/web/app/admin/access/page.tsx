"use client";

import { Dispatch, FormEvent, SetStateAction, useCallback, useEffect, useState } from "react";
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
} from "../../../lib/api";
import { clearStoredAdminSession, getStoredAdminAccessToken, getStoredAdminEmail } from "../../../lib/auth";
import { UI_CLASSES } from "../../../lib/ui-classes";
import { AVAILABLE_PERMISSIONS, resolveRolePermissionIds } from "../../../lib/permissions";
import { DashboardShell } from "../../../components/dashboard-shell";
import { TableFrame } from "../../../components/panels";

type TabType = "users" | "roles" | "permissions";

function hasAdminRole(user: UserRecord | null): boolean {
  return Boolean(user?.roles.some((role) => role.name.toLowerCase() === "admin"));
}

export default function UserManagementPage() {
  const router = useRouter();
  const [token, setToken] = useState<string>("");
  const [status, setStatus] = useState("Signed out");
  const [error, setError] = useState("");
  const [authChecked, setAuthChecked] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>("users");

  const [me, setMe] = useState<UserRecord | null>(null);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [busy, setBusy] = useState(false);

  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [userPermissionsMap, setUserPermissionsMap] = useState<Record<string, string[]>>({});
  const [selectedPermissionUser, setSelectedPermissionUser] = useState("");

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
  const [viewPermissionsUser, setViewPermissionsUser] = useState<UserRecord | null>(null);


  const clearAdminSession = useCallback((reason = "Signed out", redirectToLogin = false) => {
    clearStoredAdminSession();
    setToken("");
    setStatus(reason);
    setError("");
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
      if (!hasAdminRole(meData)) {
        setUsers([]);
        setRoles([]);
        return;
      }
      const [usersData, rolesData] = await Promise.all([
        listUsers(authToken),
        listRoles(authToken),
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
    setToken(stored);
    setStatus("Session restored");
    loadUserManagementData(stored)
      .catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearAdminSession("Session expired. Please sign in again.", true);
          setError("Session expired. Please sign in again.");
          return;
        }
        const msg = err instanceof Error ? err.message : "Failed loading user management";
        setError(msg);
      })
      .finally(() => setAuthChecked(true));
  }, [clearAdminSession, loadUserManagementData, router]);

  async function handleCreateUser(e: FormEvent) {
    e.preventDefault();
    if (!token || !newUserEmail || !newUserPassword) return;

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
    if (!token) return;

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
    if (!token) return;

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
    if (!token || !assignRoleModalUser || !assignRoleModalRoleName) return;

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
    if (!token || !newRoleName) return;

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
    if (!token || !editingRoleId || !editingRoleName) return;

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
    if (!token || !confirm(`Are you sure you want to delete the role "${roleName}"?`)) return;

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



  function toggleUserPermission(userId: string, permissionId: string) {
    setUserPermissionsMap((prev) => {
      const userPerms = prev[userId] ? [...prev[userId]] : [];
      const index = userPerms.indexOf(permissionId);
      if (index > -1) {
        userPerms.splice(index, 1);
      } else {
        userPerms.push(permissionId);
      }
      if (userPerms.length === 0) {
        const nextMap = { ...prev };
        delete nextMap[userId];
        return nextMap;
      }
      return { ...prev, [userId]: userPerms };
    });
    const hasPermission = userPermissionsMap[userId]?.includes(permissionId) ?? false;
    setStatus(`Permission ${hasPermission ? "removed" : "added"}`);
  }

  function getUserPermissions(userId: string): string[] {
    return userPermissionsMap[userId] ? [...userPermissionsMap[userId]] : [];
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

  if (me && !hasAdminRole(me)) {
    return (
      <DashboardShell
        title="User Management"
        subtitle="Manage users, roles, and permissions."
        status={status}
        activeHref="/admin/access"
        navItems={[
          { href: "/admin/dashboard", label: "Dashboard", hint: "Runs, quality, reports", group: "Monitor", icon: "DB" },
          { href: "/admin/console", label: "Console", hint: "Control plane", group: "Operate", icon: "CM" },
          { href: "/admin/settings", label: "Settings", hint: "Configuration & credentials", group: "Operate", icon: "ST" },
          { href: "/admin/access", label: "Access", hint: "Users, roles, permissions", group: "Operate", icon: "UM" },
        ]}
      >
        <div className="grid gap-4">
          <section className={sectionCardClasses}>
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-white/90">User Management</h1>
            <p className="mt-2 text-sm text-error-600 dark:text-error-400">Admin role required for access.</p>
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
      navItems={[
        { href: "/admin/dashboard", label: "Dashboard", hint: "Runs, quality, reports", group: "Monitor", icon: "DB" },
        { href: "/admin/console", label: "Console", hint: "Control plane", group: "Operate", icon: "CM" },
        { href: "/admin/settings", label: "Settings", hint: "Configuration & credentials", group: "Operate", icon: "ST" },
        { href: "/admin/access", label: "Access", hint: "Users, roles, permissions", group: "Operate", icon: "UM" },
      ]}
      auth={{
        email: me?.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
        hasToken: Boolean(token),
      }}
    >
      <div className="grid gap-4">
        <section className={sectionCardClasses}>
          <div className="border-b border-gray-200 dark:border-gray-700">
            <div className="flex gap-8">
              <button
                onClick={() => setActiveTab("users")}
                className={tabButtonClass(activeTab === "users")}
              >
                Users
              </button>
              <button
                onClick={() => setActiveTab("roles")}
                className={tabButtonClass(activeTab === "roles")}
              >
                Roles
              </button>
              <button
                onClick={() => setActiveTab("permissions")}
                className={tabButtonClass(activeTab === "permissions")}
              >
                Permissions
              </button>
            </div>
          </div>

          {error ? <p className="mt-4 text-sm text-error-600 dark:text-error-400">{error}</p> : null}

          <div className="mt-6">
            {activeTab === "users" && (
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
                            <button
                              onClick={() => setViewPermissionsUser(user)}
                              className="text-xs text-purple-600 hover:text-purple-700 dark:text-purple-400 dark:hover:text-purple-300"
                            >
                              View
                            </button>
                          </td>
                          <td>
                            <div className="flex gap-2">
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

                {/* Assign Role Modal */}
                {assignRoleModalUser && (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                    <div className="w-full max-w-md rounded-lg bg-white p-6 dark:bg-gray-800">
                      <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white/90">
                        Assign Role to {assignRoleModalUser.email}
                      </h3>
                      <form onSubmit={handleAssignRoleFromModal} className="space-y-4">
                        <select
                          value={assignRoleModalRoleName}
                          onChange={(e) => setAssignRoleModalRoleName(e.target.value)}
                          className="w-full rounded border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                          required
                        >
                          <option value="">-- Select Role --</option>
                          {roles.map((role) => (
                            <option key={role.id} value={role.name}>
                              {role.name}
                            </option>
                          ))}
                        </select>
                        <div className="flex gap-2">
                          <button type="submit" disabled={busy} className={primaryButtonClasses}>
                            Assign
                          </button>
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
                        </div>
                      </form>
                    </div>
                  </div>
                )}

                {/* Delete Confirmation Modal */}
                {deleteConfirmUser && (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                    <div className="w-full max-w-md rounded-lg bg-white p-6 dark:bg-gray-800">
                      <h3 className="mb-2 text-lg font-semibold text-gray-900 dark:text-white/90">Delete User?</h3>
                      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
                        Are you sure you want to delete <span className="font-medium">{deleteConfirmUser.email}</span>? This action cannot be undone.
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleDeleteUser(deleteConfirmUser.id)}
                          disabled={busy}
                          className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60 dark:bg-red-700 dark:hover:bg-red-800"
                        >
                          Delete
                        </button>
                        <button
                          onClick={() => setDeleteConfirmUser(null)}
                          className={secondaryButtonClasses}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* View Permissions Modal */}
                {viewPermissionsUser && (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                    <div className="w-full max-w-2xl rounded-lg bg-white p-6 dark:bg-gray-800">
                      <div className="mb-4 flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">
                          Permissions for {viewPermissionsUser.email}
                        </h3>
                        <button
                          onClick={() => setViewPermissionsUser(null)}
                          className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                        >
                          ✕
                        </button>
                      </div>

                      <div className="mb-4 space-y-3">
                        <div>
                          <p className="mb-2 text-xs font-semibold uppercase text-gray-600 dark:text-gray-400">
                            From Roles
                          </p>
                          <div className="flex flex-wrap gap-2">
                            {getRolePermissions(viewPermissionsUser).length > 0 ? (
                              getRolePermissions(viewPermissionsUser).map((permId) => {
                                const perm = AVAILABLE_PERMISSIONS.find((p) => p.id === permId);
                                return (
                                  <span
                                    key={permId}
                                    className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                  >
                                    {perm?.label || permId}
                                  </span>
                                );
                              })
                            ) : (
                              <span className="text-xs text-gray-400">No role permissions</span>
                            )}
                          </div>
                        </div>

                        <div>
                          <p className="mb-2 text-xs font-semibold uppercase text-gray-600 dark:text-gray-400">
                            Custom Permissions
                          </p>
                          <div className="flex flex-wrap gap-2">
                            {getUserPermissions(viewPermissionsUser.id).length > 0 ? (
                              getUserPermissions(viewPermissionsUser.id).map((permId) => {
                                const perm = AVAILABLE_PERMISSIONS.find((p) => p.id === permId);
                                return (
                                  <span
                                    key={permId}
                                    className="inline-flex items-center rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200"
                                  >
                                    {perm?.label || permId}
                                  </span>
                                );
                              })
                            ) : (
                              <span className="text-xs text-gray-400">No custom permissions</span>
                            )}
                          </div>
                        </div>
                      </div>

                      <button
                        onClick={() => setViewPermissionsUser(null)}
                        className={secondaryButtonClasses}
                      >
                        Close
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "roles" && (
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

            {activeTab === "permissions" && (
              <div>
                <div className="mb-6 space-y-6">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Custom User Permissions</h3>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Assign individual permissions to users in addition to their role permissions.
                    </p>
                  </div>

                  <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
                    <label className="mb-2 block text-sm font-medium text-gray-900 dark:text-white/90">Select User</label>
                    <select
                      value={selectedPermissionUser}
                      onChange={(e) => setSelectedPermissionUser(e.target.value)}
                      className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                    >
                      <option value="">-- Choose a user --</option>
                      {users.map((user) => (
                        <option key={user.id} value={user.id}>
                          {user.email}
                        </option>
                      ))}
                    </select>

                    {selectedPermissionUser && (
                      <div>
                        {(() => {
                          const user = users.find((u) => u.id === selectedPermissionUser);
                          if (!user) return null;
                          const rolePerms = getRolePermissions(user);
                          const userPerms = getUserPermissions(user.id);
                          return (
                            <div>
                              <div className="mb-4">
                                <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white/90">
                                  {user.email}
                                </h4>
                                <p className="mb-3 text-xs text-gray-600 dark:text-gray-400">
                                  Roles: {user.roles.length > 0 ? user.roles.map((r) => r.name).join(", ") : "None"}
                                </p>
                              </div>

                              <div className="space-y-2">
                                <h5 className="text-xs font-semibold uppercase tracking-wide text-gray-700 dark:text-gray-300">
                                  Available Permissions
                                </h5>
                                <div className="grid gap-3">
                                  {AVAILABLE_PERMISSIONS.map((perm) => {
                                    const hasPermission = userPerms.includes(perm.id);
                                    const fromRole = rolePerms.includes(perm.id);
                                    return (
                                      <div
                                        key={perm.id}
                                        className="flex items-start rounded-lg border border-gray-200 p-3 dark:border-gray-700"
                                      >
                                        <input
                                          type="checkbox"
                                          id={`perm-${perm.id}`}
                                          checked={hasPermission}
                                          onChange={() => toggleUserPermission(user.id, perm.id)}
                                          disabled={fromRole}
                                          className="mt-1 h-4 w-4 cursor-pointer rounded"
                                        />
                                        <label
                                          htmlFor={`perm-${perm.id}`}
                                          className="ml-3 flex-1 cursor-pointer"
                                        >
                                          <p className="text-sm font-medium text-gray-900 dark:text-white/90">
                                            {perm.label}
                                          </p>
                                          <p className="text-xs text-gray-600 dark:text-gray-400">
                                            {perm.description}
                                            {fromRole && (
                                              <span className="ml-2 inline-block rounded-full bg-blue-100 px-2 py-0.5 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                                                from role
                                              </span>
                                            )}
                                          </p>
                                        </label>
                                        {hasPermission && !fromRole && (
                                          <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                                            custom
                                          </span>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>

                              {userPerms.length > 0 && (
                                <div className="mt-4 rounded-lg bg-blue-50 p-3 dark:bg-blue-900/20">
                                  <p className="mb-2 text-xs font-semibold text-blue-900 dark:text-blue-200">
                                    Custom Permissions Assigned:
                                  </p>
                                  <div className="flex flex-wrap gap-2">
                                    {userPerms.map((permId) => {
                                      const perm = AVAILABLE_PERMISSIONS.find((p) => p.id === permId);
                                      return (
                                        <span
                                          key={permId}
                                          className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-1 text-xs font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                        >
                                          {perm?.label || permId}
                                        </span>
                                      );
                                    })}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>

                  <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
                    <h4 className="mb-3 text-sm font-semibold text-gray-900 dark:text-white/90">
                      Available Roles & Role Permissions
                    </h4>
                    <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">
                      These are the default permissions granted by each role:
                    </p>

                    <div className="space-y-3">
                      {roles.map((role) => (
                        <div key={role.id} className="rounded border border-gray-200 p-3 dark:border-gray-700">
                          <p className="font-mono text-sm font-semibold text-gray-900 dark:text-white/90">{role.name}</p>
                          <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                            {role.name === "admin"
                              ? "Full access to all features and settings. Can manage users and system configuration."
                              : role.name === "trader"
                              ? "Can monitor the bot, control execution, and review logs and reports."
                              : role.name === "viewer"
                              ? "Read-only access to dashboards and reports. Cannot modify any settings."
                              : "Custom role with limited permissions."}
                          </p>
                          <div className="mt-2 flex flex-wrap gap-1">
                            {getSavedRolePermissions(role).length > 0 ? (
                              getSavedRolePermissions(role).map((permId) => {
                                const perm = AVAILABLE_PERMISSIONS.find((row) => row.id === permId);
                                return (
                                  <span
                                    key={`${role.id}-summary-${permId}`}
                                    className="inline-flex items-center rounded-full bg-blue-100 px-2 py-1 text-xs font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                  >
                                    {perm?.label || permId}
                                  </span>
                                );
                              })
                            ) : (
                              <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-800 dark:bg-gray-900 dark:text-gray-200">
                                No permissions assigned
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </DashboardShell>
  );
}
