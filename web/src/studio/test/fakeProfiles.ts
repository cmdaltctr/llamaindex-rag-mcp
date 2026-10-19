import type { PipelineRecord } from "../../api/pipelines";
import type { ProfileDetail, ProfilePurpose, ProfileRecord } from "../../api/profiles";

/** A reply the fake server turns into a `Response`. */
export interface Reply {
  status: number;
  body: unknown;
}

const PURPOSES: ProfilePurpose[] = ["ingest", "search", "answer"];

const reply = (body: unknown, status = 200): Reply => ({ status, body });
const refusal = (message: string, status: number, extra: Record<string, unknown> = {}): Reply => reply({ status: "error", message, ...extra }, status);

/** Mirrors the server: the id comes from the title and never repeats. */
function idFromTitle(title: string, taken: (id: string) => boolean): string {
  const base = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "profile";
  let id = base;
  for (let n = 2; taken(id); n += 1) id = `${base}-${n}`;
  return id;
}

/** A list item never carries the standard graphs. */
function asItem(profile: ProfileDetail): ProfileRecord {
  const { standard_graphs: graphs, ...item } = profile;
  void graphs;
  return item;
}

/**
 * In-memory stand-in for the `/v1/profiles` routes. A new profile adds three
 * pipelines with no saved revision to the shared `pipelines` map, as the
 * server does for a duplicate or an empty profile.
 */
export function createFakeProfiles(initial: ProfileDetail[], pipelines: Map<string, PipelineRecord>) {
  const profiles = new Map(initial.map((profile) => [profile.profile_id, { ...profile }]));

  /** The user profile and purpose that a pipeline fills, or `null`. */
  function slotOf(pipelineId: string): { profile: ProfileDetail; slot: ProfilePurpose } | null {
    for (const profile of profiles.values()) {
      const slot = PURPOSES.find((purpose) => profile.slots[purpose] === pipelineId);
      if (slot !== undefined) return { profile, slot };
    }
    return null;
  }

  function create(body: Record<string, unknown>): Reply {
    const title = typeof body.title === "string" ? body.title.trim() : "";
    if (title === "" || title.length > 80) return refusal("A title holds 1 to 80 characters.", 400);
    const source = typeof body.source === "string" ? profiles.get(body.source) : null;
    if (source === undefined) return refusal("Unknown source profile.", 404);
    const id = idFromTitle(title, (candidate) => profiles.has(candidate));
    const slots = { ingest: `${id}-ingest`, search: `${id}-search`, answer: `${id}-answer` };
    for (const purpose of PURPOSES) {
      pipelines.set(slots[purpose], {
        pipeline_id: slots[purpose],
        title: `${title} ${purpose}`,
        current_revision_id: null,
        layout: {},
        created_at: "2026-10-13T12:00:00Z",
        updated_at: "2026-10-13T12:00:00Z",
      });
    }
    const profile: ProfileDetail = {
      profile_id: id,
      kind: "user",
      title,
      description: "",
      base_profile: source === null || source === undefined ? "documents" : source.base_profile,
      slots,
      ready: source !== null,
      not_ready_reasons: source === null ? ["The Ingest, Search and Answer pipelines have no saved revision. Open each one and save a revision."] : [],
      used_by: [],
      standard_graphs: null,
    };
    profiles.set(id, profile);
    return reply({ status: "ok", profile: asItem(profile) }, 201);
  }

  function change(method: string, profile: ProfileDetail, body: Record<string, unknown>): Reply {
    if (profile.kind === "builtin") return refusal("A built-in profile cannot be changed.", 403);
    if (method === "DELETE") {
      if (profile.used_by.length > 0) return refusal("A collection uses this profile.", 409, { used_by: profile.used_by });
      profiles.delete(profile.profile_id);
      return reply({ status: "ok", profile: asItem(profile) });
    }
    const title = typeof body.title === "string" ? body.title.trim() : profile.title;
    if (title === "" || title.length > 80) return refusal("A title holds 1 to 80 characters.", 400);
    profile.title = title;
    return reply({ status: "ok", profile: asItem(profile) });
  }

  /** Answers a `/v1/profiles...` request, or `null` for any other path. */
  function route(method: string, path: string, body: Record<string, unknown>): Reply | null {
    if (path === "/v1/profiles" && method === "GET") return reply({ status: "ok", profiles: [...profiles.values()].map(asItem) });
    if (path === "/v1/profiles" && method === "POST") return create(body);
    const match = /^\/v1\/profiles\/([^/]+)$/.exec(path);
    if (match === null) return null;
    const profile = profiles.get(decodeURIComponent(match[1]!));
    if (profile === undefined) return refusal("Unknown profile.", 404);
    if (method === "GET") return reply({ status: "ok", profile });
    return change(method, profile, body);
  }

  return { route, slotOf, profiles };
}
