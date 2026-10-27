import { PageHeader } from "@/components/PageHeader";
import { Users } from "@/features/users/Users";

export default function UsersPage() {
  return (
    <>
      <PageHeader
        title="Users"
        description="Change roles or remove accounts. The last owner cannot be removed."
      />
      <Users />
    </>
  );
}
