import { normalizeError } from "../../api/errors";

// Shows an ApiError (or any error/string) without exposing technical details.
export default function ErrorAlert({ error, title = "Something went wrong" }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : normalizeError(error).message;
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <p className="font-medium">{title}</p>
      <p className="mt-1">{message}</p>
    </div>
  );
}
