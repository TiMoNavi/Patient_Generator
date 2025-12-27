import { ensureStyle } from '../app/dom.js';

const css = `
.topbar { height:70px; padding:0 28px; display:flex; align-items:center; justify-content:space-between;
  border-bottom: 1px solid rgba(0,0,0,0.03); background: rgba(248,250,252,0.82); backdrop-filter: blur(10px);
}
.title { font-size:13px; font-weight:900; letter-spacing:1px; text-transform:uppercase; display:flex; align-items:center; gap:8px; }
.title::before { content:''; width:8px; height:8px; background:#10b981; border-radius:50%; }
.avatar { width:36px; height:36px; border-radius:50%; background:#4f46e5; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:900; }
`;

export function mountTopbar(root) {
  ensureStyle('sb-style-topbar', css);
  root.innerHTML = `
    <header class="topbar">
      <div class="title" id="current-page-title">OVERVIEW</div>
      <div class="avatar">U</div>
    </header>
  `;
}
