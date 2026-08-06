"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Dices } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AuthSheet } from "@/components/auth-sheet";
import { api } from "@/lib/api/client";
import { authClient } from "@/lib/auth-client";

/**
 * The one place a nickname is ever chosen. Roll until it feels right —
 * after "Keep it" the name is permanent, by design: there is no rename
 * surface anywhere in the product.
 */
export default function WelcomePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: session, isPending: sessionPending } = authClient.useSession();

  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!sessionPending && !session) router.replace("/sign-in");
  }, [sessionPending, session, router]);

  // The first candidate lands as soon as the session does; "Draw another"
  // refetches. Committing nothing until "Keep it" is the whole point.
  const rollQuery = useQuery({
    queryKey: ["nickname-roll"],
    enabled: !!session,
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
    queryFn: async () => {
      const { data, error } = await api.POST("/api/profile/nickname/roll");
      if (error || !data) throw error ?? new Error("no response");
      return data.nickname;
    },
  });
  const nickname = rollQuery.data ?? null;
  const rolling = rollQuery.isFetching;

  async function roll() {
    const { error } = await rollQuery.refetch();
    if (error) {
      toast.error("Could not draw a name", {
        description: "The API did not answer. Try the dice again.",
      });
    }
  }

  async function keep() {
    setCreating(true);
    try {
      const { data, error, response } = await api.POST("/api/profile", {
        body: { nickname },
      });
      if (response.status === 409) {
        // Someone kept the same name first — draw a fresh one and say so.
        toast.error("That name was just taken", { description: "Here is a new draw." });
        await roll();
        return;
      }
      if (error || !data) throw error ?? new Error("no response");
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
      router.replace("/");
    } catch {
      // Includes the already-registered case: the gate will route home.
      const { response } = await api.GET("/api/profile");
      if (response.ok) {
        toast("You are already registered.");
        router.replace("/");
        return;
      }
      toast.error("Registration failed", { description: "The API did not answer. Try again." });
    } finally {
      setCreating(false);
    }
  }

  return (
    <AuthSheet title="One name, drawn for you">
      <p className="text-sm text-muted-foreground">
        Inside Annos you are a nickname, not an email. Roll until one feels
        right — it is permanent after this page.
      </p>

      <div className="mt-6 border-y-2 border-foreground py-6 text-center">
        {nickname ? (
          <p className="font-mono text-xl font-bold break-all">{nickname}</p>
        ) : (
          <p className="font-mono text-xl text-muted-foreground">…</p>
        )}
      </div>

      <div className="mt-5 flex flex-col gap-3">
        <button
          type="button"
          onClick={roll}
          disabled={rolling || creating}
          className="flex min-h-12 items-center justify-center gap-2 border border-input font-bold hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Dices aria-hidden className="size-5" />
          {rolling ? "Drawing…" : "Draw another"}
        </button>
        <button
          type="button"
          onClick={keep}
          disabled={!nickname || rolling || creating}
          className="flex min-h-12 items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          {creating ? "Registering…" : "Keep it — start logging"}
        </button>
      </div>
    </AuthSheet>
  );
}
