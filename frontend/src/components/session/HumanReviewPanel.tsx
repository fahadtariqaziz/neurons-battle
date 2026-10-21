"use client";

// Human review pause: the three winning plans side by side and the seven possible actions, with the
// same rules the backend enforces (feedback required for reject, winners only for select_plan, limits).

import { Plus, Send, Trash2, UserCheck } from "lucide-react";
import { useState } from "react";

import { PerspectiveCard } from "@/components/report/PerspectiveCard";
import { PlanDetails } from "@/components/report/PlanDetails";
import { Badge } from "@/components/ui/Badge";
import { BulletList } from "@/components/ui/BulletList";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ApiError, resumeDecision } from "@/lib/api/client";
import type { HumanAction, HumanReviewPayload, LiveSnapshot } from "@/lib/api/types";
import { perspectiveOf } from "@/lib/format";

const ACTION_ORDER: HumanAction[] = ["approve", "select_plan", "reject", "request_debate_round", "request_more_research", "modify_profile", "add_context"];

const ACTION_LABEL: Record<HumanAction, string> = {
  approve: "Approve all three plans",
  select_plan: "Pick one plan to focus on",
  reject: "Reject and explain why",
  request_debate_round: "Run another debate round",
  request_more_research: "Research something specific",
  modify_profile: "Correct a fact about me",
  add_context: "Add missing context",
};

const SUBMIT_LABEL: Record<HumanAction, string> = {
  approve: "Approve and write the report",
  select_plan: "Select this plan and write the report",
  reject: "Send feedback for a new round",
  request_debate_round: "Start another round",
  request_more_research: "Start the focused research",
  modify_profile: "Save and re-check",
  add_context: "Add context and re-check",
};

