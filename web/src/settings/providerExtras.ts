import type { ComponentType } from "react";
import { LlamacppServerPanel } from "./LlamacppServerPanel";

/**
 * Extra blocks a provider card shows after its fields, by provider id. The
 * llama.cpp card shows the server that `omrs web` can start and own. A card
 * with no entry shows nothing extra.
 */
export const PROVIDER_EXTRAS: Record<string, ComponentType | undefined> = {
  llamacpp: LlamacppServerPanel,
};
