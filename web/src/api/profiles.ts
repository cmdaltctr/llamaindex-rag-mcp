/**
 * Typed client for the profile routes of the local `/v1` API.
 *
 * Shapes follow `src/omrg/transports/api/routes/profiles.py` and the
 * `Profile*` schemas in `openapi.yaml`. Every function takes the `ApiClient`
 * first. A refusal keeps its parsed body on `ApiError.body`, so a 409 delete
 * shows the collections in `used_by`.
 */
import type { ApiClient, CallOptions } from "./client";
import type { EmbeddingProfileFields } from "./embedding";
import type { GraphDocument } from "./pipelines";

export type ProfileKind = "builtin" | "user";

export type ProfilePurpose = "ingest" | "search" | "answer";

/** The three pipeline IDs of a profile by purpose. All `null` for a built-in profile. */
export type ProfileSlots = Record<ProfilePurpose, string | null>;

/** One profile as the list and the write routes return it. */
export interface ProfileRecord extends EmbeddingProfileFields {
  profile_id: string;
  kind: ProfileKind;
  title: string;
  description: string;
  base_profile: "documents" | "codebase";
  slots: ProfileSlots;
  ready: boolean;
  /** Plain lines that say which pipeline to fix and how. */
  not_ready_reasons: string[];
  /** Names of the collections whose stored profile is this one. */
  used_by: string[];
}

/** The standard graphs of a built-in profile, one per purpose. */
export type StandardGraphs = Record<ProfilePurpose, GraphDocument>;

/** `GET /v1/profiles/{id}`: the record, plus the standard graphs for a built-in (`null` for a user profile). */
export interface ProfileDetail extends ProfileRecord {
  standard_graphs: StandardGraphs | null;
}

/** `source` is a built-in ID, a user profile ID, or `null` for an empty profile. */
export interface ProfileCreateInput {
  source: string | null;
  title: string;
}

export interface ProfileUpdateInput {
  title: string;
}

const profilePath = (profileId: string): string => `/v1/profiles/${encodeURIComponent(profileId)}`;

export async function listProfiles(api: ApiClient, options: CallOptions = {}): Promise<ProfileRecord[]> {
  return (await api.request<{ profiles: ProfileRecord[] }>("GET", "/v1/profiles", { signal: options.signal })).profiles;
}

export async function getProfile(api: ApiClient, profileId: string, options: CallOptions = {}): Promise<ProfileDetail> {
  return (await api.request<{ profile: ProfileDetail }>("GET", profilePath(profileId), { signal: options.signal })).profile;
}

export async function createProfile(api: ApiClient, input: ProfileCreateInput, options: CallOptions = {}): Promise<ProfileRecord> {
  return (await api.request<{ profile: ProfileRecord }>("POST", "/v1/profiles", { body: input, signal: options.signal })).profile;
}

export async function updateProfile(
  api: ApiClient,
  profileId: string,
  input: ProfileUpdateInput,
  options: CallOptions = {},
): Promise<ProfileRecord> {
  return (await api.request<{ profile: ProfileRecord }>("PATCH", profilePath(profileId), { body: input, signal: options.signal })).profile;
}

/** Returns the profile as it was before the delete. A profile that a collection uses gives a 409 with `used_by`. */
export async function deleteProfile(api: ApiClient, profileId: string, options: CallOptions = {}): Promise<ProfileRecord> {
  return (await api.request<{ profile: ProfileRecord }>("DELETE", profilePath(profileId), { signal: options.signal })).profile;
}
