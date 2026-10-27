// TC-1 (AC-1): the design system is installed. The build itself is run by
// `pnpm run build` / `make build APP=web`; this checks the files it relies on.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";

// vitest runs from apps/web (`pnpm --dir apps/web run test`)
const root = (path: string) => join(process.cwd(), path);

test("shadcn and Tailwind v4 are configured", () => {
  for (const file of [
    "components.json",
    "postcss.config.mjs",
    "src/app/globals.css",
    "src/lib/utils.ts",
    "src/components/ui/button.tsx",
  ]) {
    expect(existsSync(root(file)), file).toBe(true);
  }
  expect(readFileSync(root("src/app/globals.css"), "utf8")).toContain(
    'import "tailwindcss"',
  );
  expect(readFileSync(root("src/app/layout.tsx"), "utf8")).toContain(
    "globals.css",
  );
});
