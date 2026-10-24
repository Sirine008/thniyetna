import React, { useEffect, useId, useRef, useState } from 'react';
import { api } from '../lib/api';

const DEBOUNCE_MS = 250;
// icon per category_key of GET /routing/places (+ the leading suggestions of the « Départ » field)
const ICONS = {
  city: '🏙️', town: '🏙️', village: '🏘️', hamlet: '🏘️', suburb: '📍', neighbourhood: '📍', locality: '📍',
  street: '🛣️', hospital: '🏥', clinic: '🏥', school: '🏫', university: '🎓', townhall: '🏛️',
  administration: '🏛️', police: '🚓', post_office: '📮', station: '🚉', bus_station: '🚌', port: '⚓',
  gps: '⌖', shortcut: '★',
};
export const placeIcon = key => ICONS[key] || '📍';
export const placeDetail = p => [p.category, p.locality, p.name_ar].filter(Boolean).join(' · ');

/** One trip field (« Départ » or « Arrivée ») with autocomplete on the place index of the Bizerte governorate:
 *  debounce, category icon, keyboard navigation (↑ ↓ Entrée Échap), ARIA combobox. `leading` options (e.g.
 *  « Ma position ») are listed first whenever the field has focus. */
export default function PlaceSearch({ label, value, onValueChange, onChoose, onClear, onFocus, leading = [], active = false,
  placeholder = 'Rechercher un lieu, une rue…', badge }) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [status, setStatus] = useState('idle'); // idle | loading | done | error
  const timer = useRef();
  const seq = useRef(0);
  const listId = useId();

  useEffect(() => () => clearTimeout(timer.current), []);

  const search = text => {
    onValueChange(text);
    clearTimeout(timer.current);
    const id = ++seq.current;
    setOpen(true);
    if (text.trim().length < 2) { setResults([]); setStatus('idle'); setActiveIndex(leading.length ? 0 : -1); return; }
    setStatus('loading');
    timer.current = setTimeout(async () => {
      try {
        const rows = await api.places(text.trim(), 8);
        if (id !== seq.current) return; // a newer keystroke is in flight
        setResults(rows); setActiveIndex(rows.length ? leading.length : (leading.length ? 0 : -1)); setStatus('done');
      } catch {
        if (id === seq.current) { setResults([]); setStatus('error'); }
      }
    }, DEBOUNCE_MS);
  };

  const options = [...leading, ...results];
  const choose = option => {
    seq.current++;
    clearTimeout(timer.current);
    setOpen(false); setResults([]); setActiveIndex(-1); setStatus('idle');
    onChoose(option);
  };

  const onKeyDown = e => {
    if (e.key === 'Escape') { setOpen(false); return; }
    if (!options.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActiveIndex(i => (i + 1) % options.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setOpen(true); setActiveIndex(i => (i <= 0 ? options.length - 1 : i - 1)); }
    else if (e.key === 'Enter' && open) { e.preventDefault(); choose(options[Math.max(0, activeIndex)]); }
  };

  const showList = open && (options.length > 0 || status !== 'idle');
  return <div className={`place-search${active ? ' active' : ''}`}>
    {badge && <span className="field-badge" aria-hidden="true">{badge}</span>}
    <label className="field-body"><small>{label}</small>
      <input
        value={value}
        onChange={e => search(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => { onFocus?.(); setOpen(true); setActiveIndex(-1); }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        autoComplete="off"
        enterKeyHint="search"
        role="combobox"
        aria-label={label}
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
      />
    </label>
    {value && <button type="button" className="place-clear" aria-label={`Effacer : ${label}`} onMouseDown={e => e.preventDefault()} onClick={() => { seq.current++; setResults([]); setStatus('idle'); onValueChange(''); onClear?.(); }}>×</button>}
    {showList && <div className="search-results" id={listId} role="listbox" aria-label={label}>
      {options.map((r, i) => <button type="button" key={r.key || `${r.name}-${r.lat}-${r.lon}`} id={`${listId}-${i}`} role="option"
        aria-selected={i === activeIndex} className={`${i === activeIndex ? 'active' : ''}${r.key ? ' leading' : ''}`}
        onMouseDown={e => e.preventDefault()} onMouseEnter={() => setActiveIndex(i)} onClick={() => choose(r)}>
        <span className="place-icon" aria-hidden="true">{placeIcon(r.category_key)}</span>
        <div><b>{r.name}</b><small>{placeDetail(r)}</small></div>
      </button>)}
      {status === 'loading' && !results.length && <p className="search-state">Recherche…</p>}
      {status === 'done' && !results.length && <p className="search-state">Aucun lieu trouvé dans le gouvernorat de Bizerte. Touchez la carte pour choisir un point.</p>}
      {status === 'error' && <p className="search-state">Recherche indisponible. Touchez la carte pour choisir un point.</p>}
    </div>}
  </div>;
}
