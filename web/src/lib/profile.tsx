"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Profile = components["schemas"]["ProfileResponse"];

/** null means signed in but not registered — the gate routes to /welcome. */
export function useProfileQuery(enabled: boolean) {
  return useQuery({
    queryKey: ["profile"],
    enabled,
    retry: false,
    queryFn: async (): Promise<Profile | null> => {
      const { data, error, response } = await api.GET("/api/profile");
      if (response.status === 404) return null;
      if (error) throw error;
      return data ?? null;
    },
  });
}

const ProfileContext = createContext<Profile | null>(null);

export const ProfileProvider = ProfileContext.Provider;

export function useProfile(): Profile {
  const profile = useContext(ProfileContext);
  if (!profile) throw new Error("useProfile outside the app gate");
  return profile;
}
