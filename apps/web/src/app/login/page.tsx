import { PageHeader } from "@/components/PageHeader";
import { LoginForm } from "@/features/auth/LoginForm";
import { safeNext } from "@/lib/gate";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  return (
    <div className="mx-auto w-full max-w-sm pt-6">
      <PageHeader title="Log in" description="Welcome back to newsdock." />
      <LoginForm next={safeNext(Array.isArray(next) ? next[0] : next)} />
    </div>
  );
}
