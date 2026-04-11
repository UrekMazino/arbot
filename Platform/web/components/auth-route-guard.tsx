"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";

import { AUTH_STORAGE_EVENT, getStoredAdminEmail } from "../lib/auth";

const PUBLIC_PATHS = new Set<string>(["/login", "/reset-password"]);

function subscribeTokenStore(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const handler = () => onStoreChange();
  window.addEventListener("storage", handler);
  window.addEventListener(AUTH_STORAGE_EVENT, handler);
  return () => {
    window.removeEventListener("storage", handler);
    window.removeEventListener(AUTH_STORAGE_EVENT, handler);
  };
}

function readTokenSnapshot(): boolean {
  return Boolean(getStoredAdminEmail());
}

function readHydratedSnapshot(): boolean {
  return true;
}

function readServerHydratedSnapshot(): boolean {
  return false;
}

export function AuthRouteGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const hasToken = useSyncExternalStore<boolean>(subscribeTokenStore, readTokenSnapshot, () => false);
  const hydrated = useSyncExternalStore<boolean>(() => () => undefined, readHydratedSnapshot, readServerHydratedSnapshot);

  const isPublicPath = useMemo(() => PUBLIC_PATHS.has(pathname), [pathname]);
  const shouldRedirect = hydrated && !isPublicPath && !hasToken;

  useEffect(() => {
    if (!shouldRedirect) {
      return;
    }
    const next = `${window.location.pathname}${window.location.search}`;
    router.replace(`/login?next=${encodeURIComponent(next)}`);
  }, [pathname, router, shouldRedirect]);

  if (isPublicPath) {
    return <>{children}</>;
  }

  if (!hydrated || shouldRedirect) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">Redirecting to login...</p>
      </div>
    );
  }

  return <>{children}</>;
}
