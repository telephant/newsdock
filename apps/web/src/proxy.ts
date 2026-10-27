// Next 16 "proxy" (the former middleware): host alignment and the optimistic login
// gate for every page. Runs on the Node.js runtime, so it can read the runtime
// config like the layout does (ADR-0014). The logic lives in lib/proxy-handler.ts.
import type { NextRequest } from "next/server";
import { getRuntimeConfig } from "@/lib/config/runtime";
import { handleRequest } from "@/lib/proxy-handler";

export function proxy(request: NextRequest) {
  return handleRequest(request, getRuntimeConfig());
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
