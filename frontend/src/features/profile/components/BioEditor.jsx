import { useId, useState } from "react";
import { BIO_MAX, createProfile, updateProfile } from "../../../api/profile";
import { errorMessage } from "../../../api/errors";
import Button from "../../../components/ui/Button";
import { useToast } from "../../../context/ToastContext";

// "About me": a short professional introduction. Saved with PATCH /profiles/me (or POST /profiles/ when the
// student has no profile yet). Empty text clears it.
export default function BioEditor({ profile, onSaved }) {
  const id = useId();
  const toast = useToast();
  const saved = profile?.bio || "";
  const [editing, setEditing] = useState(!saved);
  const [text, setText] = useState(saved);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const length = text.trim().length;

  const save = async (event) => {
    event.preventDefault();
    if (length > BIO_MAX) return setError(`Use at most ${BIO_MAX} characters.`);
    setBusy(true);
    setError(null);
    try {
      const body = { bio: text.trim() || null };
      const result = profile ? await updateProfile(body) : await createProfile(body);
      onSaved(result);
      setText(result.bio || "");
      setEditing(!result.bio);
      toast.success(result.bio ? "Bio saved." : "Bio cleared.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
    return undefined;
  };

  if (!editing) {
    return (
      <div className="flex flex-col gap-3">
        <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">{saved}</p>
        <Button variant="secondary" onClick={() => setEditing(true)} className="w-fit py-1.5 text-xs">
          Edit bio
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-2" aria-label="Edit bio">
      <label htmlFor={id} className="text-sm font-medium text-slate-700">
        Short professional introduction
      </label>
      <textarea
        id={id}
        value={text}
        rows={5}
        maxLength={BIO_MAX + 50}
        onChange={(e) => {
          setText(e.target.value);
          if (error) setError(null);
        }}
        aria-invalid={error ? true : undefined}
        aria-describedby={`${id}-count`}
        placeholder="e.g. Final-year computer science student focused on data analysis with SQL and Power BI."
        className="cn-input resize-y"
      />
      <p id={`${id}-count`} className={`text-xs ${length > BIO_MAX ? "text-red-700" : "text-slate-500"}`}>
        {length}/{BIO_MAX} characters
      </p>
      {error && (
        <p role="alert" className="text-xs text-red-700">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" loading={busy} className="py-1.5 text-xs">
          Save bio
        </Button>
        {saved && (
          <Button
            variant="ghost"
            onClick={() => {
              setText(saved);
              setEditing(false);
              setError(null);
            }}
            className="py-1.5 text-xs"
          >
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
