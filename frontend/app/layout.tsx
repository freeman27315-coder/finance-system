import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";

export const metadata: Metadata = {
  title: "Finance System",
  description: "Multi-wallet finance dashboard"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
