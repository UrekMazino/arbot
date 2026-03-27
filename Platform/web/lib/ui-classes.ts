/**
 * Global UI CSS class constants for reuse across pages
 * Ensures consistent styling across the application
 */

export const UI_CLASSES = {
  // Button styles
  primaryButton:
    "inline-flex items-center rounded-xl bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-70",
  secondaryButton:
    "inline-flex items-center rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-70 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700",

  // Card/Section styles
  sectionCard: "rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900",
} as const;
