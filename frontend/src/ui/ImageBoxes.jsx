import React, { useState } from 'react';
import { ImageOff } from 'lucide-react';

/**
 * Photo with the detection boxes drawn over it. boxes: [{ bbox: [x1, y1, x2, y2] in image pixels, label }].
 * The SVG uses the image's natural size as its coordinate system, so boxes stay aligned at any display size.
 */
export function ImageBoxes({ src, alt, boxes = [], maxHeight = 360 }) {
  const [size, setSize] = useState(null);
  const [failed, setFailed] = useState(false);
  if (!src || failed) return <div className="image-missing"><ImageOff aria-hidden="true"/><span>{src ? 'Image indisponible.' : 'Aucune image.'}</span></div>;
  return <figure className="image-boxes" style={{ margin: 0 }}>
    <div className="image-boxes-frame" style={{ maxBlockSize: maxHeight }}>
      <img src={src} alt={alt} onLoad={e => setSize([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])} onError={() => setFailed(true)} style={{ maxBlockSize: maxHeight }}/>
      {size && boxes.length > 0 && <svg viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="none" aria-hidden="true">
        {boxes.map((b, i) => { const [x1, y1, x2, y2] = b.bbox; const stroke = Math.max(2, size[0] / 300); return <g key={i}>
          <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} fill="none" stroke="#c62828" strokeWidth={stroke}/>
          <rect x={x1} y={Math.max(0, y1 - size[0] / 28)} width={Math.min(size[0] - x1, (b.label.length * size[0]) / 70 + 8)} height={size[0] / 28} fill="#c62828"/>
          <text x={x1 + 4} y={Math.max(0, y1 - size[0] / 28) + size[0] / 38} fill="#fff" fontSize={size[0] / 45} fontFamily="IBM Plex Sans, sans-serif">{b.label}</text>
        </g>; })}
      </svg>}
    </div>
    {boxes.length > 0 && <figcaption className="t-xs t-muted">Cadre rouge : zone détectée par le modèle M1 ({boxes.map(b => b.label).join(' ; ')}).</figcaption>}
  </figure>;
}
