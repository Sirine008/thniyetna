// npm test: WCAG AA contrast of the colour tokens used for text and marks (src/styles/tokens.css).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const css = fs.readFileSync(new URL('../styles/tokens.css', import.meta.url), 'utf8');
const tokens = Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map(m => [m[1], m[2]]));
const lum = hex => {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => { const [x, y] = [lum(tokens[a]), lum(tokens[b])].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

test('text colours reach 4.5:1 on their backgrounds', () => {
  const pairs = [
    ['c-gray-900', 'c-white'], ['c-gray-600', 'c-white'], ['c-gray-500', 'c-white'], ['c-gray-500', 'c-gray-50'],
    ['c-primary', 'c-white'], ['c-primary', 'c-primary-soft'], ['c-white', 'c-primary'], ['c-white', 'c-primary-hover'],
    ['c-green', 'c-green-bg'], ['c-yellow', 'c-yellow-bg'], ['c-orange', 'c-orange-bg'], ['c-red', 'c-red-bg'],
    ['c-green', 'c-white'], ['c-yellow', 'c-white'], ['c-orange', 'c-white'], ['c-red', 'c-white'],
    ['c-white', 'c-red'], ['c-white', 'c-red-solid'], ['c-white', 'c-gray-900'],
  ];
  for (const [fg, bg] of pairs) assert.ok(ratio(fg, bg) >= 4.5, `${fg} on ${bg}: ${ratio(fg, bg).toFixed(2)}`);
});
test('map lines, markers and the focus ring reach 3:1 on white (non-text contrast)', () => {
  for (const c of ['c-green-solid', 'c-orange-solid', 'c-red-solid', 'c-primary', 'c-focus'])
    assert.ok(ratio(c, 'c-white') >= 3, `${c}: ${ratio(c, 'c-white').toFixed(2)}`);
});
