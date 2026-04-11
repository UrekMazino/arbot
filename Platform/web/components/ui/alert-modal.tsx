"use client";

import { useEffect, useState } from "react";
import { AppModal } from "./modal";

type AlertVariant = "success" | "danger" | "warning" | "info";

type AlertModalProps = {
  open: boolean;
  variant?: AlertVariant;
  title: string;
  message?: string;
  autoCloseDelay?: number; // milliseconds, 0 = no auto close
  onClose?: () => void;
};

const VARIANT_STYLES = {
  success: {
    iconBg: "bg-green-100 dark:bg-green-900/30",
    iconColor: "text-green-600 dark:text-green-400",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  danger: {
    iconBg: "bg-red-100 dark:bg-red-900/30",
    iconColor: "text-red-600 dark:text-red-400",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  warning: {
    iconBg: "bg-yellow-100 dark:bg-yellow-900/30",
    iconColor: "text-yellow-600 dark:text-yellow-400",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
  info: {
    iconBg: "bg-blue-100 dark:bg-blue-900/30",
    iconColor: "text-blue-600 dark:text-blue-400",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
};

export function AlertModal({ open, variant = "info", title, message, autoCloseDelay = 3000, onClose }: AlertModalProps) {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    setIsOpen(open);
  }, [open]);

  useEffect(() => {
    if (isOpen && autoCloseDelay > 0 && onClose) {
      const timer = setTimeout(() => {
        setIsOpen(false);
        onClose();
      }, autoCloseDelay);
      return () => clearTimeout(timer);
    }
  }, [isOpen, autoCloseDelay, onClose]);

  if (!isOpen) return null;

  const style = VARIANT_STYLES[variant];

  return (
    <AppModal
      open={isOpen}
      title=""
      size="sm"
      onClose={() => {
        setIsOpen(false);
        onClose?.();
      }}
    >
      <div className="flex items-center gap-4 py-2">
        <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full ${style.iconBg}`}>
          <span className={style.iconColor}>{style.icon}</span>
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
          {message && <p className="mt-1 text-base text-gray-600 dark:text-gray-400">{message}</p>}
        </div>
      </div>
    </AppModal>
  );
}

// Hook for managing alert state
export function useAlert() {
  const [alert, setAlert] = useState<{
    open: boolean;
    variant: AlertVariant;
    title: string;
    message?: string;
    autoCloseDelay?: number;
  }>({
    open: false,
    variant: "info",
    title: "",
    message: "",
    autoCloseDelay: 3000,
  });

  const showAlert = (params: {
    variant: AlertVariant;
    title: string;
    message?: string;
    autoCloseDelay?: number;
  }) => {
    setAlert({ ...params, open: true });
  };

  const closeAlert = () => {
    setAlert((prev) => ({ ...prev, open: false }));
  };

  return {
    AlertComponent: alert.open ? (
      <AlertModal
        open={alert.open}
        variant={alert.variant}
        title={alert.title}
        message={alert.message}
        autoCloseDelay={alert.autoCloseDelay}
        onClose={closeAlert}
      />
    ) : null,
    showAlert,
    closeAlert,
  };
}