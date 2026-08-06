"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthSheet } from "@/components/auth-sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";

/**
 * Registration is UI-only by design — a hallucinating MCP client must not be
 * able to create an account. Better Auth owns the credential; the Annos
 * profile (with its generated nickname) is created at /welcome afterwards.
 *
 * No name is collected: Better Auth's `name` field is deliberately left empty.
 * The only human-readable identifier Annos ever uses is its own generated
 * nickname.
 */
export default function SignUpPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const { error } = await authClient.signUp.email({
      email,
      password,
      name: "",
    });
    if (error) {
      setError(error.message ?? "Sign-up failed");
      setPending(false);
      return;
    }
    router.push("/welcome");
  }

  return (
    <AuthSheet title="Create an account">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div>
          <Label htmlFor="email" className="mb-1.5 font-mono text-xs uppercase">
            Email
          </Label>
          <Input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-12 text-base"
          />
        </div>
        <div>
          <Label htmlFor="password" className="mb-1.5 font-mono text-xs uppercase">
            Password
          </Label>
          <Input
            id="password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-12 text-base"
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Your email stays with the sign-in system — the tracker itself never
          sees it. Inside Annos you are only your nickname, drawn on the next
          page.
        </p>
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={pending}
          className="mt-1 flex min-h-12 items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending ? "Creating account…" : "Sign up"}
        </button>
      </form>
      <p className="mt-5 text-sm text-muted-foreground">
        Already registered?{" "}
        <Link href="/sign-in" className="text-primary underline underline-offset-2">
          Sign in
        </Link>
      </p>
    </AuthSheet>
  );
}
