import { PageHeader } from "@/components/PageHeader";
import { ResetPasswordForm } from "@/features/auth/ResetPasswordForm";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ email?: string | string[] }>;
}) {
  const { email } = await searchParams;
  const initial = Array.isArray(email) ? email[0] : email;
  return (
    <div className="mx-auto w-full max-w-sm pt-6">
      <PageHeader
        title="Set a new password"
        description="Enter the code from the email and choose a new password."
      />
      <ResetPasswordForm initialEmail={initial ?? ""} />
    </div>
  );
}
