"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { forgotPassword, getMe, login } from "../../lib/api";
import {
  defaultRememberMe,
  getStoredAdminAccessToken,
  persistAdminSession,
  setRememberMePreference,
} from "../../lib/auth";

export default function LoginPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(defaultRememberMe());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [nextPath, setNextPath] = useState("/admin/dashboard");
  const [showForgot, setShowForgot] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotBusy, setForgotBusy] = useState(false);
  const [forgotError, setForgotError] = useState("");
  const [forgotMessage, setForgotMessage] = useState("");
  const [devResetToken, setDevResetToken] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const raw = params.get("next") || "";
    if (raw.startsWith("/") && !raw.startsWith("//")) {
      setNextPath(raw);
    } else {
      setNextPath("/admin/dashboard");
    }
  }, []);

  useEffect(() => {
    const token = getStoredAdminAccessToken();
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
      persistAdminSession(pair.access_token, pair.refresh_token, rememberMe);
      router.replace(nextPath);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sign-in failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function onForgotSubmit(e: FormEvent) {
    e.preventDefault();
    setForgotBusy(true);
    setForgotError("");
    setForgotMessage("");
    setDevResetToken("");
    try {
      const response = await forgotPassword(forgotEmail);
      setForgotMessage(response.message || "If this account exists, a reset flow has been started.");
      if (response.reset_token) {
        setDevResetToken(response.reset_token);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to request password reset";
      setForgotError(msg);
    } finally {
      setForgotBusy(false);
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
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">ProjectY Trade Bot</p>
            <h1 className="mt-2 text-3xl font-semibold text-gray-900 dark:text-white/90">Sign In</h1>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Use your super admin credentials to access the control plane.</p>

            <form onSubmit={onSubmit} className="mt-8 grid gap-4">
              <label className="grid gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
                Email
                <input
                  className="rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-3 focus:ring-brand-500/15 dark:border-gray-700 dark:bg-gray-800 dark:text-white/90 dark:focus:border-brand-500"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                />
              </label>

              <label className="grid gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
                Password
                <div className="relative">
                  <input
                    className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2.5 pr-20 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-3 focus:ring-brand-500/15 dark:border-gray-700 dark:bg-gray-800 dark:text-white/90 dark:focus:border-brand-500"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 text-xs font-semibold text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                </div>
              </label>

              <div className="flex items-center justify-between gap-2">
                <label className="inline-flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-300">
                  <input
                    className="h-4 w-4 rounded border-gray-300 text-brand-500 focus:ring-brand-500/20 dark:border-gray-700 dark:bg-gray-800"
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => {
                      const next = e.target.checked;
                      setRememberMe(next);
                      setRememberMePreference(next);
                    }}
                  />
                  Keep me logged in
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setShowForgot((prev) => !prev);
                    setForgotEmail(email || forgotEmail);
                    setForgotError("");
                    setForgotMessage("");
                    setDevResetToken("");
                  }}
                  className="text-xs font-semibold text-brand-600 transition hover:text-brand-500 dark:text-brand-400 dark:hover:text-brand-300"
                >
                  Forgot password?
                </button>
              </div>

              <button
                type="submit"
                disabled={busy}
                className="mt-1 inline-flex items-center justify-center rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:opacity-70"
              >
                {busy ? "Signing in..." : "Sign In"}
              </button>
            </form>

            {error ? <p className="mt-4 text-sm text-error-600 dark:text-error-400">{error}</p> : null}

            {showForgot ? (
              <div className="mt-5 rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/40">
                <h2 className="text-sm font-semibold text-gray-900 dark:text-white/90">Forgot password</h2>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Enter your admin email and we will send you a reset link.
                </p>

                <form onSubmit={onForgotSubmit} className="mt-3 grid gap-2">
                  <label className="grid gap-1 text-xs font-medium text-gray-700 dark:text-gray-300">
                    Account email
                    <input
                      className="rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-3 focus:ring-brand-500/15 dark:border-gray-700 dark:bg-gray-800 dark:text-white/90 dark:focus:border-brand-500"
                      type="email"
                      value={forgotEmail}
                      onChange={(e) => setForgotEmail(e.target.value)}
                      required
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={forgotBusy}
                    className="inline-flex items-center justify-center rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-sm font-semibold text-brand-700 transition hover:bg-brand-100 disabled:opacity-70 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300 dark:hover:bg-brand-950/40"
                  >
                    {forgotBusy ? "Requesting..." : "Request Reset Token"}
                  </button>
                </form>

                {forgotError ? <p className="mt-2 text-xs text-error-600 dark:text-error-400">{forgotError}</p> : null}
                {forgotMessage ? <p className="mt-2 text-xs text-success-700 dark:text-success-400">{forgotMessage}</p> : null}
                {devResetToken ? (
                  <p className="mt-2 text-xs text-warning-700 dark:text-warning-400">
                    Dev fallback token issued. Continue here:{" "}
                    <Link
                      href={`/reset-password?token=${encodeURIComponent(devResetToken)}`}
                      className="font-semibold text-brand-600 underline dark:text-brand-300"
                    >
                      Open reset page
                    </Link>
                  </p>
                ) : null}
              </div>
            ) : null}

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
