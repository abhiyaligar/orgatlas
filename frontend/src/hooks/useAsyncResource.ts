import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiFailure, RequestState } from "@/types";

export interface AsyncResource<T> {
  data: T | null;
  state: RequestState;
  failure: ApiFailure | null;
  reload: () => void;
}

function toFailure(error: unknown): ApiFailure {
  if (error instanceof Error) {
    const status = "status" in error ? Number((error as { status?: unknown }).status) : 0;
    return { message: error.message, status: Number.isFinite(status) ? status : 0 };
  }
  return { message: "Unexpected error", status: 0 };
}

export function useAsyncResource<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [state, setState] = useState<RequestState>("loading");
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [nonce, setNonce] = useState(0);
  const active = useRef(true);

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setFailure(null);

    loader()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setState("success");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setFailure(toFailure(error));
        setState("error");
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return { data, state, failure, reload };
}