"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { resetPassword } from "../../lib/api";

export default function ResetPasswordPage() {
  const router = useRouter();

  const [resetToken, setResetToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = (params.get("token") || "").trim();
    if (token) {
      setResetToken(token);
    }
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");

    const token = resetToken.trim();
    if (!token) {
      setError("Reset token is required.");
      return;
    }
    if (password.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Password confirmation does not match.");
      return;
    }

    setBusy(true);
    try {
      const response = await resetPassword(token, password);
      setMessage(response.message || "Password updated successfully.");
      setPassword("");
      setConfirmPassword("");
      setTimeout(() => {
        router.replace("/login");
      }, 1200);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to reset password";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-gray-50 p-4 dark:bg-gray-900 md:p-8">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-20 -left-20 h-72 w-72 rounded-full bg-brand-200/40 blur-3xl dark:bg-brand-500/20" />
        <div className="absolute right-0 bottom-0 h-80 w-80 rounded-full bg-blue-light-200/40 blur-3xl dark:bg-blue-light-500/15" />
      </div>

      <div className="relative mx-auto flex min-h-[calc(100vh-2rem)] w-full max-w-[620px] items-center md:min-h-[calc(100vh-4rem)]">
        <div className="w-full rounded-3xl border border-gray-200 bg-white p-6 shadow-xl dark:border-gray-800 dark:bg-gray-900 md:p-8">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">TailAdmin Security</p>
          <h1 className="mt-2 text-3xl font-semibold text-gray-900 dark:text-white/90">Reset Password</h1>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            Set a new password for your admin account.
          </p>

          <form onSubmit={onSubmit} className="mt-7 grid gap-4">
            <label className="grid gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
              Reset token
              <input
                className="rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-3 focus:ring-brand-500/15 dark:border-gray-700 dark:bg-gray-800 dark:text-white/90 dark:focus:border-brand-500"
                value={resetToken}
                onChange={(e) => setResetToken(e.target.value)}
                placeholder="Paste token from email link if needed"
                required
              />
            </label>

            <label className="grid gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
              New password
              <input
                className="rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-3 focus:ring-brand-500/15 dark:border-gray-700 dark:bg-gray-800 dark:text-white/90 dark:focus:border-brand-500"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                placeholder="At least 8 characters"
                required
              />
            </label>

            <label className="grid gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
              Confirm new password
              <input
                className="rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-3 focus:ring-brand-500/15 dark:border-gray-700 dark:bg-gray-800 dark:text-white/90 dark:focus:border-brand-500"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={8}
                placeholder="Repeat new password"
                required
              />
            </label>

            <button
              type="submit"
              disabled={busy}
              className="mt-1 inline-flex items-center justify-center rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:opacity-70"
            >
              {busy ? "Updating..." : "Update Password"}
            </button>
          </form>

          {error ? <p className="mt-4 text-sm text-error-600 dark:text-error-400">{error}</p> : null}
          {message ? <p className="mt-4 text-sm text-success-700 dark:text-success-400">{message}</p> : null}

          <p className="mt-6 text-xs text-gray-500 dark:text-gray-400">
            Remembered your password?{" "}
            <Link href="/login" className="font-semibold text-brand-600 underline dark:text-brand-300">
              Back to login
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
