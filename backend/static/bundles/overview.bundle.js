import { ensureStyle, escapeHtml, safeArray } from '../app/dom.js';
import { state, getBasic, getGoals, getConditions, getLabs, getDietWeeks, getEventKeywords, getEventClusters, getRules } from '../app/store.js';

const css = `
.hero h2{margin:0;font-size:28px;font-weight:950;letter-spacing:-.6px;}
.hero p{margin:8px 0 0;color:#64748b;line-height:1.55;}
.kpi-row{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px;}
.kpi-pill{background:#fff;border:1px solid #f1f5f9;border-radius:999px;padding:10px 12px;box-shadow:var(--card-shadow);}
.kpi-pill .l{font-size:12px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.08em;}
.kpi-pill .v{font-size:14px;font-weight:900;color:#0f172a;margin-top:4px;}
.split{display:grid;grid-template-columns:1.4fr 1fr;gap:16px;}
@media(max-width:1024px){.split{grid-template-columns:1fr;}}
`;

export function mountOverviewView(container) {
  ensureStyle('sb-style-overview', css);
  container.insertAdjacentHTML('beforeend', `
    <div id="view-overview" class="view-section active-view">
      <div class="scrollable-content">
        <div class="split">
          <div class="hero">
            <h2>概览</h2>
            <p id="ov-health-summary">—</p>
            <div id="ov-redflag" style="margin-top:12px;display:none;"></div>
            <div class="kpi-row" id="ov-kpis"></div>
          </div>

          <div class="card">
            <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
              <div>
                <div style="font-weight:900;">本周目标</div>
                <div class="muted" style="margin-top:6px;font-size:13px;" id="ov-goal">—</div>
              </div>
              <div style="font-weight:900;color:#4338ca;cursor:pointer;" onclick="switchView('health')">查看健康 →</div>
            </div>
            <div class="hr"></div>
            <div style="font-weight:900;">高风险触发器</div>
            <div class="muted" style="margin-top:6px;font-size:13px;" id="ov-risk">—</div>
          </div>
        </div>

        <div style="margin-top:16px;" class="grid three">
          <div class="card clickable" onclick="switchView('health')">
            <div style="font-weight:900;">健康</div>
            <div class="muted" style="margin-top:6px;font-size:13px;" id="ov-health-mini">—</div>
            <div class="hr"></div>
            <div class="muted" style="font-size:13px;" id="ov-lab-mini">—</div>
          </div>
          <div class="card clickable" onclick="switchView('diet')">
            <div style="font-weight:900;">饮食</div>
            <div class="muted" style="margin-top:6px;font-size:13px;" id="ov-diet-mini">—</div>
            <div class="hr"></div>
            <div class="muted" style="font-size:13px;" id="ov-diet-last">—</div>
          </div>
          <div class="card clickable" onclick="switchView('events')">
            <div style="font-weight:900;">动态</div>
            <div class="chips" style="margin-top:10px;" id="ov-kw"></div>
            <div class="hr"></div>
            <div class="muted" style="font-size:13px;" id="ov-events-mini">—</div>
          </div>
        </div>

        <div style="margin-top:16px;" class="card">
          <div style="font-weight:900;">杂谈信息</div>
          <div class="muted" style="margin-top:6px;font-size:13px;" id="ov-st-sum">—</div>
          <details style="margin-top:10px;">
            <summary style="cursor:pointer;font-weight:900;">展开更多</summary>
            <div style="margin-top:10px;display:flex;flex-direction:column;gap:10px;" id="ov-st-detail"></div>
          </details>
        </div>
      </div>
    </div>
  `);
}

function firstRedFlagText() {
  for (const c of getConditions()) {
    const rf = c?.red_flags;
    if (rf && String(rf).trim()) return String(rf);
  }
  return '';
}

