import { useCallback, useEffect, useRef, useState } from 'react';
import { api, errorMessage } from './api';

export function useQuery<T>(path: string | null, pollMs = 0, scope = '') {
  const key = `${scope}:${path}`;
  const [state, setState] = useState<{ key: string; data: T | undefined; loading: boolean; error: string }>({ key, data: undefined, loading: !!path, error: '' });
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion(v => v + 1), []);
  useEffect(() => {
    if (!path) {
      setState({ key, data: undefined, loading: false, error: '' });
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    setState(s => ({ key, data: s.key === key ? s.data : undefined, loading: s.key !== key || !s.data, error: '' }));
    async function load() {
      try {
        const data = await api<T>(path!, 'GET', undefined, controller.signal);
        if (alive) setState({ key, data, loading: false, error: '' });
      } catch (error) {
        if (alive) setState(s => ({ ...s, loading: false, error: errorMessage(error) }));
      } finally {
        if (alive && pollMs) timer = setTimeout(load, pollMs);
      }
    }
    void load();
    return () => { alive = false; controller.abort(); clearTimeout(timer); };
  }, [path, key, pollMs, version]);
  return { ...(state.key === key ? state : { data: undefined, loading: !!path, error: '' }), reload };
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try { await action(); } catch (err) { setError(errorMessage(err)); }
    finally { lock.current = false; setBusy(false); }
  };
  return { busy, error, setError, run };
}

export function useRoute() {
  const read = () => window.location.hash.slice(1) || '/menu';
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const update = () => { setRoute(read()); window.scrollTo({ top: 0 }); };
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  return route;
}
export function navigate(path: string) { window.location.hash = path; }
