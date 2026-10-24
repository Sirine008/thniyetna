import React, { useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './Controls';
import { number } from '../lib/format';

/**
 * Dense data table: sortable columns, pagination, stacked rows on mobile (each cell shows its label).
 * columns: [{ key, label, render(row), sort(row) -> value | false, num, width }]
 * Filtering is done by the caller (filter bar), so the same rows feed the table, the map and the counts.
 */
export function DataTable({ columns, rows, rowKey, initialSort, pageSize = 20, onRowClick, selectedKey, caption, empty, rowLabel }) {
  const [sort, setSort] = useState(initialSort || null); // { key, dir: 'asc' | 'desc' }
  const [page, setPage] = useState(0);
  useEffect(() => { setPage(0); }, [rows.length]);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find(c => c.key === sort.key);
    if (!col || col.sort === false) return rows;
    const value = col.sort || (row => row[col.key]);
    const cmp = (a, b) => {
      const [x, y] = [value(a), value(b)];
      if (x == null && y == null) return 0;
      if (x == null) return 1;               // empty values last, both directions
      if (y == null) return -1;
      return typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'fr', { numeric: true });
    };
    return [...rows].sort((a, b) => (sort.dir === 'asc' ? cmp(a, b) : -cmp(a, b)) || 0);
  }, [rows, sort, columns]);

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const current = Math.min(page, pages - 1);
  const visible = sorted.slice(current * pageSize, current * pageSize + pageSize);
  const toggle = key => setSort(s => (s?.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }));

  if (!rows.length) return empty || null;
  const sortable = columns.filter(c => c.sort !== false);
  return <>
    {/* stacked rows on mobile hide the column headers: same sort, as a select */}
    {sortable.length > 0 && <div className="table-mobile-sort">
      <label className="field-label" htmlFor={`${caption || 'table'}-sort`}>Trier par</label>
      <select id={`${caption || 'table'}-sort`} className="select" value={sort ? `${sort.key}:${sort.dir}` : ''}
        onChange={e => { const [key, dir] = e.target.value.split(':'); setSort(key ? { key, dir } : null); }}>
        <option value="">Ordre par défaut</option>
        {sortable.flatMap(c => [<option key={`${c.key}:asc`} value={`${c.key}:asc`}>{c.label} (croissant)</option>, <option key={`${c.key}:desc`} value={`${c.key}:desc`}>{c.label} (décroissant)</option>])}
      </select>
    </div>}
    <div className="table-wrap">
      <table className="table table-stack">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead><tr>{columns.map(c => {
          const active = sort?.key === c.key;
          const ariaSort = active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';
          return <th key={c.key} scope="col" className={c.num ? 'num' : undefined} style={c.width ? { inlineSize: c.width } : undefined} aria-sort={c.sort === false ? undefined : ariaSort}>
            {c.sort === false ? c.label : <button type="button" className="sort-btn" data-active={active} onClick={() => toggle(c.key)}>
              {c.label}{active ? (sort.dir === 'asc' ? <ArrowUp aria-hidden="true"/> : <ArrowDown aria-hidden="true"/>) : <ArrowUpDown aria-hidden="true"/>}
            </button>}
          </th>;
        })}</tr></thead>
        <tbody>{visible.map(row => {
          const key = rowKey(row);
          const clickable = Boolean(onRowClick);
          return <tr key={key} className={[clickable && 'is-clickable', selectedKey === key && 'is-selected'].filter(Boolean).join(' ') || undefined}
            onClick={clickable ? () => onRowClick(row) : undefined}
            onKeyDown={clickable ? e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); onRowClick(row); } } : undefined}
            tabIndex={clickable ? 0 : undefined} aria-label={clickable && rowLabel ? rowLabel(row) : undefined}>
            {columns.map(c => <td key={c.key} data-label={c.label} className={c.num ? 'num' : undefined}><div className="td-inner">{c.render ? c.render(row) : (row[c.key] ?? '—')}</div></td>)}
          </tr>;
        })}</tbody>
      </table>
    </div>
    {sorted.length > pageSize && <nav className="pagination" aria-label="Pagination">
      <span>{number(current * pageSize + 1)}–{number(Math.min(sorted.length, (current + 1) * pageSize))} sur {number(sorted.length)}</span>
      <div className="row">
        <Button size="sm" icon={ChevronLeft} disabled={current === 0} onClick={() => setPage(current - 1)}>Précédent</Button>
        <span className="t-sm">Page {current + 1} / {pages}</span>
        <Button size="sm" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>Suivant<ChevronRight aria-hidden="true"/></Button>
      </div>
    </nav>}
  </>;
}

/** Filter bar above a table; `count` is the number of rows after filtering. */
export function Toolbar({ children, count }) {
  return <div className="toolbar" role="search">{children}{count != null && <span className="toolbar-count" aria-live="polite">{count}</span>}</div>;
}
