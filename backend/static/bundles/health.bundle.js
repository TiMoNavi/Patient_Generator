import { ensureStyle, escapeHtml, safeArray } from '../app/dom.js';
import { state, getConditions, getLabs, getMeds, getRoutines, getRules } from '../app/store.js';

const css = `
.h2{margin:0;font-size:28px;font-weight:950;letter-spacing:-.6px;}
.cond{padding:14px;border-radius:16px;border:1px solid #f1f5f9;background:#fff;cursor:pointer;}
.cond:hover{background:#f8fafc;}
.pills{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;}
.pill{font-size:11px;padding:5px 10px;border-radius:999px;border:1px solid #e2e8f0;background:#f1f5f9;font-weight:900;}
.pill.bad{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.25);color:#991b1b;}
.pill.warn{background:rgba(245,158,11,.12);border-color:rgba(245,158,11,.25);color:#92400e;}
.pill.ok{background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.25);color:#065f46;}
.rule{padding:12px;border-radius:16px;border:1px solid #f1f5f9;background:#fff;}
`;

export function mountHealthView(container) {
  ensureStyle('sb-style-health', css);
  container.insertAdjacentHTML('beforeend', `
    <div id="view-health" class="view-section">
      <div class="scrollable-content">
        <div>
          <div class="h2">健康</div>
          <div class="muted" style="margin-top:8px;line-height:1.55;" id="hl-summary">—</div>
        </div>

        <div style="margin-top:16px;" class="grid two">
          <div class="card">
            <div style="font-weight:900;">病症档案</div>
            <div class="muted" style="margin-top:6px;font-size:13px;">点击条目查看详情</div>
            <div style="margin-top:12px;display:flex;flex-direction:column;gap:10px;" id="hl-conds"></div>
          </div>
          <div style="display:flex;flex-direction:column;gap:16px;">
            <div class="card">
              <div style="font-weight:900;">用药</div>
              <div style="margin-top:12px;" id="hl-meds"></div>
            </div>
            <div class="card">
              <div style="font-weight:900;">指标</div>
              <div style="margin-top:12px;" id="hl-labs"></div>
            </div>
          </div>
        </div>

        <div style="margin-top:16px;" class="grid two">
          <div class="card">
            <div style="font-weight:900;">规律作息</div>
            <div style="margin-top:12px;" id="hl-routines"></div>
          </div>
          <div class="card">
            <div style="font-weight:900;">触发规则</div>
            <div class="muted" style="margin-top:6px;font-size:13px;">高风险规则会重点提示</div>
            <div style="margin-top:12px;display:flex;flex-direction:column;gap:10px;" id="hl-rules"></div>
          </div>
        </div>
      </div>
    </div>
  `);
}

function riskCls(rule){
  const r = rule.risk_level || '';
  if (r === 'high') return 'bad';
  if (r === 'medium') return 'warn';
  return 'ok';
}

export function initHealthView() {
  document.getElementById('hl-summary').textContent = state.healthRecord?.summary || '暂无健康总结';

  const conds = getConditions();
  const condEl = document.getElementById('hl-conds');
  condEl.innerHTML = conds.length ? conds.map(c=>{
    const payload = JSON.stringify(c).replaceAll('"','&quot;');
    const pills = [
      c.status && `<span class="pill">${escapeHtml(c.status)}</span>`,
      c.severity && `<span class="pill">${escapeHtml(c.severity)}</span>`,
      c.since && `<span class="pill">${escapeHtml(c.since)}</span>`
    ].filter(Boolean).join('');
    const main = c.main_symptoms || c.notes || c.recommended_actions || '';
    return `
      <div class="cond" onclick="Modal.openJson('${escapeHtml(c.name||'详情')}', ${payload})">
        <div style="font-weight:900;">${escapeHtml(c.name||'未命名')}</div>
        <div class="pills">${pills}</div>
        <div class="muted" style="margin-top:8px;font-size:13px;line-height:1.55;">${escapeHtml(main)}</div>
      </div>
    `;
  }).join('') : `<div class="muted">无病症条目</div>`;

  const meds = getMeds();
  document.getElementById('hl-meds').innerHTML = meds.length ? `
    <table class="table">
      <thead><tr><th>类型</th><th>名称</th><th>剂量</th><th>频次</th></tr></thead>
      <tbody>${meds.map(m=>`
        <tr><td>${escapeHtml(m.type||'')}</td><td>${escapeHtml(m.name||'')}</td><td>${escapeHtml(m.dose||'')}</td><td>${escapeHtml(m.frequency||'')}</td></tr>
      `).join('')}</tbody>
    </table>
  ` : `<div class="muted">无用药记录</div>`;

  const labs = getLabs();
  document.getElementById('hl-labs').innerHTML = labs.length ? `
    <table class="table">
      <thead><tr><th>指标</th><th>值</th><th>日期</th><th>来源</th></tr></thead>
      <tbody>${labs.map(l=>`
        <tr><td>${escapeHtml(l.name||'')}</td><td>${escapeHtml(`${l.value ?? ''}${l.unit||''}`)}</td><td>${escapeHtml(l.date||'')}</td><td>${escapeHtml(l.source||'')}</td></tr>
      `).join('')}</tbody>
    </table>
  ` : `<div class="muted">无指标记录</div>`;

  const routines = getRoutines();
  document.getElementById('hl-routines').innerHTML = routines.length ? `
    <table class="table">
      <thead><tr><th>名称</th><th>模式</th><th>时间/窗口</th><th>稳定性</th></tr></thead>
      <tbody>${routines.map(r=>`
        <tr><td>${escapeHtml(r.name||'')}</td><td>${escapeHtml(r.pattern||'')}</td><td>${escapeHtml(r.time||r.time_window||'')}</td><td>${escapeHtml(r.stability||'')}</td></tr>
      `).join('')}</tbody>
    </table>
  ` : `<div class="muted">无规律数据</div>`;

  const rules = getRules();
  document.getElementById('hl-rules').innerHTML = rules.length ? rules.map(rule=>{
    const cls = riskCls(rule);
    return `
      <div class="rule">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
          <div style="font-weight:900;">${escapeHtml(rule.name||'规则')}</div>
          <span class="pill ${cls}">${escapeHtml(rule.risk_level||'info')}</span>
        </div>
        <div class="muted" style="margin-top:8px;font-size:13px;line-height:1.55;"><b>触发：</b>${escapeHtml(typeof rule.trigger==='string'?rule.trigger:JSON.stringify(rule.trigger||''))}</div>
        <div class="muted" style="margin-top:6px;font-size:13px;line-height:1.55;"><b>影响：</b>${escapeHtml(rule.effect||'—')}</div>
        <div class="muted" style="margin-top:6px;font-size:13px;line-height:1.55;"><b>建议：</b>${escapeHtml(rule.hint||'—')}</div>
      </div>
    `;
  }).join('') : `<div class="muted">无触发规则</div>`;
}
