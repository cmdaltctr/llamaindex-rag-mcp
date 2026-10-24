import { describe, expect, it } from "vitest";
import { cellRule, changesOf, restartFor, startText } from "./configurationDraft";
import type { ConfigurationSetting } from "./configurationTypes";
import { IDENTITY_NOTE } from "./DocumentReadingSection";

/** A row the page may edit, from the default, applying after a restart. */
function setting(key: string, value: ConfigurationSetting["value"], overrides: Partial<ConfigurationSetting> = {}): ConfigurationSetting {
  return { key, value, source: "default", applies: "restart", restart_pending: false, saved: null, editable: true, read_only_reason: null, kind: "text", choices: null, min: null, max: null, nullable: false, ...overrides };
}

const TOP_K = setting("retrieval.top_k", 10, { kind: "int", min: 1, max: 100 });
const HYBRID = setting("retrieval.hybrid_enabled", false, { kind: "bool" });
const TIMEOUT = setting("metadata.ollama_classify_timeout_override", 30, { kind: "float", min: 0, nullable: true, source: "config-file", applies: "live" });

describe("startText", () => {
  it("starts from the saved value on a row that waits for a restart", () => {
    expect(startText(setting("retrieval.top_k", 10, { kind: "int", saved: 20, source: "config-file", restart_pending: true }))).toBe("20");
  });

  it("starts from the value in force when nothing waits", () => {
    expect(startText(setting("retrieval.top_k", 10, { kind: "int", saved: 20 }))).toBe("10");
  });

  it("gives an empty text for no value, also for a saved default that waits", () => {
    expect(startText(setting("answer.model", null))).toBe("");
    expect(startText({ ...TIMEOUT, saved: null, restart_pending: true })).toBe("");
  });

  it("types a boolean as true or false", () => {
    expect(startText(HYBRID)).toBe("false");
    expect(startText(setting("answer.enabled", true, { kind: "bool" }))).toBe("true");
  });
});

describe("cellRule", () => {
  it("gives the range rule for answer.max_rounds 12", () => {
    const rounds = setting("answer.max_rounds", 3, { kind: "int", min: 1, max: 8 });
    expect(cellRule(rounds, "12")).toBe("Enter 1 to 8.");
    expect(cellRule(rounds, "2.5")).toBe("Enter 1 to 8.");
    expect(cellRule(rounds, "8")).toBeNull();
  });

  it("accepts a decimal in range for a float and refuses one out of range", () => {
    const threshold = setting("retrieval.rerank_threshold", 0.5, { kind: "float", min: 0, max: 1 });
    expect(cellRule(threshold, "0.75")).toBeNull();
    expect(cellRule(threshold, "1.5")).toBe("Enter 0 to 1.");
  });

  it("asks for a value in an empty text that is not optional", () => {
    expect(cellRule(setting("answer.model", "qwen"), "")).toBe("Enter a value.");
    expect(cellRule(setting("answer.model", "qwen"), "   ")).toBe("Enter a value.");
    expect(cellRule(TOP_K, "")).toBe("Enter a value.");
  });

  it("accepts an empty optional number", () => {
    expect(cellRule(TIMEOUT, "")).toBeNull();
  });

  it("has no rule for a boolean or a choice", () => {
    expect(cellRule(HYBRID, "true")).toBeNull();
    expect(cellRule(setting("metadata.extraction_mode", "fast", { kind: "choice", choices: ["fast", "full"] }), "full")).toBeNull();
  });
});

describe("changesOf", () => {
  it("holds only the cells that differ from their start, typed for their kind", () => {
    const mode = setting("metadata.extraction_mode", "fast", { kind: "choice", choices: ["fast", "full"] });
    const draft = { "retrieval.top_k": "20", "retrieval.hybrid_enabled": "true", "metadata.extraction_mode": "fast" };
    expect(changesOf([TOP_K, HYBRID, mode], draft)).toEqual({ "retrieval.top_k": 20, "retrieval.hybrid_enabled": true });
  });

  it("gives null for an emptied optional setting", () => {
    expect(changesOf([TIMEOUT], { [TIMEOUT.key]: "" })).toEqual({ [TIMEOUT.key]: null });
  });

  it("sends a decimal as a number and a boolean off as false", () => {
    const threshold = setting("retrieval.rerank_threshold", 0.5, { kind: "float" });
    const enabled = setting("answer.enabled", true, { kind: "bool" });
    expect(changesOf([threshold, enabled], { "retrieval.rerank_threshold": " 0.75 ", "answer.enabled": "false" })).toEqual({ "retrieval.rerank_threshold": 0.75, "answer.enabled": false });
  });

  it("keeps text as typed and leaves out rows with no draft", () => {
    expect(changesOf([setting("answer.model", "qwen"), TOP_K], { "answer.model": "llama" })).toEqual({ "answer.model": "llama" });
  });

  it("is empty when nothing changed", () => {
    expect(changesOf([TOP_K, HYBRID], { "retrieval.top_k": "10", "retrieval.hybrid_enabled": "false" })).toEqual({});
  });
});

describe("restartFor", () => {
  it("names one saved key that applies at restart", () => {
    expect(restartFor([TOP_K, TIMEOUT], { "retrieval.top_k": 20, [TIMEOUT.key]: null })).toEqual({ change: "retrieval.top_k", plural: false });
  });

  it("counts several keys that apply at restart", () => {
    expect(restartFor([TOP_K, HYBRID], { "retrieval.top_k": 20, "retrieval.hybrid_enabled": true })).toEqual({ change: "2 changed settings", plural: true });
  });

  it("adds the index identity note for a chunking key", () => {
    const overlap = setting("chunking.chunk_overlap", 100, { kind: "int" });
    expect(restartFor([overlap], { "chunking.chunk_overlap": 50 })).toEqual({ change: "chunking.chunk_overlap", plural: false, note: IDENTITY_NOTE });
  });

  it("asks for no restart when every saved key applies live", () => {
    expect(restartFor([TIMEOUT], { [TIMEOUT.key]: 10 })).toBeNull();
  });
});
