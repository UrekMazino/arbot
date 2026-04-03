"use client";

export type SidebarIconName = "dashboard" | "console" | "settings" | "access";

type SidebarIconProps = {
  name?: SidebarIconName;
  className?: string;
};

function iconClassName(className?: string): string {
  return className || "h-[18px] w-[18px]";
}

export function SidebarIcon({ name = "dashboard", className }: SidebarIconProps) {
  const iconProps = {
    className: iconClassName(className),
    viewBox: "0 0 24 24",
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg",
    "aria-hidden": true,
  } as const;

  switch (name) {
    case "console":
      return (
        <svg {...iconProps}>
          <path
            d="M4.75 6.75C4.75 5.64543 5.64543 4.75 6.75 4.75H17.25C18.3546 4.75 19.25 5.64543 19.25 6.75V17.25C19.25 18.3546 18.3546 19.25 17.25 19.25H6.75C5.64543 19.25 4.75 18.3546 4.75 17.25V6.75Z"
            stroke="currentColor"
            strokeWidth="1.7"
          />
          <path d="M8.5 10L10.75 12L8.5 14" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M12.75 14H15.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      );
    case "settings":
      return (
        <svg {...iconProps}>
          <path
            d="M12 8.25C9.92893 8.25 8.25 9.92893 8.25 12C8.25 14.0711 9.92893 15.75 12 15.75C14.0711 15.75 15.75 14.0711 15.75 12C15.75 9.92893 14.0711 8.25 12 8.25Z"
            stroke="currentColor"
            strokeWidth="1.7"
          />
          <path
            d="M19.25 13.176V10.824C19.25 10.4971 19.0439 10.2061 18.7353 10.0974L17.5219 9.67026C17.3263 9.11957 17.0344 8.61303 16.6638 8.17258L16.9241 6.91366C16.9901 6.59464 16.8634 6.2672 16.5982 6.07835L14.7082 4.73251C14.4431 4.54367 14.0918 4.53463 13.8172 4.70961L12.7317 5.40163C12.2434 5.30798 11.7566 5.30798 11.2683 5.40163L10.1828 4.70961C9.90824 4.53463 9.55695 4.54367 9.29184 4.73251L7.40177 6.07835C7.13665 6.2672 7.00993 6.59464 7.07587 6.91366L7.33616 8.17258C6.96562 8.61303 6.67375 9.11957 6.47808 9.67026L5.26474 10.0974C4.95611 10.2061 4.75 10.4971 4.75 10.824V13.176C4.75 13.5029 4.95611 13.7939 5.26474 13.9026L6.47808 14.3297C6.67375 14.8804 6.96562 15.387 7.33616 15.8274L7.07587 17.0863C7.00993 17.4054 7.13665 17.7328 7.40177 17.9216L9.29184 19.2675C9.55695 19.4563 9.90824 19.4654 10.1828 19.2904L11.2683 18.5984C11.7566 18.692 12.2434 18.692 12.7317 18.5984L13.8172 19.2904C14.0918 19.4654 14.4431 19.4563 14.7082 19.2675L16.5982 17.9216C16.8634 17.7328 16.9901 17.4054 16.9241 17.0863L16.6638 15.8274C17.0344 15.387 17.3263 14.8804 17.5219 14.3297L18.7353 13.9026C19.0439 13.7939 19.25 13.5029 19.25 13.176Z"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "access":
      return (
        <svg {...iconProps}>
          <path
            d="M15.5 7.5C15.5 9.15685 14.1569 10.5 12.5 10.5C10.8431 10.5 9.5 9.15685 9.5 7.5C9.5 5.84315 10.8431 4.5 12.5 4.5C14.1569 4.5 15.5 5.84315 15.5 7.5Z"
            stroke="currentColor"
            strokeWidth="1.7"
          />
          <path
            d="M6 18.25C6.50327 15.6508 8.78269 13.75 11.5 13.75H13.5C16.2173 13.75 18.4967 15.6508 19 18.25"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
          <path d="M7.25 9.25C7.25 10.3546 6.35457 11.25 5.25 11.25C4.14543 11.25 3.25 10.3546 3.25 9.25C3.25 8.14543 4.14543 7.25 5.25 7.25C6.35457 7.25 7.25 8.14543 7.25 9.25Z" stroke="currentColor" strokeWidth="1.7" />
          <path d="M1.75 17C1.95019 15.3336 3.36511 14.0833 5.04343 14.0833H6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      );
    case "dashboard":
    default:
      return (
        <svg {...iconProps}>
          <rect x="4.75" y="4.75" width="6.5" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
          <rect x="12.75" y="4.75" width="6.5" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
          <rect x="4.75" y="12.75" width="6.5" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
          <rect x="12.75" y="16.25" width="6.5" height="3" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
        </svg>
      );
  }
}