export function HumanReviewPanel({
  threadId,
  payload,
  live,
  onSubmitted,
}: {
  threadId: string;
  payload: HumanReviewPayload;
  live: LiveSnapshot | null;
  onSubmitted: () => void;
}) {
  const [action, setAction] = useState<HumanAction>("approve");
  const [feedback, setFeedback] = useState("");
  const [selected, setSelected] = useState<string | null>(payload.selectable_plan_ids[0] ?? null);
  const [rows, setRows] = useState<{ key: string; value: string }[]>([{ key: "", value: "" }]);
  const [openPlan, setOpenPlan] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { can_debate, can_research, blocked_by } = payload.limits;
  const blockedNote = blocked_by.length ? ` (${blocked_by.join("; ")})` : "";

  function disabledReason(a: HumanAction): string | null {
    if (a === "request_debate_round" && !can_debate) return `No debate round left${blockedNote}.`;
    if (a === "request_more_research" && !can_research) return `No research pass left${blockedNote}.`;
    if ((a === "modify_profile" || a === "add_context") && !can_research && !can_debate) return `Cannot re-check anymore${blockedNote}.`;
    if (a === "select_plan" && payload.selectable_plan_ids.length === 0) return "No plan can be selected.";
    return null;
  }

  const profileChanges = Object.fromEntries(rows.filter((r) => r.key.trim() && r.value.trim()).map((r) => [r.key.trim(), r.value.trim()]));

  function validationError(): string | null {
    if (action === "reject" && !feedback.trim()) return "Say what is wrong with the plans so the next round can address it.";
    if (action === "add_context" && !feedback.trim()) return "Write the context you want to add.";
    if (action === "select_plan" && !selected) return "Choose one of the three plans.";
    if (action === "modify_profile" && Object.keys(profileChanges).length === 0) return "Add at least one fact (key and value).";
    return null;
  }

  async function submit() {
    const invalid = validationError();
    if (invalid) {
      setError(invalid);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await resumeDecision(threadId, {
        type: "human_review",
        action,
        feedback: feedback.trim(),
        selected_plan_id: action === "select_plan" ? selected ?? undefined : undefined,
        profile_changes: action === "modify_profile" ? profileChanges : undefined,
      });
      onSubmitted();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
      setSubmitting(false);
    }
  }

  const needsFeedback = action === "reject" || action === "add_context" || action === "request_more_research";

  return (
    <div className="animate-fade-up space-y-5">
      <Card className="border-amber-200">
        <CardHeader
          eyebrow="Your turn"
          title={
            <span className="flex items-center gap-2">
              <UserCheck className="size-5 text-amber-600" aria-hidden />
              Review the three winning plans
            </span>
          }
          description="The Judge picked one winner per perspective and the Evidence Checker verified their claims. Nothing more happens until you decide."
          aside={<Badge tone="amber" size="md">Review round {payload.round}</Badge>}
        />
        <CardBody className="space-y-4">
          {payload.error && (
            <Callout tone="warning" title="Your previous choice was not accepted">
              <p>{payload.error}</p>
            </Callout>
          )}
          {payload.unresolved_questions.length > 0 && (
            <Callout tone="warning" title="Still unverified after checking">
              <BulletList items={payload.unresolved_questions} />
            </Callout>
          )}
          <div className="grid gap-4 lg:grid-cols-3">
            {payload.perspectives.map((p) => {
              const perspective = perspectiveOf(p.perspective);
              if (!perspective) return null;
              const plan = live?.debate.care_plans.find((c) => c.plan_id === p.plan_id) ?? null;
              return (
                <PerspectiveCard
                  key={p.perspective}
                  perspective={perspective}
                  planId={p.plan_id}
                  name={p.name ?? null}
                  summary={p.summary ?? null}
                  weightedTotal={p.weighted_total ?? null}
                  confidence={p.confidence ?? null}
                  difficulty={p.difficulty ?? null}
                  verificationCounts={p.verification_counts ?? {}}
                  objections={p.top_objections ?? []}
                  unavailableReason={p.reason ?? null}
                  isUserChoice={false}
                  expanded={openPlan === p.plan_id}
                  onToggle={plan ? () => setOpenPlan(openPlan === p.plan_id ? null : p.plan_id) : undefined}
                />
              );
            })}
          </div>
          {openPlan && live && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              {(() => {
                const plan = live.debate.care_plans.find((c) => c.plan_id === openPlan);
                if (!plan) return null;
                return (
                  <PlanDetails
                    plan={plan}
                    score={live.debate.scores.find((s) => s.plan_id === openPlan) ?? null}
                    criticism={live.debate.criticisms.find((c) => c.plan_id === openPlan) ?? null}
                    claims={live.verification.results.filter((r) => r.plan_id === openPlan)}
                  />
                );
              })()}
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader eyebrow="Decide" title="What should happen next?" description={blocked_by.length ? `Some options are unavailable: ${blocked_by.join("; ")}.` : "Every option is available."} />
        <CardBody className="space-y-5">
          <div className="grid gap-2 sm:grid-cols-2">
            {ACTION_ORDER.map((a) => {
              const reason = disabledReason(a);
              const checked = action === a;
              return (
                <label
                  key={a}
                  className={`flex cursor-pointer gap-3 rounded-xl border p-3 transition ${
                    checked ? "border-brand bg-brand-faint ring-2 ring-brand/20" : "border-slate-200 bg-white hover:border-slate-300"
                  } ${reason ? "cursor-not-allowed opacity-60" : ""}`}
                >
                  <input type="radio" name="action" value={a} checked={checked} disabled={!!reason} onChange={() => setAction(a)} className="mt-1 accent-brand" />
                  <span className="space-y-0.5">
                    <span className="block text-sm font-semibold text-slate-900">{ACTION_LABEL[a]}</span>
                    <span className="block text-xs text-slate-600">{payload.options[a]}</span>
                    {reason && <span className="block text-xs text-amber-700">{reason}</span>}
                  </span>
                </label>
              );
            })}
          </div>

          {action === "select_plan" && (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium text-slate-900">Which plan?</legend>
              <div className="grid gap-2 sm:grid-cols-3">
                {payload.perspectives
                  .filter((p) => p.plan_id && payload.selectable_plan_ids.includes(p.plan_id))
                  .map((p) => (
                    <label key={p.plan_id} className={`flex cursor-pointer gap-2 rounded-lg border p-3 text-sm ${selected === p.plan_id ? "border-brand bg-brand-faint" : "border-slate-200"}`}>
                      <input type="radio" name="plan" checked={selected === p.plan_id} onChange={() => setSelected(p.plan_id)} className="mt-0.5 accent-brand" />
                      <span>
                        <span className="block font-medium text-slate-900">{p.name}</span>
                        <span className="block text-xs text-slate-500">{p.label.split(" (")[0]}</span>
                      </span>
                    </label>
                  ))}
              </div>
            </fieldset>
          )}

          {needsFeedback && (
            <div className="space-y-1.5">
              <label htmlFor="feedback" className="block text-sm font-medium text-slate-900">
                {action === "reject" ? "What is wrong with the plans?" : action === "add_context" ? "Context to add" : "What should the agents look for?"}
                {action === "request_more_research" && <span className="font-normal text-slate-500"> (optional: otherwise the unverified claims are re-checked)</span>}
              </label>
              <textarea
                id="feedback"
                rows={3}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                maxLength={4000}
                className="w-full rounded-lg border border-slate-300 p-2.5 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
              />
            </div>
          )}

          {action === "modify_profile" && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-slate-900">Facts to correct</p>
              {rows.map((row, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    value={row.key}
                    onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, key: e.target.value } : r)))}
                    placeholder="key, e.g. age"
                    className="w-1/3 rounded-lg border border-slate-300 p-2 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
                  />
                  <input
                    value={row.value}
                    onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))}
                    placeholder="value, e.g. 50"
                    className="flex-1 rounded-lg border border-slate-300 p-2 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
                  />
                  <Button variant="ghost" size="sm" aria-label="Remove" onClick={() => setRows(rows.length > 1 ? rows.filter((_, j) => j !== i) : [{ key: "", value: "" }])}>
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </div>
              ))}
              <Button variant="secondary" size="sm" icon={<Plus className="size-4" aria-hidden />} onClick={() => setRows([...rows, { key: "", value: "" }])}>
                Add another fact
              </Button>
            </div>
          )}

          {error && (
            <Callout tone="danger">
              <p>{error}</p>
            </Callout>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500">You can inspect every plan, score and source in the tabs below before deciding.</p>
            <Button size="lg" onClick={submit} loading={submitting} icon={<Send className="size-4" aria-hidden />}>
              {SUBMIT_LABEL[action]}
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
