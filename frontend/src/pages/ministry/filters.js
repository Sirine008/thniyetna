import { useSearchParams } from 'react-router-dom';

/** A list filter stored in the URL (so KPI tiles and links can open a filtered list). Default values stay out of the URL. */
export function useUrlFilter(key, fallback = '') {
  const [params, setParams] = useSearchParams();
  const value = params.get(key) ?? fallback;
  const set = next => setParams(current => {
    const p = new URLSearchParams(current);
    if (next === fallback || next == null || next === '') p.delete(key); else p.set(key, next);
    return p;
  }, { replace: true });
  return [value, set];
}

/** Case- and accent-insensitive text search. */
export const fold = text => String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
export const matches = (query, ...fields) => !query.trim() || fields.some(f => fold(f).includes(fold(query.trim())));
