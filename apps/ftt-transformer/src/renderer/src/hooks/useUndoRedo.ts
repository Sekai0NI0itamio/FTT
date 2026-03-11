import { useCallback, useState } from "react";

export function useUndoRedo<T>(initialState: T) {
  const [past, setPast] = useState<T[]>([]);
  const [present, setPresent] = useState<T>(initialState);
  const [future, setFuture] = useState<T[]>([]);

  const set = useCallback((next: T) => {
    setPast((prev) => [...prev, present]);
    setPresent(next);
    setFuture([]);
  }, [present]);

  const undo = useCallback(() => {
    setPast((prev) => {
      if (prev.length === 0) return prev;
      const previous = prev[prev.length - 1];
      setFuture((futurePrev) => [present, ...futurePrev]);
      setPresent(previous);
      return prev.slice(0, -1);
    });
  }, [present]);

  const redo = useCallback(() => {
    setFuture((prev) => {
      if (prev.length === 0) return prev;
      const next = prev[0];
      setPast((pastPrev) => [...pastPrev, present]);
      setPresent(next);
      return prev.slice(1);
    });
  }, [present]);

  const canUndo = past.length > 0;
  const canRedo = future.length > 0;

  return { present, set, undo, redo, canUndo, canRedo };
}
