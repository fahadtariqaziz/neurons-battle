"use client";

// Red-flag pause: a human decides whether to go on. Both options are explained; "stop" ends the session.

import { OctagonAlert, PhoneCall } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { ApiError, resumeDecision } from "@/lib/api/client";
import type { RedFlagPayload } from "@/lib/api/types";

export function RedFlagDecision({
  threadId,
  payload,
  onSubmitted,
}: {
  threadId: string;
  payload: RedFlagPayload;
  onSubmitted: () => void;
}) {
  const [busy, setBusy] = useState<"continue" | "stop" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(action: "continue" | "stop") {
    if (busy) return;
    setBusy(action);
    setError(null);
    try {
      await resumeDecision(threadId, { type: "red_flag", action });
      onSubmitted();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
      setBusy(null);
    }
  }

  const nextStep = payload.resume_to === "clarification" ? "the clarification questions" : "the research";

  return (
    <section role="alertdialog" aria-labelledby="redflag-title" className="animate-fade-up overflow-hidden rounded-2xl border-2 border-red-300 bg-white shadow-md">
      <div className="flex gap-4 border-b border-red-100 bg-red-50 px-5 py-5">
        <OctagonAlert className="mt-0.5 size-8 shrink-0 text-red-600" aria-hidden />
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wider text-red-700">Safety check: your decision is needed</p>
          <h2 id="redflag-title" className="text-xl font-semibold text-red-900">
            Possible emergency signs were reported
          </h2>
          <p className="text-sm text-red-900/90">{payload.message}</p>
        </div>
      </div>
      <div className="space-y-5 px-5 py-5">
        <ul className="space-y-2">
          {payload.red_flags.map((f) => (
            <li key={f} className="flex gap-2 rounded-lg border border-red-200 bg-red-50/60 px-3 py-2 text-sm text-red-900">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-red-500" />
              {f}
            </li>
          ))}
        </ul>
        <div className="flex gap-3 rounded-xl bg-slate-900 px-4 py-3 text-sm text-white">
          <PhoneCall className="mt-0.5 size-5 shrink-0" aria-hidden />
          <p>
            <span className="font-semibold">If any of these is happening right now,</span> call your local emergency number or go to the
            nearest emergency department. This tool gives information only and cannot help in an emergency.
          </p>
        </div>
        {payload.error && (
          <Callout tone="warning" title="Your previous reply was not accepted">
            <p>{payload.error}</p>
          </Callout>
        )}
        {error && (
          <Callout tone="danger" title="Could not send your decision">
            <p>{error}</p>
          </Callout>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-2 rounded-xl border border-slate-200 p-4">
            <p className="text-sm font-semibold text-slate-900">Stop here and seek care</p>
            <p className="text-sm text-slate-600">Ends this session now. Nothing more is researched. You can start a new session later.</p>
            <Button variant="danger" onClick={() => decide("stop")} loading={busy === "stop"} disabled={busy === "continue"} className="w-full">
              Stop the session
            </Button>
          </div>
          <div className="space-y-2 rounded-xl border border-slate-200 p-4">
            <p className="text-sm font-semibold text-slate-900">Continue for information</p>
            <p className="text-sm text-slate-600">
              Goes on with {nextStep}. Every plan will put urgent care first, and no extra research loops will run.
            </p>
            <Button variant="secondary" onClick={() => decide("continue")} loading={busy === "continue"} disabled={busy === "stop"} className="w-full">
              Continue anyway
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
