import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client";
import { createProfile, deleteProfile, getProfile, listProfiles, updateProfile, type ProfileRecord } from "./profiles";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function fetchReturning(response: Response) {
  return vi.fn(async (input: string, init?: RequestInit) => {
    void input;
    void init;
    return response;
  });
}

const USER: ProfileRecord = {
  profile_id: "papers-search",
  kind: "user",
  title: "Papers search",
  description: "",
  base_profile: "documents",
  slots: { ingest: "p1", search: "p2", answer: "p3" },
  ready: true,
  not_ready_reasons: [],
  used_by: [],
};

describe("profile API client", () => {
  it("lists the profiles", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", profiles: [USER] }));
    const api = createApiClient(fetchImpl);
    expect(await listProfiles(api)).toEqual([USER]);
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/profiles");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("reads one profile with the standard graphs of a built-in", async () => {
    const graphs = { ingest: { schema_version: 1, nodes: [] }, search: { schema_version: 1, nodes: [] }, answer: { schema_version: 1, nodes: [] } };
    const builtin = { ...USER, profile_id: "documents", kind: "builtin", slots: { ingest: null, search: null, answer: null }, standard_graphs: graphs };
    const fetchImpl = fetchReturning(json({ status: "ok", profile: builtin }));
    const api = createApiClient(fetchImpl);
    const profile = await getProfile(api, "documents");
    expect(profile.standard_graphs).toEqual(graphs);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/profiles/documents");
  });

  it("reads a user profile with no standard graphs", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", profile: { ...USER, standard_graphs: null } }));
    const api = createApiClient(fetchImpl);
    expect((await getProfile(api, "papers-search")).standard_graphs).toBeNull();
  });

  it("encodes the profile id in the path", async () => {
    const fetchImpl = vi.fn(async (input: string, init?: RequestInit) => {
      void input;
      void init;
      return json({ status: "ok", profile: USER });
    });
    const api = createApiClient(fetchImpl);
    await getProfile(api, "a/b?c");
    await updateProfile(api, "a/b?c", { title: "T" });
    await deleteProfile(api, "a/b?c");
    expect(fetchImpl.mock.calls.map((call) => call[0])).toEqual(["/v1/profiles/a%2Fb%3Fc", "/v1/profiles/a%2Fb%3Fc", "/v1/profiles/a%2Fb%3Fc"]);
  });

  it("creates a profile from a source with a POST body", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", profile: USER }, 201));
    const api = createApiClient(fetchImpl);
    const created = await createProfile(api, { source: "documents", title: "Papers search" });
    expect(created.profile_id).toBe("papers-search");
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/profiles");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ source: "documents", title: "Papers search" });
    expect(new Headers(init?.headers).get("content-type")).toBe("application/json");
  });

  it("creates an empty profile with a null source", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", profile: USER }, 201));
    const api = createApiClient(fetchImpl);
    await createProfile(api, { source: null, title: "Blank" });
    expect(JSON.parse(String(fetchImpl.mock.calls[0]?.[1]?.body))).toEqual({ source: null, title: "Blank" });
  });

  it("renames a profile with PATCH and the title only", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", profile: { ...USER, title: "New" } }));
    const api = createApiClient(fetchImpl);
    const changed = await updateProfile(api, "papers-search", { title: "New" });
    expect(changed.title).toBe("New");
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/profiles/papers-search");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ title: "New" });
  });

  it("deletes a profile with DELETE and no body", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", profile: USER }));
    const api = createApiClient(fetchImpl);
    expect((await deleteProfile(api, "papers-search")).profile_id).toBe("papers-search");
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/profiles/papers-search");
    expect(init?.method).toBe("DELETE");
    expect(init?.body).toBeUndefined();
  });

  it("keeps the used_by names of a 409 refusal readable from ApiError.body", async () => {
    const fetchImpl = fetchReturning(json({ status: "error", message: "In use.", used_by: ["kb-a", "kb-b"] }, 409));
    const api = createApiClient(fetchImpl);
    const failure = await deleteProfile(api, "papers-search").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(409);
    expect((failure as ApiError).body).toMatchObject({ used_by: ["kb-a", "kb-b"] });
  });
});
