/**
 * useDataViewBootstrap — kicks off the Data View SSE bootstrap load once.
 *
 * Simplified counterpart to `worldview/useQueryStream.ts`: Data View has no
 * query/mode/provider to pass in, so there's nothing to "run" beyond a single
 * parameterless `store.bootstrap()` call. Guarded with a mount ref, mirroring
 * `routes/index.tsx`'s own `startedRef` guard around the worldview mock
 * auto-play, so React StrictMode's dev-mode double-invoke of effects doesn't
 * double-open the SSE connection. `bootstrap()` itself is also idempotent
 * (a no-op once loading/ready), so this guard is defense in depth, not the
 * only thing preventing a double connection.
 */

import { useEffect, useRef } from "react";

import { useDataViewStore } from "./store";

export function useDataViewBootstrap(): void {
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    useDataViewStore.getState().bootstrap();
  }, []);
}
