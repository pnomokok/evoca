import { useCallback, useRef } from 'react';

// One audio element per component, created on first use. Call the returned
// function wherever the element is needed (handlers and effects, not render).
export function useAudioElement() {
  const ref = useRef(null);
  return useCallback(() => {
    if (!ref.current) ref.current = new Audio();
    return ref.current;
  }, []);
}
