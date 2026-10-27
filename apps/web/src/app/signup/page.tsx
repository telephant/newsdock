import { PageHeader } from "@/components/PageHeader";
import { SignupForm } from "@/features/auth/SignupForm";

export default function SignupPage() {
  return (
    <div className="mx-auto w-full max-w-sm pt-6">
      <PageHeader
        title="Sign up"
        description="Create an account to read the news dock."
      />
      <SignupForm />
    </div>
  );
}
