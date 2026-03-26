"use client";

import { useEffect, useMemo } from "react";
import { usePathname, useRouter } from "next/navigation";

import { getStoredAdminAccessToken } from "../lib/auth";

const PUBLIC_PATHS = new Set<string>(["/login", "/reset-password"]);

export function AuthRouteGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const isPublicPath = useMemo(() => PUBLIC_PATHS.has(pathname), [pathname]);
  const hasToken = typeof window !== "undefined" ? Boolean(getStoredAdminAccessToken()) : false;
  const shouldRedirect = !isPublicPath && !hasToken;

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

  if (typeof window === "undefined" || shouldRedirect) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">Redirecting to login...</p>
      </div>
    );
  }

  return <>{children}</>;
}
