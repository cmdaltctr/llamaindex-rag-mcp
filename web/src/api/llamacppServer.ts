/**
 * Typed client for the llama.cpp server that `omrg web` starts and owns.
 * Shapes follow `openapi.yaml` (`getLlamacppServer`, `saveLlamacppServer`,
 * `startLlamacppServer`, `stopLlamacppServer`, `restartLlamacppServer`).
 * No response holds log text or text from the process: a failure is one fixed
 * reason.
 */
import type { ApiClient, CallOptions } from "./client";

export type ServerState = "stopped" | "starting" | "running" | "failed";

/** The fixed reasons of a `failed` state. */
export type ServerReason = "binary-invalid" | "model-invalid" | "not-loopback" | "port-in-use" | "exited" | "timeout" | "not-configured";

export interface ServerField {
  id: string;
  label: string;
  kind: "text" | "int";
  /** The program path or model (empty when not set), or the context window. */
  value: string | number;
  min: number | null;
  max: number | null;
  source: "env" | "config-file" | "saved" | "default";
  locked: boolean;
  lock_reason: string | null;
}

export interface LlamacppServerStatus {
  status: "ok";
  state: ServerState;
  reason: ServerReason | null;
  exit_code: number | null;
  pid_running: boolean;
  /** What the live process was started with, or `null` when none is owned. */
  running_with: { context_window: number; model_kind: "file" | "hf" } | null;
  /** The saved program, model or window differ from the live process. */
  pending_restart: boolean;
  saved: { binary: ServerField; model: ServerField; context_window: ServerField };
}

/** Keys to save. An absent key stays as it is; `null` clears the saved value. */
export interface LlamacppServerChange {
  binary?: string | null;
  model?: string | null;
  context_window?: number | null;
}

const PATH = "/v1/llamacpp/server";

export function getLlamacppServer(api: ApiClient, options: CallOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("GET", PATH, { signal: options.signal });
}

/** Saves the program, the model or the window. A running server keeps running. */
export function saveLlamacppServer(api: ApiClient, change: LlamacppServerChange, options: CallOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("PUT", PATH, { body: change, signal: options.signal });
}

export function startLlamacppServer(api: ApiClient, options: CallOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("POST", `${PATH}/start`, { signal: options.signal });
}

export function stopLlamacppServer(api: ApiClient, options: CallOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("POST", `${PATH}/stop`, { signal: options.signal });
}

export function restartLlamacppServer(api: ApiClient, options: CallOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("POST", `${PATH}/restart`, { signal: options.signal });
}
