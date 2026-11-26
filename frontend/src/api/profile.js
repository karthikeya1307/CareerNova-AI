// Student profile endpoints (backend/routes/profiles.py). The profile belongs to the signed-in user;
// no user id is ever sent. Fields: college (<=200), degree (<=150), graduation_year (1900-2100),
// location (<=150). Name, email and phone live on the account (/auth/me) and have no update endpoint.
import { api } from "./client";
import { normalizeError } from "./errors";

export const PROFILE_LIMITS = { college: 200, degree: 150, location: 150, yearMin: 1900, yearMax: 2100 };

// GET /profiles/me -> ProfileResponse, or null when the student has not created one yet (404).
export async function getProfile() {
  try {
    const { data } = await api.get("/profiles/me");
    return data;
  } catch (error) {
    if (normalizeError(error).status === 404) return null;
    throw error;
  }
}

// POST /profiles/ -> ProfileResponse (201). 409 if a profile already exists.
export async function createProfile(fields) {
  const { data } = await api.post("/profiles/", fields);
  return data;
}

// PATCH /profiles/me -> ProfileResponse. Only the fields sent are changed (null clears a field).
export async function updateProfile(changes) {
  const { data } = await api.patch("/profiles/me", changes);
  return data;
}

export const BIO_MAX = 600; // backend profile_schema.BIO_MAX
export const AVATAR_TYPES = ["image/png", "image/jpeg", "image/webp"];
export const AVATAR_MAX_BYTES = 2 * 1024 * 1024; // backend avatars.MAX_BYTES

// Same first checks as the backend (which also reads the real image header and its size).
export function validateAvatarFile(file) {
  if (!file) return "Choose a picture.";
  if (!AVATAR_TYPES.includes(file.type) && !/\.(png|jpe?g|webp)$/i.test(file.name)) return "Use a PNG, JPEG or WebP picture.";
  if (file.size === 0) return "The file is empty.";
  if (file.size > AVATAR_MAX_BYTES) return "The picture is larger than 2 MB.";
  return null;
}

// POST /profiles/me/avatar (multipart "file") -> ProfileResponse (has_avatar: true). The profile row is
// created if the student has none yet.
export async function uploadAvatar(file, { onProgress } = {}) {
  const form = new FormData();
  form.append("file", file, file.name);
  const { data } = await api.post("/profiles/me/avatar", form, {
    onUploadProgress: onProgress
      ? (event) => {
          if (event.total) onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
        }
      : undefined,
  });
  return data;
}

// DELETE /profiles/me/avatar -> 204
export async function deleteAvatar() {
  await api.delete("/profiles/me/avatar");
}

// GET /profiles/me/avatar -> the picture (owner only), as a Blob; null when there is none (404).
export async function fetchAvatarBlob() {
  try {
    const { data } = await api.get("/profiles/me/avatar", { responseType: "blob" });
    return data;
  } catch (error) {
    if (normalizeError(error).status === 404) return null;
    throw error;
  }
}
