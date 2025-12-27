import { ensureStyle, escapeHtml } from '../app/dom.js';

const css = `
.overlay { position:fixed; inset:0; background:rgba(15,23,42,.4); backdrop-filter: blur(8px);
  display:flex; align-items:center; justify-content:center; opacity:0; pointer-events:none; transition:.2s;
  z-index:1000;
}
.overlay.open { opacity:1; pointer-events:auto; }
.win { width:92%; max-width:720px; max-height:82vh; background:rgba(255,255,255,.92); border-radius:22px; overflow:hidden;
  box-shadow: 0 25px 50px -12px rgba(0,0,0,.25);
}
.head { padding:16px 18px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(0,0,0,.05); }
.body { padding:18px; overflow:auto; }
.kv { display:grid; grid-template-columns:160px 1fr; gap:10px; padding:10px 0; border-bottom:1px solid #f1f5f9; }
.k { font-size:12px; font-weight:900; color:#64748b; text-transform:uppercase; letter-spacing:.08em; }
.v { font-size:13px; font-weight:600; line-height:1.6; }
@media (max-width:640px){ .kv{grid-template-columns:1fr;} }
`;

function toKvHtml(obj) {
  if (!obj || typeof obj !== 'object') return `<div class="muted">无数据</div>`;
  return Object.entries(obj).map(([k,v]) => {
    const vv = (v && typeof v === 'object') ? JSON.stringify(v, null, 2) : String(v ?? '');
    return `<div class="kv"><div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(vv)}</div></div>`;
  }).join('') || `<div class="muted">无数据</div>`;
}

export function mountModal(root) {
  ensureStyle('sb-style-modal', css);
  root.innerHTML = `
    <div class="overlay" id="m-overlay" onclick="closeModal()">
      <div class="win" onclick="event.stopPropagation()">
        <div class="head">
          <div style="font-weight:900;" id="m-title">详情</div>
          <button style="border:none;background:#f1f5f9;border-radius:999px;padding:8px;cursor:pointer;" onclick="closeModal()">关闭</button>
        </div>
        <div class="body" id="m-body"></div>
      </div>
    </div>
  `;

  const overlay = document.getElementById('m-overlay');
  const titleEl = document.getElementById('m-title');
  const bodyEl = document.getElementById('m-body');

  function open(title, html) {
    titleEl.textContent = title || '详情';
    bodyEl.innerHTML = html || `<div class="muted">无内容</div>`;
    overlay.classList.add('open');
  }
  function openJson(title, obj) { open(title, toKvHtml(obj)); }
  function close() { overlay.classList.remove('open'); }

  window.closeModal = close;
  return { open, openJson, close };
}
