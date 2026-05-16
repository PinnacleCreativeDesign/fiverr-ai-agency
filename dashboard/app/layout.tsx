import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Fiverr AI Agency — Control Room",
  description: "Live view of the 19-agent order pipeline.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
