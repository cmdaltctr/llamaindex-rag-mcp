import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EmbeddingProfileFields } from "../api/embedding";
import type { ProfileRecord } from "../api/profiles";
import { renderWithProviders } from "../test/providers";
import { EmbeddingModelSection } from "./EmbeddingModelSection";
import { choose } from "./test/helpers";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const PROVIDERS = {
  status: "ok",
  providers: [
    { name: "ollama", available: true, reason: null },
    { name: "onnx", available: true, reason: null },
    { name: "llamacpp", available: false, reason: "No server." },
  ],
  server_default: { provider: "ollama", model: "nomic-embed-text" },
};

const NO_LOCK = { locked: false, collections: [] };

function profile(kind: "builtin" | "user", extra: EmbeddingProfileFields = {}): ProfileRecord {
  return {
    profile_id: kind === "user" ? "papers-search" : "documents",
    kind,
    title: "P",
    description: "",
    base_profile: "documents",
    slots: { ingest: null, search: null, answer: null },
    ready: true,
    not_ready_reasons: [],
    used_by: [],
    embedding: { provider: "ollama", model: "nomic-embed-text", source: "server_default", dimensions: null },
    embedding_lock: NO_LOCK,
    ...extra,
  };
}

type Handler = (method: string, path: string, body: Record<string, unknown>) => Response | undefined;

function setup(record: ProfileRecord, handler: Handler = () => undefined) {
  const calls: { method: string; path: string; body: Record<string, unknown> }[] = [];
  const fetchImpl = vi.fn(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    calls.push({ method, path, body });
    const custom = handler(method, path, body);
    if (custom !== undefined) return custom;
    if (path === "/v1/embedding-providers") return json(PROVIDERS);
    return json({ status: "error", message: "Not found." }, 404);
  });
  const user = userEvent.setup();
  renderWithProviders(<EmbeddingModelSection profile={record} />, { fetchImpl });
  return { user, calls };
}

