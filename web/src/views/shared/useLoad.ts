import { useCallback, useEffect, useEffectEvent, useState } from "react";
import { messageOf } from "./labels";

interface Loaded<T> {
  id: string;
  key: string;
  data?: T;
  error?: string;
}

export interface LoadState<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Runs `load` when `key` changes or `reload` is called. A reload keeps the
 * previous data for the same key on screen until the new data arrives.
 * Pass `key = null` to skip loading.
 */
export function useLoad<T>(load: () => Promise<T>, key: string | null): LoadState<T> {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<Loaded<T>>({ id: "", key: "" });
  const id = key === null ? "" : `${key}#${version}`;
  const run = useEffectEvent(load);
  const reload = useCallback(() => setVersion((current) => current + 1), []);

  useEffect(() => {
    if (key === null) return;
    let live = true;
    run().then(
      (data) => live && setState({ id, key, data }),
      (error: unknown) => live && setState({ id, key, error: messageOf(error) }),
    );
    return () => {
      live = false;
    };
  }, [id, key]);

  const sameKey = key !== null && state.key === key;
  return {
    data: sameKey ? state.data : undefined,
    error: state.id === id && state.error !== undefined ? state.error : null,
    loading: key !== null && state.id !== id,
    reload,
  };
}
