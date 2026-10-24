import React from 'react';

// Realtime (SSE) connection state, with text: colour is never the only signal.
export default function LivePill({ status = 'live' }) {
  const live = status === 'live';
  return <span className={`live-state${live ? ' is-live' : ''}`} role="status"
    title={live ? 'Connexion temps réel active : les nouveaux événements sont reçus automatiquement' : 'Tentative de reconnexion au flux temps réel'}>
    <i aria-hidden="true"/>{live ? 'En direct' : 'Reconnexion…'}
  </span>;
}