describe("EmbeddingModelSection", () => {
  it("shows the server default as read-only text for a built-in profile", async () => {
    setup(profile("builtin"));
    expect(await screen.findByText(/nomic-embed-text/)).toBeInTheDocument();
    expect(screen.getByText(/server default/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check model" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("shows the controls for an unlocked user profile", async () => {
    setup(profile("user"));
    expect(await screen.findByRole("combobox", { name: "Provider" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check model" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save model" })).toBeInTheDocument();
  });

  it("starts empty for a profile on the server default, so a save is a choice", async () => {
    setup(profile("user"));
    const field = await screen.findByRole("textbox", { name: "Model" });
    expect(field).toHaveValue("");
    expect(field).toHaveAttribute("placeholder", "nomic-embed-text");
    expect(screen.getByRole("button", { name: "Save model" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Check model" })).toBeDisabled();
  });

  it("starts with the saved model for a profile that chose one", async () => {
    setup(profile("user", { embedding: { provider: "onnx", model: "bge-small", source: "profile", dimensions: 384 } }));
    expect(await screen.findByRole("textbox", { name: "Model" })).toHaveValue("bge-small");
    expect(screen.getByRole("button", { name: "Save model" })).toBeEnabled();
  });

  it("checks the typed model and shows the vector size", async () => {
    const { user, calls } = setup(profile("user"), (method, path) =>
      method === "POST" && path === "/v1/embedding-providers/ollama/check" ? json({ status: "ok", ok: true, dimensions: 1024, norm: 1, reason: null }) : undefined,
    );
    const field = await screen.findByRole("textbox", { name: "Model" });
    await user.clear(field);
    await user.type(field, "mxbai-embed-large");
    await user.click(screen.getByRole("button", { name: "Check model" }));
    expect(await screen.findByText(/Vector size: 1024/)).toBeInTheDocument();
    expect(calls.find((call) => call.method === "POST")?.body).toEqual({ model: "mxbai-embed-large" });
  });

  it("shows the reason of a failed check", async () => {
    const { user } = setup(profile("user"), (method) =>
      method === "POST" ? json({ status: "ok", ok: false, dimensions: null, norm: null, reason: "Model not found." }) : undefined,
    );
    await user.type(await screen.findByRole("textbox", { name: "Model" }), "ghost-model");
    await user.click(screen.getByRole("button", { name: "Check model" }));
    expect(await screen.findByText("Model not found.")).toBeInTheDocument();
  });

  it("saves the provider and model, then refreshes the profile", async () => {
    const saved = profile("user", { embedding: { provider: "onnx", model: "bge-small", source: "profile", dimensions: 384 } });
    const { user, calls } = setup(profile("user"), (method, path) => (method === "PUT" && path === "/v1/profiles/papers-search/embedding" ? json({ status: "ok", profile: saved }) : undefined));
    await choose(user, await screen.findByRole("combobox", { name: "Provider" }), "onnx");
    const field = screen.getByRole("textbox", { name: "Model" });
    await user.clear(field);
    await user.type(field, "bge-small");
    await user.click(screen.getByRole("button", { name: "Save model" }));
    await waitFor(() => expect(calls.some((call) => call.method === "PUT")).toBe(true));
    expect(calls.find((call) => call.method === "PUT")?.body).toEqual({ provider: "onnx", model: "bge-small" });
  });

  it("clears the choice with two nulls", async () => {
    const { user, calls } = setup(profile("user", { embedding: { provider: "onnx", model: "bge-small", source: "profile", dimensions: 384 } }), (method) =>
      method === "PUT" ? json({ status: "ok", profile: profile("user") }) : undefined,
    );
    await user.click(await screen.findByRole("button", { name: "Use server default" }));
    await waitFor(() => expect(calls.some((call) => call.method === "PUT")).toBe(true));
    expect(calls.find((call) => call.method === "PUT")?.body).toEqual({ provider: null, model: null });
  });

  it("shows the lock text and no controls for a locked profile", async () => {
    const lock = { locked: true, collections: [{ collection: "papers", provider: "ollama", model: "nomic-embed-text", chunk_count: 12 }] };
    setup(profile("user", { embedding_lock: lock }));
    expect(await screen.findByText("Locked: papers already holds vectors made with nomic-embed-text. Create a new collection to use another model.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check model" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("names the first blocking collection", async () => {
    const lock = {
      locked: true,
      collections: [
        { collection: "alpha", provider: "ollama", model: "m1", chunk_count: 1 },
        { collection: "beta", provider: "ollama", model: "m2", chunk_count: 2 },
      ],
    };
    setup(profile("user", { embedding_lock: lock }));
    expect(await screen.findByText(/^Locked: alpha already holds vectors made with m1\./)).toBeInTheDocument();
  });

  it("says the model is not recorded when the stamp lacks it", async () => {
    const lock = { locked: true, collections: [{ collection: "papers", provider: null, model: null, chunk_count: 5 }] };
    setup(profile("user", { embedding_lock: lock }));
    expect(
      await screen.findByText("Locked: papers already holds vectors, but the model that made them is not recorded. Create a new collection to use another model."),
    ).toBeInTheDocument();
  });

  it("shows the lock text when a save gets a 409", async () => {
    const body = {
      status: "error",
      message: "Locked.",
      error_type: "embedding_locked",
      collections: [{ collection: "papers", provider: "ollama", model: "nomic-embed-text", chunk_count: 3 }],
    };
    const { user } = setup(profile("user"), (method) => (method === "PUT" ? json(body, 409) : undefined));
    await user.type(await screen.findByRole("textbox", { name: "Model" }), "other-model");
    await user.click(screen.getByRole("button", { name: "Save model" }));
    expect(await screen.findByText("Locked: papers already holds vectors made with nomic-embed-text. Create a new collection to use another model.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save model" })).not.toBeInTheDocument();
  });

  it("lets the user try again after a 409, because the collection may have changed", async () => {
    const body = {
      status: "error",
      message: "Locked.",
      error_type: "embedding_locked",
      collections: [{ collection: "papers", provider: "ollama", model: "nomic-embed-text", chunk_count: 3 }],
    };
    const { user } = setup(profile("user"), (method) => (method === "PUT" ? json(body, 409) : undefined));
    await user.type(await screen.findByRole("textbox", { name: "Model" }), "other-model");
    await user.click(screen.getByRole("button", { name: "Save model" }));
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: "Save model" })).toBeInTheDocument();
    expect(screen.queryByText(/^Locked:/)).not.toBeInTheDocument();
  });

  it("offers no retry for a lock that the server reports", async () => {
    const lock = { locked: true, collections: [{ collection: "papers", provider: "ollama", model: "nomic-embed-text", chunk_count: 12 }] };
    setup(profile("user", { embedding_lock: lock }));
    await screen.findByText(/^Locked:/);
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("shows the reason when a save gets a 422", async () => {
    const { user } = setup(profile("user"), (method) => (method === "PUT" ? json({ status: "error", message: "Check failed.", reason: "Model not found." }, 422) : undefined));
    await user.type(await screen.findByRole("textbox", { name: "Model" }), "ghost-model");
    await user.click(screen.getByRole("button", { name: "Save model" }));
    expect(await screen.findByText("Model not found.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save model" })).toBeInTheDocument();
  });
});
