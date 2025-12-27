import { ensureStyle } from '../app/dom.js';
import { state } from '../app/store.js';

const css = `
/* Timeline */
.timeline-container { max-width: 600px; margin: 0 auto; }
.timeline-item { position: relative; padding-left: 60px; padding-bottom: 40px; }
.timeline-item::before { content: ''; position: absolute; left: 24px; top: 0; bottom: 0; width: 2px; background: #e2e8f0; }
.timeline-item:last-child::before { display: none; }
.tl-icon { position: absolute; left: 0; top: 0; width: 50px; height: 50px; border-radius: 16px; background: white; border: 2px solid #e2e8f0; display: flex; align-items: center; justify-content: center; z-index: 2; color: #64748b; }
.timeline-item.active .tl-icon { background: #4f46e5; border-color: #4f46e5; color: white; }
.timeline-item.completed .tl-icon { background: #ecfdf5; border-color: #10b981; color: #10b981; }
`;

const html = `
<div id="view-timeline" class="view-section">
  <div class="scrollable-content">
    <div class="timeline-container">
      <h2 style="margin-bottom:30px;">健康时钟</h2>
      <div id="timeline-content"></div>
    </div>
  </div>
</div>
`;

export function mountTimelineView(container) {
  ensureStyle('sb-style-timeline', css);
  container.insertAdjacentHTML('beforeend', html);
}

export function initTimelineView() {
  const sched = state.scheduleData || {};
  const el = document.getElementById('timeline-content');
  if (!el || !sched.today_windows) return;

  el.innerHTML = sched.today_windows.map((w, i) => {
    const status = i===1 ? 'active' : (i<1 ? 'completed' : '');
    const icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>';
    return `<div class="timeline-item ${status}"><div class="tl-icon">${icon}</div><div style="background:white; padding:16px; border-radius:12px; border:1px solid #f1f5f9;"><div style="font-size:13px; font-weight:600; color:#94a3b8; margin-bottom:4px;">${w.start} - ${w.end}</div><div style="font-size:15px; font-weight:700; color:#1e293b;">${w.name}</div></div></div>`;
  }).join('');
}
