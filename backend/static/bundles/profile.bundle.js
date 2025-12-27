import { ensureStyle } from '../app/dom.js';
import { state, getVal } from '../app/store.js';

const css = `
/* Profile Grid */
.profile-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; max-width: 1000px; }
.data-card { background: white; border-radius: 24px; padding: 24px; border: 1px solid #f1f5f9; box-shadow: var(--card-shadow); transition: all 0.3s var(--ease-spring); cursor: pointer; position: relative; overflow: hidden; }
.data-card:hover { transform: translateY(-6px); box-shadow: 0 12px 24px -4px rgba(0,0,0,0.06); border-color: #e2e8f0; }
.data-card::after { content: "查看详情 →"; position: absolute; right: 24px; bottom: 24px; font-size: 12px; color: #94a3b8; opacity: 0; transition: 0.2s; transform: translateX(10px); }
.data-card:hover::after { opacity: 1; transform: translateX(0); }
.dc-header { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.dc-icon { width: 48px; height: 48px; border-radius: 14px; background: #f8fafc; display: flex; align-items: center; justify-content: center; font-size: 20px; }
.dc-title { font-size: 18px; font-weight: 700; color: #1e293b; }
.dc-item { display: flex; align-items: baseline; gap: 8px; font-size: 14px; color: #475569; margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.dc-item::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: #cbd5e1; flex-shrink: 0; }
`;

const html = `
<div id="view-profile" class="view-section active-view">
  <div class="scrollable-content">
    <div style="margin-bottom:32px;">
      <h2 style="margin:0; font-size:28px; color:#1e293b;">数字孪生画像</h2>
      <p style="color:#64748b; margin-top:8px;">点击卡片探索您的数字生命细节 🧬</p>
    </div>
    <div class="profile-grid">
      <div class="data-card" onclick="openModal('basic')">
        <div class="dc-header"><div class="dc-icon" style="color:#10b981; background:#ecfdf5;">🧬</div><div class="dc-title">生理指标</div></div>
        <div id="profile-basic-list"></div>
      </div>
      <div class="data-card" onclick="openModal('medical')">
        <div class="dc-header"><div class="dc-icon" style="color:#6366f1; background:#e0e7ff;">🛡️</div><div class="dc-title">医学状态</div></div>
        <div id="profile-medical-list"></div>
      </div>
      <div class="data-card" onclick="openModal('lifestyle')">
        <div class="dc-header"><div class="dc-icon" style="color:#f59e0b; background:#fef3c7;">☕</div><div class="dc-title">生活习惯</div></div>
        <div id="profile-lifestyle-list"></div>
      </div>
      <div class="data-card" onclick="openModal('personality')">
        <div class="dc-header"><div class="dc-icon" style="color:#ec4899; background:#fce7f3;">🧠</div><div class="dc-title">性格画像</div></div>
        <div id="profile-personality-list"></div>
      </div>
    </div>
  </div>
</div>
`;

export function mountProfileView(container) {
  ensureStyle('sb-style-profile', css);
  container.insertAdjacentHTML('beforeend', html);
}

export function initProfileView() {
  const data = state.fullProfileData || {};
  const setHTML = (id, htmlText) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = htmlText;
  };

  if (data.basic) setHTML('profile-basic-list', `<div class="dc-item">BMI ${getVal(data.basic.bmi)}</div><div class="dc-item">${getVal(data.basic.height_cm)}cm / ${getVal(data.basic.weight_kg)}kg</div>`);
  if (data.medical) setHTML('profile-medical-list', `<div class="dc-item">${String(getVal(data.medical.diagnosis)).substring(0,10)}...</div><div class="dc-item">${String(getVal(data.medical.glucose_status)).substring(0,10)}...</div>`);
  if (data.lifestyle && data.diet) setHTML('profile-lifestyle-list', `<div class="dc-item">${String(getVal(data.lifestyle.sleep_pattern)).substring(0,12)}...</div><div class="dc-item">${String(getVal(data.diet.takeout_frequency)).substring(0,12)}...</div>`);
  if (data.personality) setHTML('profile-personality-list', `<div class="dc-item">${String(getVal(data.personality.tone_preference)).substring(0,10)}...</div><div class="dc-item">${getVal(data.personality.decision_style)}</div>`);
}
