import type { Metadata } from "next";
import type { ReactNode } from "react";
import { headers } from "next/headers";
import { connection } from "next/server";
import { ConfigProvider } from "@/components/ConfigProvider";
import { Nav } from "@/features/auth/Nav";
import { SessionProvider } from "@/features/auth/SessionProvider";
import { getRuntimeConfig } from "@/lib/config/runtime";
import { MISMATCH_HEADER } from "@/lib/hosts";
import "./globals.css";

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
  // set by the proxy only (it always overwrites the header): page and API are on
  // hostnames that cannot share the login cookie, so say so instead of failing quietly
  const hostProblem = (await headers()).get(MISMATCH_HEADER);
  return (
    <html lang="en">
      <body>
        {hostProblem ? <p role="alert">{hostProblem}</p> : null}
        <ConfigProvider value={config}>
          <SessionProvider>
            <Nav />
            {children}
          </SessionProvider>
        </ConfigProvider>
      </body>
    </html>
  );
}
