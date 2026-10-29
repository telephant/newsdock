import { PageHeader } from "@/components/PageHeader";
import { ForgotPasswordForm } from "@/features/auth/ForgotPasswordForm";

export default function ForgotPasswordPage() {
  return (
    <div className="mx-auto w-full max-w-sm pt-6">
      <PageHeader
        title="Forgot password"
        description="We email you a code to set a new password."
      />
      <ForgotPasswordForm />
    </div>
  );
}
