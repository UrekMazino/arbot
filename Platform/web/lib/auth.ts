export const ADMIN_REMEMBER_ME_KEY = "v2_admin_remember_me";
export const ADMIN_EMAIL_KEY = "v2_admin_email";
export const AUTH_STORAGE_EVENT = "v2_auth_storage_change";

function inBrowser(): boolean {
  return typeof window !== "undefined";
}

function notifyAuthStorageChange(): void {
  if (!inBrowser()) {
    return;
  }
  window.dispatchEvent(new Event(AUTH_STORAGE_EVENT));
}

export function persistAdminSession(rememberMe: boolean, email?: string): void {
  if (!inBrowser()) {
    return;
  }

  if (email) {
    const storage = rememberMe ? localStorage : sessionStorage;
    storage.setItem(ADMIN_EMAIL_KEY, email);
  } else {
    localStorage.removeItem(ADMIN_EMAIL_KEY);
    sessionStorage.removeItem(ADMIN_EMAIL_KEY);
  }

  localStorage.setItem(ADMIN_REMEMBER_ME_KEY, rememberMe ? "1" : "0");
  notifyAuthStorageChange();
}

export function getStoredAdminEmail(): string {
  if (!inBrowser()) {
    return "";
  }
  return localStorage.getItem(ADMIN_EMAIL_KEY) || sessionStorage.getItem(ADMIN_EMAIL_KEY) || "";
}

export function clearStoredAdminSession(): void {
  if (!inBrowser()) {
    return;
  }
  localStorage.removeItem(ADMIN_EMAIL_KEY);
  sessionStorage.removeItem(ADMIN_EMAIL_KEY);
  notifyAuthStorageChange();
}

export function defaultRememberMe(): boolean {
  if (!inBrowser()) {
    return true;
  }
  return localStorage.getItem(ADMIN_REMEMBER_ME_KEY) !== "0";
}

export function setRememberMePreference(rememberMe: boolean): void {
  if (!inBrowser()) {
    return;
  }
  localStorage.setItem(ADMIN_REMEMBER_ME_KEY, rememberMe ? "1" : "0");
}
