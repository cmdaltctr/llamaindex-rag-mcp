import { describe, expect, it } from "vitest";
import { ApiError, createApiClient } from "../../api/client";
import { getPipeline, saveRevision } from "../../api/pipelines";
import { createProfile, deleteProfile, getProfile, listProfiles, updateProfile } from "../../api/profiles";
import { fakeServer } from "./fakeServer";
import { ANSWER_PIPELINE, ANSWER_REVISION, STANDARD_GRAPHS, TEMPLATE_DOC, TEMPLATE_PIPELINE, TEMPLATE_REVISION, USER_PROFILE } from "./helpers";

function setup() {
  const server = fakeServer({ pipelines: [TEMPLATE_PIPELINE, ANSWER_PIPELINE], revisions: [TEMPLATE_REVISION, ANSWER_REVISION] });
  return { server, api: createApiClient(server.fetchImpl) };
}

describe("the fake profile routes", () => {
  it("lists built-in profiles first, without standard graphs", async () => {
    const { api } = setup();
    const profiles = await listProfiles(api);
    expect(profiles.map((profile) => profile.profile_id)).toEqual(["documents", "codebase", "search-copy", "half-built"]);
    expect(profiles.every((profile) => !("standard_graphs" in profile))).toBe(true);
  });

  it("returns the standard graphs for a built-in and null for a user profile", async () => {
    const { api } = setup();
    expect((await getProfile(api, "documents")).standard_graphs).toEqual(STANDARD_GRAPHS);
    expect((await getProfile(api, "search-copy")).standard_graphs).toBeNull();
  });

  it("answers an unknown profile with 404", async () => {
    const { api } = setup();
    const failure = await getProfile(api, "pl_1").catch((error: unknown) => error);
    expect((failure as ApiError).status).toBe(404);
  });

  it("makes the id from the title and three pipelines for a new profile", async () => {
    const { api, server } = setup();
    const made = await createProfile(api, { source: "documents", title: "Papers search" });
    expect(made).toMatchObject({ profile_id: "papers-search", kind: "user", ready: true, used_by: [] });
    expect(Object.values(made.slots).every((id) => id !== null && server.pipelines.has(id))).toBe(true);
    const second = await createProfile(api, { source: null, title: "Papers search" });
    expect(second).toMatchObject({ profile_id: "papers-search-2", ready: false });
  });

  it("renames a user profile and refuses a built-in", async () => {
    const { api } = setup();
    expect((await updateProfile(api, "search-copy", { title: "  New  " })).title).toBe("New");
    expect(((await updateProfile(api, "documents", { title: "x" }).catch((e: unknown) => e)) as ApiError).status).toBe(403);
    expect(((await updateProfile(api, "search-copy", { title: " " }).catch((e: unknown) => e)) as ApiError).status).toBe(400);
  });

  it("refuses to delete a profile in use with the collection names, then deletes an unused one", async () => {
    const { api } = setup();
    const refused = (await deleteProfile(api, "search-copy").catch((error: unknown) => error)) as ApiError;
    expect(refused.status).toBe(409);
    expect(refused.body).toMatchObject({ used_by: USER_PROFILE.used_by });
    await deleteProfile(api, "half-built");
    expect((await listProfiles(api)).map((profile) => profile.profile_id)).not.toContain("half-built");
  });

  it("names the profile slot of a pipeline and the affected collections of a revision save", async () => {
    const { api } = setup();
    const detail = await getPipeline(api, "p1");
    expect(detail).toMatchObject({ profile_slot: { profile_id: "search-copy", slot: "search" } });
    const saved = await saveRevision(api, "p1", TEMPLATE_DOC);
    expect(saved.affected_collections).toEqual(USER_PROFILE.used_by);
  });
});
