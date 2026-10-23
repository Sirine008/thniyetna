import React, { useEffect, useId, useRef, useState } from 'react';
import { api } from '../lib/api';

const DEBOUNCE_MS = 250;
// icon per category_key of GET /routing/places
const ICONS = {
  city: '🏙️', town: '🏙️', village: '🏘️', hamlet: '🏘️', suburb: '📍', neighbourhood: '📍', locality: '📍',
  street: '🛣️', hospital: '🏥', clinic: '🏥', school: '🏫', university: '🎓', townhall: '🏛️',
  administration: '🏛️', police: '🚓', post_office: '📮', station: '🚉', bus_station: '🚌', port: '⚓',
};
export const placeIcon = key => ICONS[key] || '📍';
export const placeDetail = p => [p.category, p.locality, p.name_ar].filter(Boolean).join(' · ');

/** Destination search with autocomplete (place index of the Bizerte governorate): debounce, category icon,
 *  keyboard navigation (↑ ↓ Entrée Échap) and the ARIA combobox pattern. */
export default function PlaceSearch({ value, onValueChange, onChoose, onClear, placeholder = 'Où allez-vous ?' }) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [status, setStatus] = useState('idle'); // idle | loading | done | error
  const timer = useRef();
  const seq = useRef(0);
  const listId = useId();

  useEffect(() => () => clearTimeout(timer.current), []);

  const search = text => {
    onValueChange(text);
    clearTimeout(timer.current);
    const id = ++seq.current;
    if (text.trim().length < 2) { setResults([]); setOpen(false); setStatus('idle'); return; }
    setStatus('loading');
    setOpen(true);
    timer.current = setTimeout(async () => {
      try {
        const rows = await api.places(text.trim(), 8);
        if (id !== seq.current) return; // a newer keystroke is in flight
        setResults(rows); setActive(rows.length ? 0 : -1); setStatus('done');
      } catch {
        if (id === seq.current) { setResults([]); setStatus('error'); }
      }
    }, DEBOUNCE_MS);
  };

  const choose = place => {
    seq.current++;
    clearTimeout(timer.current);
    setOpen(false); setResults([]); setActive(-1); setStatus('idle');
    onChoose(place);
  };

  const onKeyDown = e => {
    if (e.key === 'Escape') { setOpen(false); return; }
    if (!results.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive(i => (i + 1) % results.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setOpen(true); setActive(i => (i <= 0 ? results.length - 1 : i - 1)); }
    else if (e.key === 'Enter' && open) { e.preventDefault(); choose(results[Math.max(0, active)]); }
  };

  const showList = open && (status !== 'idle');
  return <div className="place-search">
    <input
      value={value}
      onChange={e => search(e.target.value)}
      onKeyDown={onKeyDown}
      onFocus={() => results.length && setOpen(true)}
      onBlur={() => setTimeout(() => setOpen(false), 120)}
      placeholder={placeholder}
      autoComplete="off"
      enterKeyHint="search"
      role="combobox"
      aria-label="Destination"
      aria-autocomplete="list"
      aria-expanded={showList}
      aria-controls={listId}
      aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
    />
    {value && <button type="button" className="place-clear" aria-label="Effacer la destination" onClick={() => { search(''); onClear?.(); }}>×</button>}
    {showList && <div className="search-results" id={listId} role="listbox">
      {results.map((r, i) => <button type="button" key={`${r.name}-${r.lat}-${r.lon}`} id={`${listId}-${i}`} role="option"
        aria-selected={i === active} className={i === active ? 'active' : ''}
        onMouseDown={e => e.preventDefault()} onMouseEnter={() => setActive(i)} onClick={() => choose(r)}>
        <span className="place-icon" aria-hidden="true">{placeIcon(r.category_key)}</span>
        <div><b>{r.name}</b><small>{placeDetail(r)}</small></div>
      </button>)}
      {status === 'loading' && !results.length && <p className="search-state">Recherche…</p>}
      {status === 'done' && !results.length && <p className="search-state">Aucun lieu trouvé dans le gouvernorat de Bizerte. Touchez la carte pour choisir un point.</p>}
      {status === 'error' && <p className="search-state">Recherche indisponible. Touchez la carte pour choisir un point.</p>}
    </div>}
  </div>;
}
