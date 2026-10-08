import type { Metadata } from "next";
import type { ReactNode } from "react";
import { connection } from "next/server";
import { ConfigProvider } from "@/components/ConfigProvider";
import { getRuntimeConfig } from "@/lib/config/runtime";

export const metadata: Metadata = {
  title: "newsdock",
  description: "News dock for AI agents",
};

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  await connection(); // dynamic rendering: config is read per request, not at build
  const config = getRuntimeConfig();
  return (
    <html lang="en">
      <body>
        <ConfigProvider value={config}>{children}</ConfigProvider>
      </body>
    </html>
  );
}
