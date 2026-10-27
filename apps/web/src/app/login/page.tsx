import { LoginForm } from "@/features/auth/LoginForm";
import { safeNext } from "@/lib/gate";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  return (
    <main>
      <h1>Log in</h1>
      <LoginForm next={safeNext(Array.isArray(next) ? next[0] : next)} />
    </main>
  );
}
