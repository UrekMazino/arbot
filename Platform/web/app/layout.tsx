import type { Metadata } from "next";
import { Space_Grotesk, Fraunces } from "next/font/google";
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
  title: "OKXStatBot V2 Console",
  description: "Realtime monitoring and run analytics for OKXStatBot.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${bodyFont.variable} ${titleFont.variable}`}>{children}</body>
    </html>
  );
}
