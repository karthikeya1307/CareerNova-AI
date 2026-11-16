import { useState } from "react";
import Button from "./Button";
import Input from "./Input";
import Modal from "./Modal";

export default function ConfirmDialog({
  title = "Are you sure?",
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "danger",
  requireText = null,
  onConfirm,
  onCancel,
}) {
  const [typed, setTyped] = useState("");
  const blocked = Boolean(requireText) && typed !== requireText;
  return (
    <Modal
      title={title}
      onClose={onCancel}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm} disabled={blocked}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {message && <p>{message}</p>}
      {requireText && (
        <Input
          className="mt-4"
          label={`Type ${requireText} to confirm`}
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          autoComplete="off"
        />
      )}
    </Modal>
  );
}
