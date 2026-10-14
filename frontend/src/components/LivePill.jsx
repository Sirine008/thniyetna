import React from 'react';
export default function LivePill({status='live'}){
  const live=status==='live';
  return <div className={`live-pill ${status}`} title={live?'Connexion SSE active : les nouveaux événements sont reçus automatiquement':'Tentative de reconnexion au flux SSE'}><i/>{live?'Flux connecté':'Reconnexion…'}</div>
}
