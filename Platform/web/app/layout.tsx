import type { Metadata } from "next";
import { Space_Grotesk, Fraunces } from "next/font/google";
import { AuthRouteGuard } from "../components/auth-route-guard";
import "./globals.css";

const bodyFont = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
});

const titleFont = Fraunces({
  subsets: ["latin"],
  variable: "--font-title",
  weight: ["500", "700"],
});

export const metadata: Metadata = {
  title: "Project Y",
  description: "Realtime monitoring and run analytics for Project Y.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${bodyFont.variable} ${titleFont.variable}`}>
        <AuthRouteGuard>{children}</AuthRouteGuard>
      </body>
    </html>
  );
}
