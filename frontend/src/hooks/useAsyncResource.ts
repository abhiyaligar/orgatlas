import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiFailure, RequestState } from "@/types";

export interface AsyncResource<T> {
  data: T | null;
  state: RequestState;
  failure: ApiFailure | null;
  reload: () => void;
}

interface AsyncSlice {
  key: string;
  state: RequestState;
  failure: ApiFailure | null;
}

function toFailure(error: unknown): ApiFailure {
  if (error instanceof Error) {
    const candidate = (error as { status?: unknown }).status;
    const status = typeof candidate === "number" ? candidate : 0;
    return { message: error.message, status };
  }
  return { message: "Unexpected error", status: 0 };
}

export function useAsyncResource<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncResource<T> {
  const [nonce, setNonce] = useState(0);
  const [data, setData] = useState<T | null>(null);
  const [slice, setSlice] = useState<AsyncSlice>({ key: "", state: "idle", failure: null });

  const key = `${nonce}::${deps.join("|")}`;
  const active = useRef(true);

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    loader()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setSlice({ key, state: "success", failure: null });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setSlice({ key, state: "error", failure: toFailure(error) });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  // A new key means a new request is in flight; derive that during render
  // rather than resetting state inside the effect body.
  const isStale = slice.key !== key;
  const state: RequestState = isStale ? "loading" : slice.state;

  return {
    data: isStale ? null : data,
    state,
    failure: isStale ? null : slice.failure,
    reload,
  };
}