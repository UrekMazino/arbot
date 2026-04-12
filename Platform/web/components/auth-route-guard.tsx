"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { getMe } from "../lib/api";
import { clearStoredAdminSession } from "../lib/auth";
import { FloatingTerminal } from "./floating-terminal";

const PUBLIC_PATHS = new Set<string>(["/login", "/reset-password"]);

type SessionState = "checking" | "authenticated" | "unauthenticated";
type SessionCheck = {
  path: string;
  state: Exclude<SessionState, "checking">;
};

export function AuthRouteGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [sessionCheck, setSessionCheck] = useState<SessionCheck | null>(null);

  const isPublicPath = useMemo(() => PUBLIC_PATHS.has(pathname), [pathname]);
  const sessionState: SessionState = isPublicPath
    ? "authenticated"
    : sessionCheck?.path === pathname
      ? sessionCheck.state
      : "checking";

  useEffect(() => {
    let cancelled = false;

    if (isPublicPath) {
      return () => {
        cancelled = true;
      };
    }

    getMe()
      .then(() => {
        if (!cancelled) {
          setSessionCheck({ path: pathname, state: "authenticated" });
        }
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        clearStoredAdminSession();
        setSessionCheck({ path: pathname, state: "unauthenticated" });
        const next = `${window.location.pathname}${window.location.search}`;
        router.replace(`/login?next=${encodeURIComponent(next)}`);
      });

    return () => {
      cancelled = true;
    };
  }, [isPublicPath, pathname, router]);

  if (isPublicPath) {
    return <>{children}</>;
  }

  if (sessionState !== "authenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {sessionState === "checking" ? "Restoring session..." : "Redirecting to login..."}
        </p>
      </div>
    );
  }

  return (
    <>
      {children}
      <FloatingTerminal />
    </>
  );
}
