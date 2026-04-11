"use client";

import { useEffect, useState } from "react";

type NotificationVariant = "success" | "danger" | "warning" | "info";

type NotificationProps = {
  variant?: NotificationVariant;
  title: string;
  message?: string;
  autoCloseDelay?: number;
  actionLabel?: string;
  onActionClick?: () => void;
  onClose: () => void;
};

const VARIANT_STYLES = {
  success: {
    bgColor: "bg-green-50 dark:bg-green-900/20",
    borderColor: "border-green-200 dark:border-green-800",
    iconBg: "bg-green-100 dark:bg-green-900/40",
    iconColor: "text-green-600 dark:text-green-400",
    actionColor: "bg-green-600 hover:bg-green-700 text-white",
  },
  danger: {
    bgColor: "bg-red-50 dark:bg-red-900/20",
    borderColor: "border-red-200 dark:border-red-800",
    iconBg: "bg-red-100 dark:bg-red-900/40",
    iconColor: "text-red-600 dark:text-red-400",
    actionColor: "bg-red-600 hover:bg-red-700 text-white",
  },
  warning: {
    bgColor: "bg-yellow-50 dark:bg-yellow-900/20",
    borderColor: "border-yellow-200 dark:border-yellow-800",
    iconBg: "bg-yellow-100 dark:bg-yellow-900/40",
    iconColor: "text-yellow-600 dark:text-yellow-400",
    actionColor: "bg-yellow-500 hover:bg-yellow-600 text-white",
  },
  info: {
    bgColor: "bg-blue-50 dark:bg-blue-900/20",
    borderColor: "border-blue-200 dark:border-blue-800",
    iconBg: "bg-blue-100 dark:bg-blue-900/40",
    iconColor: "text-blue-600 dark:text-blue-400",
    actionColor: "bg-brand-500 hover:bg-brand-600 text-white",
  },
};

const ICONS = {
  success: (
    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  danger: (
    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  warning: (
    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  ),
  info: (
    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
};

export function Notification({
  variant = "info",
  title,
  message,
  autoCloseDelay = 3000,
  actionLabel,
  onActionClick,
  onClose,
}: NotificationProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Trigger entrance animation
    setTimeout(() => setIsVisible(true), 10);
  }, []);

  useEffect(() => {
    if (autoCloseDelay > 0) {
      const timer = setTimeout(() => {
        setIsVisible(false);
        setTimeout(onClose, 300); // Wait for animation
      }, autoCloseDelay);
      return () => clearTimeout(timer);
    }
  }, [autoCloseDelay, onClose]);

  const style = VARIANT_STYLES[variant];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Backdrop */}
      <div
        className={`absolute inset-0 bg-gray-900/50 transition-opacity duration-300 ${isVisible ? "opacity-100" : "opacity-0"}`}
        onClick={onClose}
      />

      {/* Modal */}
      <div
        className={`relative w-full max-w-md transform transition-all duration-300 ${isVisible ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"}`}
      >
        <div
          className={`rounded-2xl border ${style.borderColor} ${style.bgColor} p-6 shadow-2xl`}
        >
          <div className="flex items-start gap-4">
            {/* Icon */}
            <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${style.iconBg}`}>
              <span className={style.iconColor}>{ICONS[variant]}</span>
            </div>

            {/* Content */}
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
              {message && (
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{message}</p>
              )}

              {/* Action button */}
              {actionLabel && onActionClick && (
                <div className="mt-4 flex justify-end">
                  <button
                    type="button"
                    onClick={onActionClick}
                    className={`inline-flex items-center rounded-xl px-4 py-2 text-sm font-medium ${style.actionColor}`}
                  >
                    {actionLabel}
                  </button>
                </div>
              )}
            </div>

            {/* Close button */}
            <button
              type="button"
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Hook for managing notification state
export function useNotification() {
  const [notification, setNotification] = useState<{
    open: boolean;
    variant: NotificationVariant;
    title: string;
    message?: string;
    autoCloseDelay?: number;
    actionLabel?: string;
    onActionClick?: () => void;
  }>({
    open: false,
    variant: "info",
    title: "",
    message: "",
    autoCloseDelay: 3000,
  });

  const showNotification = (params: {
    variant: NotificationVariant;
    title: string;
    message?: string;
    autoCloseDelay?: number;
    actionLabel?: string;
    onActionClick?: () => void;
  }) => {
    setNotification({ ...params, open: true });
  };

  const closeNotification = () => {
    setNotification((prev) => ({ ...prev, open: false }));
  };

  return {
    NotificationComponent: notification.open ? (
      <Notification
        variant={notification.variant}
        title={notification.title}
        message={notification.message}
        autoCloseDelay={notification.autoCloseDelay}
        actionLabel={notification.actionLabel}
        onActionClick={notification.onActionClick}
        onClose={closeNotification}
      />
    ) : null,
    showNotification,
    closeNotification,
  };
}