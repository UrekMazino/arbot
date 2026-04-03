"use client";

import { ReactNode } from "react";

type ModalSize = "sm" | "md" | "lg" | "xl";

type AppModalProps = {
  open: boolean;
  title: string;
  description?: string;
  size?: ModalSize;
  footer?: ReactNode;
  onClose: () => void;
  children: ReactNode;
};

const SIZE_CLASSES: Record<ModalSize, string> = {
  sm: "max-w-md",
  md: "max-w-2xl",
  lg: "max-w-4xl",
  xl: "max-w-6xl",
};

export function AppModal({
  open,
  title,
  description,
  size = "md",
  footer,
  onClose,
  children,
}: AppModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-gray-900/70 px-4 py-6 backdrop-blur-sm sm:px-6"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div className="flex min-h-full items-center justify-center">
        <div
          className={`relative w-full ${SIZE_CLASSES[size]} overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-2xl dark:border-gray-800 dark:bg-gray-900`}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="border-b border-gray-200 px-5 py-4 dark:border-gray-800 sm:px-6">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white/90">{title}</h3>
                {description ? <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description}</p> : null}
              </div>
              <button
                type="button"
                onClick={onClose}
                className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-gray-200 text-gray-500 transition hover:bg-gray-50 hover:text-gray-700 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
                aria-label="Close dialog"
              >
                <svg className="h-5 w-5" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path d="M15 5L5 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                  <path d="M5 5L15 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          </div>

          <div className="px-5 py-5 sm:px-6">{children}</div>

          {footer ? <div className="border-t border-gray-200 px-5 py-4 dark:border-gray-800 sm:px-6">{footer}</div> : null}
        </div>
      </div>
    </div>
  );
}
