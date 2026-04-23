import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "City Scraper — Real Estate Intelligence",
  description: "Find leadership and key contacts for any property address.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
