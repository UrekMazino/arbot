"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getMe, login } from "../../lib/api";
import { ADMIN_ACCESS_TOKEN_KEY, ADMIN_REFRESH_TOKEN_KEY } from "../../lib/auth";

export default function LoginPage() {
  const router = useRouter();

  const [email, setEmail] = useState("admin@okxstatbot.dev");
  const [password, setPassword] = useState("ChangeMeNow123!");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [nextPath, setNextPath] = useState("/admin");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const raw = params.get("next") || "";
    if (raw.startsWith("/") && !raw.startsWith("//")) {
      setNextPath(raw);
    } else {
      setNextPath("/admin");
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem(ADMIN_ACCESS_TOKEN_KEY) || "";
    if (token) {
      router.replace(nextPath);
    }
  }, [router, nextPath]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const pair = await login(email, password);
      const me = await getMe(pair.access_token);
      if (!me.is_superuser) {
        setError("This account is not a super admin account.");
        return;
      }
      localStorage.setItem(ADMIN_ACCESS_TOKEN_KEY, pair.access_token);
      localStorage.setItem(ADMIN_REFRESH_TOKEN_KEY, pair.refresh_token);
      // Keep analytics page compatibility while moving to shared admin auth.
      localStorage.setItem("v2_access_token", pair.access_token);
      localStorage.setItem("v2_refresh_token", pair.refresh_token);
      router.replace(nextPath);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sign-in failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-gray-50 p-4 dark:bg-gray-900 md:p-8">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-24 -left-24 h-72 w-72 rounded-full bg-brand-200/45 blur-3xl dark:bg-brand-500/25" />
        <div className="absolute right-0 bottom-0 h-80 w-80 rounded-full bg-blue-light-200/45 blur-3xl dark:bg-blue-light-500/15" />
      </div>

      <div className="relative mx-auto flex min-h-[calc(100vh-2rem)] w-full max-w-[1100px] items-center md:min-h-[calc(100vh-4rem)]">
        <div className="grid w-full overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-xl dark:border-gray-800 dark:bg-gray-900 lg:grid-cols-2">
          <section className="p-6 md:p-10">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">TailAdmin Sign In</p>
            <h1 className="mt-2 text-3xl font-semibold text-gray-900 dark:text-white/90">Admin Login</h1>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Use your super admin credentials to access the control plane.</p>

            <form onSubmit={onSubmit} className="mt-8 grid gap-4">
              <label className="grid gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
                Email
                <input
                  className="rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-3 focus:ring-brand-500/15 dark:border-gray-700 dark:bg-gray-800 dark:text-white/90 dark:focus:border-brand-500"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@okxstatbot.dev"
                  required
                />
              </label>

              <label className="grid gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
                Password
                <input
                  className="rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-3 focus:ring-brand-500/15 dark:border-gray-700 dark:bg-gray-800 dark:text-white/90 dark:focus:border-brand-500"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                />
              </label>

              <button
                type="submit"
                disabled={busy}
                className="mt-1 inline-flex items-center justify-center rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:opacity-70"
              >
                {busy ? "Signing in..." : "Sign In"}
              </button>
            </form>

            {error ? <p className="mt-4 text-sm text-error-600 dark:text-error-400">{error}</p> : null}

            <p className="mt-6 text-xs text-gray-500 dark:text-gray-400">
              Only super admin users are allowed for this login route.
            </p>
          </section>

          <aside className="relative hidden overflow-hidden bg-gray-900 lg:flex">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(70,95,255,0.45),transparent_50%),radial-gradient(circle_at_bottom_left,rgba(11,165,236,0.35),transparent_45%)]" />
            <div className="relative flex h-full w-full flex-col justify-between p-10">
              <div>
                <span className="inline-flex rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-white/90">
                  OKXStatBot
                </span>
                <h2 className="mt-4 text-3xl font-semibold leading-tight text-white">
                  Secure Access for Super Admin Control
                </h2>
                <p className="mt-3 max-w-sm text-sm text-white/75">
                  Start and stop bots, inspect live logs, and manage users from one secured control console.
                </p>
              </div>

              <div className="space-y-3 text-sm text-white/80">
                <div className="rounded-xl border border-white/20 bg-white/10 p-3">Live process controls and terminal tail</div>
                <div className="rounded-xl border border-white/20 bg-white/10 p-3">Role and permission management</div>
                <div className="rounded-xl border border-white/20 bg-white/10 p-3">Runtime env settings with audit visibility</div>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
