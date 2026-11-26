import { useId, useRef, useState } from "react";
import { deleteAvatar, uploadAvatar, validateAvatarFile } from "../../../api/profile";
import { errorMessage } from "../../../api/errors";
import Avatar from "../../../components/ui/Avatar";
import Button from "../../../components/ui/Button";
import Icon from "../../../components/ui/Icon";
import { useConfirm } from "../../../context/ConfirmContext";
import { useAvatar } from "../../../context/AvatarContext";
import { useToast } from "../../../context/ToastContext";

// Upload, replace or remove the profile picture (PNG / JPEG / WebP, up to 2 MB). The picture is private:
// it is shown only to its owner in the profile, header, dashboard and assistant.
export default function ProfilePhoto({ user, hasAvatar, onChanged }) {
  const inputId = useId();
  const input = useRef(null);
  const { url, refresh } = useAvatar();
  const confirm = useConfirm();
  const toast = useToast();
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const [removing, setRemoving] = useState(false);
  const showing = Boolean(url);

  const choose = async (file) => {
    setError(null);
    const problem = validateAvatarFile(file);
    if (problem) return setError(problem);
    setProgress(0);
    try {
      const profile = await uploadAvatar(file, { onProgress: setProgress });
      await refresh();
      onChanged?.(profile);
      toast.success("Profile picture updated.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setProgress(null);
      if (input.current) input.current.value = "";
    }
    return undefined;
  };

  const remove = async () => {
    const ok = await confirm({
      title: "Remove your profile picture?",
      message: "Your initials will be shown instead. You can upload a new picture at any time.",
      confirmLabel: "Remove picture",
      tone: "danger",
    });
    if (!ok) return;
    setRemoving(true);
    setError(null);
    try {
      await deleteAvatar();
      await refresh();
      onChanged?.();
      toast.success("Profile picture removed.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setRemoving(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <Avatar user={user} size="xl" className="ring-4 ring-brand-50" />
      <div className="flex min-w-0 flex-col gap-2">
        <p className="text-sm text-slate-600">
          {showing ? "This picture is shown on your profile, in the header and in the assistants." : "No picture yet - your initials are shown."}
        </p>
        <div className="flex flex-wrap gap-2">
          <label htmlFor={inputId} className="sr-only">
            Choose a profile picture
          </label>
          <input
            ref={input}
            id={inputId}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            onChange={(e) => choose(e.target.files?.[0])}
          />
          <Button onClick={() => input.current?.click()} loading={progress !== null} className="py-1.5 text-xs">
            {progress === null && <Icon name="upload" className="h-3.5 w-3.5" />}
            {progress === null ? (showing || hasAvatar ? "Change picture" : "Upload picture") : `Uploading ${progress}%`}
          </Button>
          {(showing || hasAvatar) && (
            <Button variant="secondary" onClick={remove} loading={removing} className="py-1.5 text-xs">
              Remove
            </Button>
          )}
        </div>
        <p className="text-[11px] text-slate-500">PNG, JPEG or WebP · up to 2 MB · at least 32×32 pixels.</p>
        {error && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
