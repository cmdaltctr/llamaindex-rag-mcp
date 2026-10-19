/**
 * Typed client for the embedding routes of the local `/v1` API: the provider
 * list, the model check and the profile embedding choice. Shapes follow
 * design D10 of `add-profile-embedding-model`. A refusal keeps its parsed body
 * on `ApiError.body`; `embeddingLockOf` and `embeddingRefusalReason` read it.
 */
import { ApiError, type ApiClient, type CallOptions } from "./client";
import type { ProfileRecord } from "./profiles";

export interface EmbeddingProvider {
  name: string;
  available: boolean;
  /** Why the provider is not available; `null` when it is. */
  reason: string | null;
}

export interface EmbeddingIdentity {
  provider: string;
  model: string;
}

export interface EmbeddingProviders {
  providers: EmbeddingProvider[];
  /** What an empty choice resolves to: the `EMBED_*` server settings. */
  server_default: EmbeddingIdentity;
}

export interface EmbeddingCheck {
  ok: boolean;
  dimensions: number | null;
  norm: number | null;
  /** Why the check failed; `null` when it passed. */
  reason: string | null;
}

/** Both fields `null` clears the choice, so the profile uses the server default. */
export interface EmbeddingChoice {
  provider: string | null;
  model: string | null;
}

/** One collection that blocks a model change. `model` is `null` when the stamp does not record it. */
export interface EmbeddingLockCollection {
  collection: string;
  provider: string | null;
  model: string | null;
  chunk_count: number;
}

/** The effective model of a profile. `source` is `profile` or `server_default`. */
export interface ProfileEmbedding {
  provider: string;
  model: string;
  source: "profile" | "server_default";
  dimensions: number | null;
}

export interface ProfileEmbeddingLock {
  locked: boolean;
  collections: EmbeddingLockCollection[];
}

/** The embedding fields that a profile item gains. Optional, so a reply from an older server still types. */
export interface EmbeddingProfileFields {
  embedding?: ProfileEmbedding;
  embedding_lock?: ProfileEmbeddingLock;
}

export async function listEmbeddingProviders(api: ApiClient, options: CallOptions = {}): Promise<EmbeddingProviders> {
  return api.request<EmbeddingProviders>("GET", "/v1/embedding-providers", { signal: options.signal });
}

/** Embeds a probe text with the model. A failed check is a normal answer with `ok: false`. */
export async function checkEmbeddingModel(api: ApiClient, provider: string, model: string, options: CallOptions = {}): Promise<EmbeddingCheck> {
  const path = `/v1/embedding-providers/${encodeURIComponent(provider)}/check`;
  return api.request<EmbeddingCheck>("POST", path, { body: { model }, signal: options.signal });
}

/**
 * Saves the choice. A lock refusal is a 409 (read it with `embeddingLockOf`),
 * a failed check is a 422 (`embeddingRefusalReason`) and a built-in profile is a 400.
 */
export async function saveProfileEmbedding(
  api: ApiClient,
  profileId: string,
  choice: EmbeddingChoice,
  options: CallOptions = {},
): Promise<ProfileRecord> {
  const path = `/v1/profiles/${encodeURIComponent(profileId)}/embedding`;
  return (await api.request<{ profile: ProfileRecord }>("PUT", path, { body: choice, signal: options.signal })).profile;
}

function bodyOf(error: unknown): Record<string, unknown> | null {
  if (!(error instanceof ApiError) || typeof error.body !== "object" || error.body === null) return null;
  return error.body as Record<string, unknown>;
}

/** The blocking collections of an `embedding_locked` 409, or `null` for any other error. */
export function embeddingLockOf(error: unknown): EmbeddingLockCollection[] | null {
  const body = bodyOf(error);
  if (body === null || body.error_type !== "embedding_locked" || !Array.isArray(body.collections)) return null;
  return body.collections as EmbeddingLockCollection[];
}

/** The reason of a 422 failed check, or `null` for any other error. */
export function embeddingRefusalReason(error: unknown): string | null {
  const body = bodyOf(error);
  if (!(error instanceof ApiError) || error.status !== 422 || body === null) return null;
  return typeof body.reason === "string" && body.reason.length > 0 ? body.reason : null;
}
