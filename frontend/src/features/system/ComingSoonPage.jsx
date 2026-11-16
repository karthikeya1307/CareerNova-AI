import EmptyState from "../../components/ui/EmptyState";

// Placeholder for sections implemented in later frontend steps.
export default function ComingSoonPage({ title, phase }) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">{title}</h1>
      <EmptyState title={`${title} is coming soon`} message={`This page is built in frontend step ${phase}.`} />
    </div>
  );
}
