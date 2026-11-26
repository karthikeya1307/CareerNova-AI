import EmptyState from "../../components/ui/EmptyState";

// Placeholder for sections implemented in later frontend steps.
export default function ComingSoonPage({ title, phase }) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{title}</h1>
      <EmptyState
        title={`${title} is coming soon`}
        message={phase ? `This page is built in frontend step ${phase}.` : "This page is built in a later frontend step."}
      />
    </div>
  );
}
