"use client";

// Keeps a session's status fresh: GET every 2 s while the graph runs, stop when it pauses or finishes.
// Everything shown comes from the backend (run_state, progress, pending); the UI never guesses.
// After a POST /resume, call refresh() to start polling again.

import { useCallback, useEffect, useState } from "react";

import { ApiError, getDecision } from "@/lib/api/client";
import type { DecisionStatus } from "@/lib/api/types";

const POLL_MS = 2000;
const RETRY_MS = 5000; // backend unreachable: keep trying, a bit slower

export function useDecision(threadId: string) {
  const [status, setStatus] = useState<DecisionStatus | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [refreshCount, setRefreshCount] = useState(0); // changing it re-runs the effect below

  useEffect(() => {
    let cancelled = false; // set when the page unmounts or threadId changes: ignore late answers
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function load() {
      try {
        const next = await getDecision(threadId);
        if (cancelled) return;
        setStatus(next);
        setError(null);
        if (next.run_state === "running") timer = setTimeout(load, POLL_MS);
      } catch (e) {
        if (cancelled) return;
        const err = e instanceof ApiError ? e : new ApiError(0, "unknown", String(e));
        setError(err);
        if (err.status === 0 || err.status >= 500) timer = setTimeout(load, RETRY_MS); // 404 etc.: stop
      }
    }

    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [threadId, refreshCount]);

  const refresh = useCallback(() => setRefreshCount((n) => n + 1), []);

  return { status, error, refresh };
}
