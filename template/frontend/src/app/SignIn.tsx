import { useState, type FormEvent } from "react";
import { errorMessage } from "../lib/api";
import { play } from "../lib/sound";
import { Button, Field, Input } from "../ui";
import { useSignIn } from "./session";

export function SignIn() {
  const signIn = useSignIn();
  const [key, setKey] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    signIn.mutate({ key }, { onError: () => play("error"), onSuccess: () => play("success") });
  }

  return (
    <div className="auth-wrap">
      <div className="w-full max-w-[22rem] fade-up">
        <div className="panel">
          <div className="panel-body px-7 pb-7 pt-8">
            <div className="mb-6 flex flex-col items-center text-center">
              <span className="brand-mark mb-4 !size-9 !rounded-[10px]">
                <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
                  <path d="M5 12V4h6M5 8h4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <h1 className="text-[15px] font-semibold tracking-[-0.01em]">Sign in to Fstack Starter</h1>
              <p className="mt-1 text-sm text-muted">Enter the access key for this workspace.</p>
            </div>
            <form onSubmit={submit} className="space-y-3.5">
              <Field label="Access key" htmlFor="access-key" error={signIn.isError ? errorMessage(signIn.error) : undefined}>
                <Input
                  id="access-key"
                  type="password"
                  autoComplete="current-password"
                  autoFocus
                  required
                  value={key}
                  invalid={signIn.isError}
                  onChange={(e) => setKey(e.target.value)}
                />
              </Field>
              <Button type="submit" variant="primary" block pending={signIn.isPending} className="!mt-5">
                Continue
              </Button>
            </form>
          </div>
          <div className="panel-foot justify-center">
            <span>
              The key is <code className="text-ink-2">APP_ACCESS_KEY</code> in backend/.env
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
