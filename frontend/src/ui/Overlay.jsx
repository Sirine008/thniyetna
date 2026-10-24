import React, { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react';
import { CircleAlert, CircleCheck, Info, X } from 'lucide-react';
import { Button } from './Controls';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Escape closes, focus moves inside on open, Tab stays inside, focus returns to the opener on close. */
function useDialog(ref, onClose) {
  useEffect(() => {
    const opener = document.activeElement;
    const node = ref.current;
    (node?.querySelector('[data-autofocus]') || node?.querySelector(FOCUSABLE) || node)?.focus();
    const onKey = event => {
      if (event.key === 'Escape') { event.stopPropagation(); onClose(); return; }
      if (event.key !== 'Tab' || !node) return;
      const items = [...node.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null);
      if (!items.length) return;
      const [first, last] = [items[0], items[items.length - 1]];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); if (opener?.focus) opener.focus(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}

export function SidePanel({ title, subtitle, onClose, children, footer, label }) {
  const ref = useRef();
  const id = useId();
  useDialog(ref, onClose);
  return <>
    <div className="overlay" onClick={onClose} aria-hidden="true"/>
    <aside className="side-panel" role="dialog" aria-modal="true" aria-labelledby={`${id}-t`} aria-label={label} ref={ref} tabIndex={-1}>
      <div className="side-panel-head"><div><h2 id={`${id}-t`} className="section-title">{title}</h2>{subtitle && <div className="t-sm t-muted">{subtitle}</div>}</div>
        <Button variant="ghost" icon={X} aria-label="Fermer le panneau" onClick={onClose}/></div>
      <div className="side-panel-body">{children}</div>
      {footer && <div className="side-panel-foot">{footer}</div>}
    </aside>
  </>;
}

export function Modal({ title, onClose, children, footer, wide }) {
  const ref = useRef();
  const id = useId();
  useDialog(ref, onClose);
  return <div className="modal-wrap" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby={`${id}-t`} ref={ref} tabIndex={-1} style={wide ? { inlineSize: 'min(720px, 100%)' } : undefined}>
      <div className="modal-head"><h2 id={`${id}-t`} className="section-title">{title}</h2></div>
      <div className="modal-body">{children}</div>
      {footer && <div className="modal-foot">{footer}</div>}
    </div>
  </div>;
}

/** Confirmation before an action: the action runs only on « confirmLabel ». */
export function ConfirmModal({ title, children, confirmLabel, danger, loading, onConfirm, onCancel }) {
  return <Modal title={title} onClose={onCancel} footer={<>
    <Button onClick={onCancel} data-autofocus>Annuler</Button>
    <Button variant={danger ? 'danger-solid' : 'primary'} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
  </>}>{children}</Modal>;
}

// ---------- Toasts ----------
const ToastContext = createContext({ push: () => {} });
export const useToast = () => useContext(ToastContext);
const TOAST_ICONS = { success: CircleCheck, error: CircleAlert, info: Info };

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const remove = useCallback(id => setItems(list => list.filter(t => t.id !== id)), []);
  const push = useCallback((message, tone = 'success') => {
    const id = Date.now() + Math.random();
    setItems(list => [...list.slice(-2), { id, message, tone }]);
    setTimeout(() => remove(id), tone === 'error' ? 8000 : 4500);
  }, [remove]);
  return <ToastContext.Provider value={{ push }}>
    {children}
    <div className="toast-region" aria-live="polite" aria-atomic="false">{items.map(t => { const Icon = TOAST_ICONS[t.tone] || Info; return <div className={`toast toast-${t.tone}`} key={t.id} role={t.tone === 'error' ? 'alert' : 'status'}>
      <Icon aria-hidden="true"/><span>{t.message}</span><button type="button" aria-label="Fermer le message" onClick={() => remove(t.id)}><X size={16} aria-hidden="true"/></button>
    </div>; })}</div>
  </ToastContext.Provider>;
}
