import { useCallback, useRef, useState } from "react";
import { normalizeError } from "../../api/errors";
import { compactErrors } from "./validation";

// Small form-state helper for the auth screens.
//   * `field(name)` returns value/onChange/error props for an input.
//   * `submit(event, action, onApiError)` validates, runs `action(values)`, and turns API failures
//     into field errors (FastAPI 422 lists) or a form-level ApiError. `onApiError` can handle a
//     specific failure (e.g. 409, 403) and return true to stop the default handling.
//   * After a failed submit, focus moves to the first invalid field.
export default function useAuthForm(initialValues, validate) {
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const formRef = useRef(null);
  const busy = useRef(false);

  const focusFirstInvalid = useCallback(() => {
    requestAnimationFrame(() => formRef.current?.querySelector('[aria-invalid="true"]')?.focus());
  }, []);

  const setValue = useCallback((name, value) => {
    setValues((current) => ({ ...current, [name]: value }));
    setErrors((current) => {
      if (!current[name]) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
  }, []);

  const field = (name) => ({
    name,
    value: values[name],
    error: errors[name],
    onChange: (event) => setValue(name, event.target.type === "checkbox" ? event.target.checked : event.target.value),
  });

  const submit = async (event, action, onApiError) => {
    event?.preventDefault();
    if (busy.current) return; // ignore double submits
    const found = compactErrors(validate(values));
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length) {
      focusFirstInvalid();
      return;
    }
    busy.current = true;
    setSubmitting(true);
    try {
      await action(values);
    } catch (error) {
      const failure = normalizeError(error);
      if (onApiError?.(failure)) return;
      const known = Object.fromEntries(Object.entries(failure.fieldErrors || {}).filter(([name]) => name in values));
      if (failure.status === 422 && Object.keys(known).length) {
        setErrors(known);
        focusFirstInvalid();
      } else {
        setApiError(failure);
      }
    } finally {
      busy.current = false;
      setSubmitting(false);
    }
  };

  return { values, setValue, errors, setErrors, apiError, setApiError, submitting, field, submit, formRef, focusFirstInvalid };
}
