import { useCallback, useEffect } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';

/**
 * A list's search text, kept in the history entry's own state instead of the
 * address. What is typed there is often a buyer's name, login or e-mail, and an
 * address with it would stay in the browser's history and its suggestions long
 * after (GDPR, docs/GDPR.md). The state still survives a reload, "back" and
 * "forward", like the rest of the list's filters, which stay in the address.
 *
 * An address that still carries `?search=` (a bookmark from before, or a link
 * from elsewhere) is honoured once: the text moves into the state, and the
 * address is replaced without it.
 */
export interface ListSearchState {
  search?: string;
}

export function searchFromState(state: unknown): string {
  const search = (state as ListSearchState | null)?.search;
  return typeof search === 'string' ? search : '';
}

export function useListSearch(): {
  search: string;
  /** Set the address's other parameters and the search together, in one entry. */
  update: (params: URLSearchParams, search: string | undefined) => void;
  /** The state to hand a link that is to come back to this list as it is. */
  state: ListSearchState | null;
} {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const legacy = searchParams.get('search');

  useEffect(() => {
    if (legacy === null) return;
    const next = new URLSearchParams(searchParams);
    next.delete('search');
    const query = next.toString();
    navigate(`${location.pathname}${query ? `?${query}` : ''}`, {
      replace: true,
      state: { ...(location.state as object | null), search: legacy || undefined },
    });
  }, [legacy, searchParams, location.pathname, location.state, navigate]);

  const search = legacy ?? searchFromState(location.state);

  const update = useCallback(
    (params: URLSearchParams, next: string | undefined) => {
      params.delete('search');
      setSearchParams(params, { state: next ? { search: next } : null });
    },
    [setSearchParams],
  );

  return { search, update, state: search ? { search } : null };
}
