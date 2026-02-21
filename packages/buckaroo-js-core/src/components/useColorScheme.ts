import { useSyncExternalStore } from 'react';

type ColorScheme = 'light' | 'dark';

const mql =
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null;

function subscribe(cb: () => void): () => void {
  mql?.addEventListener('change', cb);
  return () => mql?.removeEventListener('change', cb);
}

function getSnapshot(): ColorScheme {
  return mql?.matches ? 'dark' : 'light';
}

function getServerSnapshot(): ColorScheme {
  return 'dark'; // SSR fallback
}

/**
 * React hook that reactively tracks the user's OS color scheme preference.
 * Re-renders the component when the preference changes.
 */
export function useColorScheme(): ColorScheme {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
