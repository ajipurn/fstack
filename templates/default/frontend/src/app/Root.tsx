import { Spinner } from "../ui";
import { AppShell } from "./AppShell";
import { useSession } from "./session";
import { SignIn } from "./SignIn";

/** Session gate: splash → sign-in → app shell. */
export function Root() {
  const session = useSession();
  if (session.isPending) {
    return (
      <div className="grid min-h-dvh place-items-center text-muted">
        <Spinner />
      </div>
    );
  }
  if (!session.data) return <SignIn />;
  return <AppShell />;
}
