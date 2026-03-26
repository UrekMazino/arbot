export const ADMIN_ACCESS_TOKEN_KEY = "v2_admin_access_token";
export const ADMIN_REFRESH_TOKEN_KEY = "v2_admin_refresh_token";
export const LEGACY_ACCESS_TOKEN_KEY = "v2_access_token";
export const LEGACY_REFRESH_TOKEN_KEY = "v2_refresh_token";
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

function readStorageKey(key: string): string {
  if (!inBrowser()) {
    return "";
  }
  return localStorage.getItem(key) || sessionStorage.getItem(key) || "";
}

function setTokenPair(target: Storage, accessToken: string, refreshToken: string): void {
  target.setItem(ADMIN_ACCESS_TOKEN_KEY, accessToken);
  target.setItem(ADMIN_REFRESH_TOKEN_KEY, refreshToken);
  target.setItem(LEGACY_ACCESS_TOKEN_KEY, accessToken);
  target.setItem(LEGACY_REFRESH_TOKEN_KEY, refreshToken);
}

function clearTokenPair(target: Storage): void {
  target.removeItem(ADMIN_ACCESS_TOKEN_KEY);
  target.removeItem(ADMIN_REFRESH_TOKEN_KEY);
  target.removeItem(LEGACY_ACCESS_TOKEN_KEY);
  target.removeItem(LEGACY_REFRESH_TOKEN_KEY);
}

export function persistAdminSession(accessToken: string, refreshToken: string, rememberMe: boolean, email?: string): void {
  if (!inBrowser()) {
    return;
  }
  clearTokenPair(localStorage);
  clearTokenPair(sessionStorage);
  const storage = rememberMe ? localStorage : sessionStorage;
  setTokenPair(storage, accessToken, refreshToken);
  localStorage.setItem(ADMIN_REMEMBER_ME_KEY, rememberMe ? "1" : "0");
  if (email) {
    storage.setItem(ADMIN_EMAIL_KEY, email);
  }
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
  clearTokenPair(localStorage);
  clearTokenPair(sessionStorage);
  notifyAuthStorageChange();
}

export function getStoredAdminAccessToken(): string {
  return readStorageKey(ADMIN_ACCESS_TOKEN_KEY) || readStorageKey(LEGACY_ACCESS_TOKEN_KEY);
}

export function getStoredAdminRefreshToken(): string {
  return readStorageKey(ADMIN_REFRESH_TOKEN_KEY) || readStorageKey(LEGACY_REFRESH_TOKEN_KEY);
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
