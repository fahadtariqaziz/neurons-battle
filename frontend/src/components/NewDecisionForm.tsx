"use client";

// Problem input (requirements §10 A): question + optional context → POST /api/decisions → session page.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, createDecision } from "@/lib/api/client";

const MAX_CHARS = 4000; // same limits as the backend (intake.py)

export function NewDecisionForm() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { thread_id } = await createDecision({ question: question.trim(), context: context.trim() });
      router.push(`/decisions/${thread_id}`); // the thread_id lives in the URL: refresh-safe and shareable
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
      setSubmitting(false);
    }
  }

  const tooShort = question.trim().length < 3;

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5">
      <div className="space-y-1">
        <label htmlFor="question" className="block text-sm font-medium">
          Your condition or symptoms
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={MAX_CHARS}
          rows={4}
          placeholder="e.g. I have type 2 diabetes, diagnosed last year"
          className="w-full rounded-md border border-zinc-300 p-3 focus:border-zinc-500 focus:outline-none"
          required
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="context" className="block text-sm font-medium">
          Extra context <span className="font-normal text-zinc-500">(optional)</span>
        </label>
        <textarea
          id="context"
          value={context}
          onChange={(e) => setContext(e.target.value)}
          maxLength={MAX_CHARS}
          rows={2}
          placeholder="e.g. vegetarian, limited budget, already taking metformin"
          className="w-full rounded-md border border-zinc-300 p-3 focus:border-zinc-500 focus:outline-none"
        />
      </div>
      {error && (
        <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={submitting || tooShort}
        className="rounded-md bg-zinc-900 px-4 py-2 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? "Starting…" : "Start"}
      </button>
    </form>
  );
}
