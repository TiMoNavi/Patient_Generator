export function ensureStyle(id, cssText) {
  const existing = document.getElementById(id);
  if (existing) return;
  const style = document.createElement('style');
  style.id = id;
  style.textContent = cssText;
  document.head.appendChild(style);
}

export function escapeHtml(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function safeArray(x) { return Array.isArray(x) ? x : []; }

export function fmtDate(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth()+1).padStart(2,'0');
  const dd = String(d.getDate()).padStart(2,'0');
  const hh = String(d.getHours()).padStart(2,'0');
  const mi = String(d.getMinutes()).padStart(2,'0');
  const hasTime = String(ts).includes('T') || !(hh === '00' && mi === '00');
  return hasTime ? `${yyyy}-${mm}-${dd} ${hh}:${mi}` : `${yyyy}-${mm}-${dd}`;
}
