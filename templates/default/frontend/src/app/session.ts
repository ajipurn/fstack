import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { ApiError, get, post, setCsrf, SIGNED_OUT } from "../lib/api";
import { keys, queryClient } from "../lib/query";
import type { Session } from "../lib/types";

async function fetchSession(): Promise<Session | null> {
  try {
    const session = await get<Session>("/auth/me");
    setCsrf(session.csrf_token);
    return session;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export function clearSession() {
  setCsrf("");
  queryClient.setQueryData(keys.session, null);
  queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "session" });
}

export function useSession() {
  useEffect(() => {
    window.addEventListener(SIGNED_OUT, clearSession);
    return () => window.removeEventListener(SIGNED_OUT, clearSession);
  }, []);
  return useQuery({ queryKey: keys.session, queryFn: fetchSession, staleTime: Infinity, retry: false });
}

export function useSignIn() {
  return useMutation({
    meta: { silent: true },
    mutationFn: (body: { key: string }) => post<Session>("/auth/login", body),
    onSuccess: ({ csrf_token }) => {
      setCsrf(csrf_token);
      queryClient.setQueryData<Session>(keys.session, { via: "dashboard", csrf_token });
    },
  });
}

export function useSignOut() {
  return useMutation({
    mutationFn: () => post<void>("/auth/logout"),
    onSettled: clearSession,
  });
}
