import { ensureStyle } from '../app/dom.js';
import { state, getBasic, getEventKeywords } from '../app/store.js';

const css = `
.sidebar {height:100%; width: 300px; background: #fff; border-right: 1px solid #e2e8f0; display:flex; flex-direction:column; padding:22px; }
.logo { display:flex; gap:12px; align-items:center; margin-bottom:22px; }
.logo-icon { width:40px; height:40px; border-radius:12px; background: var(--primary-gradient); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:900; }
.user-card { border:1px solid #f1f5f9; border-radius:18px; padding:14px; box-shadow: var(--card-shadow); }
.user-name { font-weight:900; }
.user-sub { font-size:12px; color:#64748b; margin-top:4px; }
.nav { margin-top:18px; display:flex; flex-direction:column; gap:8px; }
.nav-item { padding:12px; border-radius:14px; cursor:pointer; font-weight:800; color:#475569; }
.nav-item:hover { background:#f1f5f9; }
.nav-item.active { background: var(--primary); color:#fff; box-shadow: 0 10px 22px -6px rgba(79,70,229,.45); }
.tip { margin-top:auto; border-radius:18px; padding:16px; background: var(--primary-gradient); color:#fff; }
@media (max-width: 768px) { .sidebar { display:none; } }
`;

const html = `
<aside class="sidebar">
  <div class="logo">
    <div class="logo-icon">S</div>
    <div>
      <div style="font-weight:900;">SugarBuddy</div>
      <div style="font-size:10px; font-weight:800; color:#4f46e5; letter-spacing:1px;">AI DIGITAL TWIN</div>
    </div>
  </div>

  <div class="user-card">
    <div class="user-name" id="sb-user-name">用户</div>
    <div class="user-sub" id="sb-user-sub">—</div>
    <div class="chips" style="margin-top:10px;" id="sb-user-chips"></div>
  </div>

  <nav class="nav">
    <div class="nav-item active" id="nav-overview" onclick="switchView('overview')">概览</div>
    <div class="nav-item" id="nav-health" onclick="switchView('health')">健康</div>
    <div class="nav-item" id="nav-diet" onclick="switchView('diet')">饮食</div>
    <div class="nav-item" id="nav-events" onclick="switchView('events')">动态</div>
    <div class="nav-item" id="nav-chat" onclick="switchView('chat')">对话</div>
  </nav>

  <div class="tip">
    <div style="font-weight:900; font-size:12px;">提示</div>
    <div style="margin-top:6px; font-size:13px; line-height:1.55;" id="sb-tip-text">加载中…</div>
  </div>
</aside>
`;

export function mountSidebar(root) {
  ensureStyle('sb-style-sidebar', css);
  root.innerHTML = html;
}

export function updateSidebar() {
  const basic = getBasic();
  const name = basic.display_name || '用户';
  const gender = String(basic.gender||'');
  const age = basic.age_range || '—';
  const h = basic.height_cm ? `${basic.height_cm}cm` : '';
  const w = basic.weight_kg ? `${basic.weight_kg}kg` : '';
  const bmi = (basic.bmi != null) ? `BMI ${basic.bmi}` : '';
  const sub = [age, gender, h && w ? `${h}/${w}` : (h||w), bmi].filter(Boolean).join(' · ');

  document.getElementById('sb-user-name').textContent = name;
  document.getElementById('sb-user-sub').textContent = sub || '—';

  const chipsEl = document.getElementById('sb-user-chips');
  const tags = [
    ...(state.profileStatic?.ai_inferred?.tags || []),
    ...(getEventKeywords().slice(0, 4))
  ].slice(0, 6);
  chipsEl.innerHTML = tags.map(t => `<span class="chip">${t}</span>`).join('');

  document.getElementById('sb-tip-text').textContent =
    state.recentEvents?.digest || '建议从“饭后快走 10-15 分钟”和“含糖饮料替换”开始。';
}
