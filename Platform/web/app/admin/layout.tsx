"use client";

import { SidebarProvider } from "../../context/sidebar-context";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <SidebarProvider>{children}</SidebarProvider>;
}