import { NewDecisionForm } from "@/components/NewDecisionForm";

// Server Component: static text rendered on the server; the interactive form is a Client Component.
export default function Home() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Describe your health condition</h1>
        <p className="text-zinc-600">
          A few questions first, then agents research the condition from three perspectives (research papers,
          doctors, patients), debate care plans and write a report for you to discuss with your doctor.
        </p>
      </div>
      <NewDecisionForm />
    </div>
  );
}
