"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  RoleRecord,
  UserRecord,
  assignUserRole,
  createRole,
  createUser,
  deleteRole,
  getMe,
  getRolePermissions,
  isUnauthorizedError,
  listRoles,
  listUsers,
  removeUserRole,
  setRolePermissions,
  updateRole,
} from "../../../lib/api";
import { clearStoredAdminSession, getStoredAdminAccessToken, getStoredAdminEmail } from "../../../lib/auth";
import { UI_CLASSES } from "../../../lib/ui-classes";
import { AVAILABLE_PERMISSIONS, ROLE_PERMISSIONS } from "../../../lib/permissions";
import { DashboardShell } from "../../../components/dashboard-shell";
import { TableFrame } from "../../../components/panels";

type TabType = "users" | "roles" | "permissions";

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
  const [newUserSuper, setNewUserSuper] = useState(false);
  const [roleTargetUser, setRoleTargetUser] = useState("");
  const [roleName, setRoleName] = useState("viewer");
  const [userPermissionsMap, setUserPermissionsMap] = useState<Record<string, string[]>>({});
  const [selectedPermissionUser, setSelectedPermissionUser] = useState("");

  // Role CRUD state
  const [newRoleName, setNewRoleName] = useState("");
  const [newRoleDescription, setNewRoleDescription] = useState("");
  const [editingRoleId, setEditingRoleId] = useState<string | null>(null);
  const [editingRoleName, setEditingRoleName] = useState("");
  const [editingRoleDescription, setEditingRoleDescription] = useState("");
  const [selectedRoleForPermissions, setSelectedRoleForPermissions] = useState<string | null>(null);
  const [rolePermissionsMap, setRolePermissionsMap] = useState<Record<string, string[]>>({});

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
      const [meData, usersData, rolesData] = await Promise.all([
        getMe(authToken),
        listUsers(authToken),
        listRoles(authToken),
      ]);
      setMe(meData);
      setUsers(usersData);
      setRoles(rolesData);
      if (!roleTargetUser && usersData.length > 0) {
        setRoleTargetUser(usersData[0].id);
      }
    },
    [roleTargetUser],
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
        is_superuser: newUserSuper,
      });
      setNewUserEmail("");
      setNewUserPassword("");
      setNewUserSuper(false);
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

  async function handleAssignRole(e: FormEvent) {
    e.preventDefault();
    if (!token || !roleTargetUser || !roleName) return;

    setBusy(true);
    setError("");
    try {
      await assignUserRole(token, roleTargetUser, roleName);
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

  async function handleCreateRole(e: FormEvent) {
    e.preventDefault();
    if (!token || !newRoleName) return;

    setBusy(true);
    setError("");
    try {
      await createRole(token, {
        name: newRoleName,
        description: newRoleDescription,
      });
      setNewRoleName("");
      setNewRoleDescription("");
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
      });
      setEditingRoleId(null);
      setEditingRoleName("");
      setEditingRoleDescription("");
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

  async function handleDeleteRole(roleName: string) {
    if (!token || !confirm(`Are you sure you want to delete the role "${roleName}"?`)) return;

    setBusy(true);
    setError("");
    try {
      await deleteRole(token, roleName);
      if (selectedRoleForPermissions === roleName) {
        setSelectedRoleForPermissions(null);
      }
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

  async function handleToggleRolePermission(roleName: string, permissionId: string) {
    if (!token) return;

    setBusy(true);
    setError("");
    try {
      const currentPerms = rolePermissionsMap[roleName] || [];
      const updated = currentPerms.includes(permissionId)
        ? currentPerms.filter((p) => p !== permissionId)
        : [...currentPerms, permissionId];

      await setRolePermissions(token, roleName, updated);
      setRolePermissionsMap((prev) => ({ ...prev, [roleName]: updated }));
      setStatus("Role permissions updated");
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Update role permissions failed";
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
        const { [userId]: _, ...rest } = prev;
        return rest;
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
      const permsForRole = ROLE_PERMISSIONS[role.name];
      if (permsForRole) {
        rolePerms.push(...permsForRole);
      }
    });
    return [...new Set(rolePerms)];
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

  if (me && !me.is_superuser) {
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
            <p className="mt-2 text-sm text-error-600 dark:text-error-400">Current account is not superuser.</p>
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
                <form onSubmit={handleCreateUser} className="mb-6 flex flex-wrap items-center gap-2">
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
                  <label className="inline-flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    <input
                      className="h-4 w-4 min-w-0"
                      type="checkbox"
                      checked={newUserSuper}
                      onChange={(e) => setNewUserSuper(e.target.checked)}
                    />
                    superuser
                  </label>
                  <button type="submit" disabled={busy} className={primaryButtonClasses}>
                    Create User
                  </button>
                </form>

                <TableFrame compact>
                  <table>
                    <thead>
                      <tr>
                        <th>Email</th>
                        <th>Active</th>
                        <th>Super</th>
                        <th>Roles</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((user) => (
                        <tr key={user.id}>
                          <td>{user.email}</td>
                          <td>{user.is_active ? "yes" : "no"}</td>
                          <td>{user.is_superuser ? "yes" : "no"}</td>
                          <td>
                            <div className="flex flex-wrap items-center gap-1.5">
                              {user.roles.map((role) => (
                                <button
                                  key={`${user.id}-${role.name}`}
                                  className="inline-flex items-center rounded-full border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                                  onClick={() => handleRemoveRole(user.id, role.name)}
                                  disabled={busy}
                                >
                                  {role.name} x
                                </button>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {!users.length ? (
                        <tr>
                          <td colSpan={4} className="text-sm text-gray-500 dark:text-gray-400">
                            No users found.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </TableFrame>
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
                      placeholder="Role name (e.g., editor, analyst)"
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
                    <div className="flex gap-2">
                      <button type="submit" disabled={busy} className={primaryButtonClasses}>
                        {editingRoleId ? "Update Role" : "Create Role"}
                      </button>
                      {editingRoleId && (
                        <button
                          type="button"
                          onClick={() => {
                            setEditingRoleId(null);
                            setEditingRoleName("");
                            setEditingRoleDescription("");
                          }}
                          className={secondaryButtonClasses}
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                  </form>
                </div>

                {/* Assign Role to User Section */}
                <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
                  <h4 className="mb-4 text-sm font-semibold text-gray-900 dark:text-white/90">Assign Role to User</h4>
                  <form onSubmit={handleAssignRole} className="flex flex-wrap items-center gap-2">
                    <select
                      value={roleTargetUser}
                      onChange={(e) => setRoleTargetUser(e.target.value)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                    >
                      <option value="">-- Select User --</option>
                      {users.map((user) => (
                        <option key={user.id} value={user.id}>
                          {user.email}
                        </option>
                      ))}
                    </select>
                    <select
                      value={roleName}
                      onChange={(e) => setRoleName(e.target.value)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                    >
                      <option value="">-- Select Role --</option>
                      {roles.map((role) => (
                        <option key={role.id} value={role.name}>
                          {role.name}
                        </option>
                      ))}
                    </select>
                    <button type="submit" disabled={busy} className={primaryButtonClasses}>
                      Assign Role
                    </button>
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
                              <td className="text-xs text-gray-600 dark:text-gray-400">
                                {role.description || "—"}
                              </td>
                              <td>
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => {
                                      setEditingRoleId(role.id);
                                      setEditingRoleName(role.name);
                                      setEditingRoleDescription(role.description || "");
                                    }}
                                    className="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                                    disabled={busy}
                                  >
                                    Edit
                                  </button>
                                  <button
                                    onClick={() => {
                                      setSelectedRoleForPermissions(role.name);
                                    }}
                                    className="text-xs text-purple-600 hover:text-purple-700 dark:text-purple-400 dark:hover:text-purple-300"
                                  >
                                    Permissions
                                  </button>
                                  {role.name !== "admin" && role.name !== "editor" && role.name !== "viewer" && (
                                    <button
                                      onClick={() => handleDeleteRole(role.name)}
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
                            <td colSpan={4} className="text-sm text-gray-500 dark:text-gray-400">
                              No roles found.
                            </td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </TableFrame>
                </div>

                {/* Role Permissions Management */}
                {selectedRoleForPermissions && (
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-900/20">
                    <div className="mb-4 flex items-center justify-between">
                      <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-200">
                        Manage Permissions for "{selectedRoleForPermissions}"
                      </h4>
                      <button
                        onClick={() => setSelectedRoleForPermissions(null)}
                        className="text-blue-600 hover:text-blue-700 dark:text-blue-400"
                      >
                        ✕
                      </button>
                    </div>

                    <div className="space-y-2">
                      {AVAILABLE_PERMISSIONS.map((perm) => {
                        const rolePerms = rolePermissionsMap[selectedRoleForPermissions] || [];
                        const hasPermission = rolePerms.includes(perm.id);
                        return (
                          <label
                            key={perm.id}
                            className="flex items-start gap-3 rounded border border-blue-200 p-3 dark:border-blue-800"
                          >
                            <input
                              type="checkbox"
                              checked={hasPermission}
                              onChange={() =>
                                handleToggleRolePermission(selectedRoleForPermissions, perm.id)
                              }
                              disabled={busy}
                              className="mt-1 h-4 w-4 cursor-pointer rounded"
                            />
                            <div className="flex-1">
                              <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                                {perm.label}
                              </p>
                              <p className="text-xs text-blue-700 dark:text-blue-300">
                                {perm.description}
                              </p>
                            </div>
                          </label>
                        );
                      })}
                    </div>

                    {(rolePermissionsMap[selectedRoleForPermissions] || []).length > 0 && (
                      <div className="mt-4 rounded bg-blue-100 p-3 dark:bg-blue-900">
                        <p className="mb-2 text-xs font-semibold text-blue-900 dark:text-blue-200">
                          Assigned Permissions:
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {(rolePermissionsMap[selectedRoleForPermissions] || []).map((permId) => {
                            const perm = AVAILABLE_PERMISSIONS.find((p) => p.id === permId);
                            return (
                              <span
                                key={permId}
                                className="inline-flex items-center rounded-full bg-blue-200 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-800 dark:text-blue-200"
                              >
                                {perm?.label || permId}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}
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
                              : role.name === "editor"
                              ? "Can create, edit, and manage content. Can view reports and analytics."
                              : role.name === "viewer"
                              ? "Read-only access to dashboards and reports. Cannot modify any settings."
                              : "Custom role with limited permissions."}
                          </p>
                          <div className="mt-2 flex flex-wrap gap-1">
                            {role.name === "admin" && (
                              <>
                                <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-1 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                                  Full Access
                                </span>
                                <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-1 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                                  User Management
                                </span>
                                <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-1 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                                  System Config
                                </span>
                              </>
                            )}
                            {role.name === "editor" && (
                              <>
                                <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-1 text-xs font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                                  Content Management
                                </span>
                                <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-1 text-xs font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                                  View Reports
                                </span>
                              </>
                            )}
                            {role.name === "viewer" && (
                              <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-800 dark:bg-gray-900 dark:text-gray-200">
                                Read-Only Access
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
