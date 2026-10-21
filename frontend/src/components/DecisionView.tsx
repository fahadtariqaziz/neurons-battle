"use client";

// Session page, bare version (9.1): live status + progress lines from the backend.
// The pause screens (questions, red-flag decision, review) and the report come in 9.2-9.4.

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useDecision } from "@/hooks/useDecision";
import { ApiError, resumeDecision } from "@/lib/api/client";
import type { PendingPause, RunState } from "@/lib/api/types";

const RUN_STATE_STYLE: Record<RunState, string> = {
  running: "bg-blue-100 text-blue-800",
  paused: "bg-amber-100 text-amber-800",
  interrupted: "bg-orange-100 text-orange-800",
  finished: "bg-green-100 text-green-800",
};

const PAUSE_TEXT: Record<PendingPause["type"], string> = {
  clarification: "waiting for your answers to the clarification questions",
  red_flag: "waiting for your decision about possible emergency signs",
  human_review: "waiting for your review of the three plans",
};

export function DecisionView() {
  const { threadId } = useParams<{ threadId: string }>();
  const { status, error, refresh } = useDecision(threadId);
  const [actionError, setActionError] = useState<string | null>(null);
  const progressEnd = useRef<HTMLLIElement>(null);

  const lineCount = status?.progress.length ?? 0;
  useEffect(() => {
    progressEnd.current?.scrollIntoView({ block: "nearest" }); // keep the newest line in view
  }, [lineCount]);

  async function continueRun() {
    setActionError(null);
    try {
      await resumeDecision(threadId, { type: "continue" });
      refresh();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Something went wrong.");
    }
  }

  if (!status) {
    return error ? <ErrorBox message={error.message} /> : <p className="text-zinc-500">Loading session…</p>;
  }

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <p className="text-sm text-zinc-500">Session {status.thread_id}</p>
        <h1 className="text-2xl font-semibold">{status.condition_name ?? status.question ?? "New session"}</h1>
        {status.question && status.condition_name && <p className="text-zinc-600">“{status.question}”</p>}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className={`rounded-full px-2.5 py-0.5 font-medium ${RUN_STATE_STYLE[status.run_state]}`}>
            {status.run_state}
          </span>
          {status.workflow_status && <span className="text-zinc-600">status: {status.workflow_status}</span>}
          {status.run_state === "running" && <span className="animate-pulse text-blue-700">agents at work…</span>}
        </div>
      </section>

      {status.red_flags.length > 0 && (
        <section role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-900">
          <p className="font-semibold">Possible emergency signs were reported</p>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {status.red_flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
          <p className="mt-2 text-sm">
            If any of these is happening now, contact emergency services or go to the nearest emergency department.
          </p>
        </section>
      )}

      {error && <ErrorBox message={`Could not refresh: ${error.message}`} />}
      {status.error && <ErrorBox message={`${status.error.code}: ${status.error.message}`} />}
      {actionError && <ErrorBox message={actionError} />}

      {status.run_state === "paused" && status.pending && (
        <section className="rounded-lg border border-amber-300 bg-amber-50 p-4">
          <p className="font-medium">Paused: {PAUSE_TEXT[status.pending.type]}.</p>
          <p className="mt-1 text-sm text-amber-900">The answer screen for this pause comes in the next steps (9.2-9.4).</p>
        </section>
      )}

      {status.run_state === "interrupted" && (
        <section className="flex items-center justify-between gap-4 rounded-lg border border-orange-300 bg-orange-50 p-4">
          <p className="text-sm">The run stopped before finishing (e.g. the server restarted). Everything up to the last step is saved.</p>
          <button onClick={continueRun} className="shrink-0 rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white">
            Continue
          </button>
        </section>
      )}

      {status.run_state === "finished" && (
        <section className="rounded-lg border border-green-300 bg-green-50 p-4 text-sm">
          Finished with status <strong>{status.workflow_status}</strong>.
          {status.has_report ? " The report screen comes in 9.4." : " No report was written for this session."}
        </section>
      )}

      <section className="space-y-2">
        <h2 className="font-semibold">Agent activity</h2>
        {status.progress.length === 0 ? (
          <p className="text-sm text-zinc-500">
            No live progress from this server process yet (progress lines are lost when the backend restarts).
          </p>
        ) : (
          <ol className="max-h-96 space-y-1 overflow-y-auto rounded-lg border border-zinc-200 bg-white p-3 font-mono text-xs">
            {status.progress.map((line, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0 text-zinc-400">{new Date(line.at).toLocaleTimeString()}</span>
                <span className="shrink-0 font-semibold text-zinc-700">{line.node}</span>
                <span className="text-zinc-800">{line.message}</span>
              </li>
            ))}
            <li ref={progressEnd} aria-hidden />
          </ol>
        )}
      </section>
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
      {message}
    </p>
  );
}
