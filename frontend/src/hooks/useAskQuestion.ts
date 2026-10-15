import { useCallback, useState } from "react";

import { askQuestion, ApiError } from "@/services/apiClient";
import type { AskQuestionRequest, AskQuestionResponse, ApiFailure } from "@/types";

export interface AskState {
  response: AskQuestionResponse | null;
  pending: boolean;
  failure: ApiFailure | null;
  ask: (request: AskQuestionRequest) => Promise<void>;
  clear: () => void;
}

export function useAskQuestion(): AskState {
  const [response, setResponse] = useState<AskQuestionResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const ask = useCallback(async (request: AskQuestionRequest) => {
    setPending(true);
    setFailure(null);
    try {
      const result = await askQuestion(request);
      setResponse(result);
    } catch (error) {
      setResponse(null);
      setFailure({
        message: error instanceof Error ? error.message : "Unexpected error",
        status: error instanceof ApiError ? error.status : 0,
      });
    } finally {
      setPending(false);
    }
  }, []);

  const clear = useCallback(() => {
    setResponse(null);
    setFailure(null);
  }, []);

  return { response, pending, failure, ask, clear };
}