"use client";

import { useState } from "react";
import { AppModal } from "./modal";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "warning" | "info";
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "danger",
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const [loading, setLoading] = useState(false);

  const handleConfirm = async () => {
    setLoading(true);
    try {
      await Promise.resolve(onConfirm());
    } finally {
      setLoading(false);
    }
  };

  const buttonClass =
    variant === "danger"
      ? "bg-red-600 hover:bg-red-700 text-white"
      : variant === "warning"
        ? "bg-yellow-500 hover:bg-yellow-600 text-white"
        : "bg-brand-500 hover:bg-brand-600 text-white";

  return (
    <AppModal
      open={open}
      title={title}
      size="sm"
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={loading}
            className={`inline-flex items-center rounded-xl px-4 py-2 text-sm font-medium text-white ${buttonClass} disabled:opacity-70`}
          >
            {loading ? "Processing..." : confirmLabel}
          </button>
        </div>
      }
    >
      <p className="text-gray-600 dark:text-gray-400">{description}</p>
    </AppModal>
  );
}

// Hook for managing confirm dialog state
export function useConfirmDialog() {
  const [config, setConfig] = useState<{
    open: boolean;
    title: string;
    description?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    variant?: "danger" | "warning" | "info";
    onConfirm: () => void | Promise<void>;
  } | null>(null);

  const confirm = (params: {
    title: string;
    description?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    variant?: "danger" | "warning" | "info";
    onConfirm: () => void | Promise<void>;
  }) => {
    setConfig({ ...params, open: true });
  };

  const close = () => {
    setConfig(null);
  };

  return {
    ConfirmDialogComponent: config ? (
      <ConfirmDialog
        open={config.open}
        title={config.title}
        description={config.description}
        confirmLabel={config.confirmLabel}
        cancelLabel={config.cancelLabel}
        variant={config.variant}
        onConfirm={async () => {
          try {
            await Promise.resolve(config.onConfirm());
          } finally {
            close();
          }
        }}
        onClose={close}
      />
    ) : null,
    confirm,
    close,
  };
}