function newestDietDayText() {
  const days = [];
  for (const w of getDietWeeks()) for (const d of safeArray(w?.days)) days.push(d);
  days.sort((a,b)=>String(b?.date||'').localeCompare(String(a?.date||'')));
  const d = days[0];
  if (!d) return '暂无近日日记录';
  const b = d.breakfast || d.meals?.breakfast || '—';
  const l = d.lunch || d.meals?.lunch || '—';
  const di = d.dinner || d.meals?.dinner || '—';
  return `${d.date}: 早 ${b} / 午 ${l} / 晚 ${di}`;
}

export function initOverviewView() {
  document.getElementById('ov-health-summary').textContent = state.healthRecord?.summary || '暂无健康总结';

  const rf = firstRedFlagText();
  const rfEl = document.getElementById('ov-redflag');
  if (rf) {
    rfEl.style.display = 'block';
    rfEl.innerHTML = `<div class="notice"><h4>风险提示</h4><p>${escapeHtml(rf)}</p></div>`;
  } else {
    rfEl.style.display = 'none';
    rfEl.innerHTML = '';
  }

  const basic = getBasic();
  const kpis = [];
  const add = (l,v)=>kpis.push(`<div class="kpi-pill"><div class="l">${escapeHtml(l)}</div><div class="v">${escapeHtml(v)}</div></div>`);
  if (basic.bmi != null) add('BMI', String(basic.bmi));
  if (basic.height_cm != null) add('身高', `${basic.height_cm}cm`);
  if (basic.weight_kg != null) add('体重', `${basic.weight_kg}kg`);
  if (basic.age_range) add('年龄段', String(basic.age_range));
  if (basic.gender) add('性别', String(basic.gender));
  document.getElementById('ov-kpis').innerHTML = kpis.join('') || add('数据','未提供');

  const goals = getGoals();
  const text = [
    goals.primary_goal && `主目标：${goals.primary_goal}`,
    goals.secondary_goal && `次目标：${goals.secondary_goal}`,
    safeArray(goals.constraints).length && `约束：${safeArray(goals.constraints).join('、')}`
  ].filter(Boolean).join('；');
  document.getElementById('ov-goal').textContent = text || '未设置目标';

  const rules = getRules();
  const high = rules.find(r => r.risk_level === 'high' || String(r.effect||'').includes('high'));
  document.getElementById('ov-risk').textContent = high ? `${high.name || '高风险触发器'}：${high.hint || '—'}` : '暂无';

  const condMini = getConditions().slice(0,2).map(c => `${c.name||'—'}（${c.status||'—'}）`).join('；');
  document.getElementById('ov-health-mini').textContent = condMini || '暂无病症条目';

  const lab = getLabs()[0];
  document.getElementById('ov-lab-mini').textContent = lab
    ? `关键指标：${lab.name||'—'} ${lab.value ?? ''}${lab.unit||''}（${lab.date||''}）`
    : '关键指标：未提供';

  document.getElementById('ov-diet-mini').textContent = state.diet2w?.summary || '暂无饮食总结';
  document.getElementById('ov-diet-last').textContent = newestDietDayText();

  const kws = getEventKeywords().slice(0,8);
  document.getElementById('ov-kw').innerHTML = kws.map(k=>`<span class="chip">${escapeHtml(k)}</span>`).join('') || `<span class="muted">无关键词</span>`;
  const top = getEventClusters().slice().sort((a,b)=>(b.count||0)-(a.count||0))[0];
  document.getElementById('ov-events-mini').textContent = state.recentEvents?.digest || (top ? `热点：${top.topic||'—'}（${top.count||0}）` : '暂无动态摘要');

  document.getElementById('ov-st-sum').textContent = state.smalltalk?.summary || '暂无杂谈信息';
  const topics = safeArray(state.smalltalk?.topics);
  document.getElementById('ov-st-detail').innerHTML = topics.length
    ? topics.map(t=>`<div class="card" style="padding:12px;border-radius:16px;"><div style="font-weight:900;">${escapeHtml(t.key||'topic')}</div><div class="muted" style="margin-top:6px;font-size:13px;line-height:1.55;">${escapeHtml(t.text||'')}</div></div>`).join('')
    : `<div class="muted">无更多内容</div>`;
}
