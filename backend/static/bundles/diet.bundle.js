import { ensureStyle, escapeHtml, safeArray } from '../app/dom.js';
import { state, getDietWeeks } from '../app/store.js';

const css = `
.h2{margin:0;font-size:28px;font-weight:950;letter-spacing:-.6px;}
.week{border:1px solid #f1f5f9;border-radius:18px;overflow:hidden;background:#fff;}
.week-h{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:12px 14px;background:#f8fafc;border-bottom:1px solid #f1f5f9;}
.week-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));}
@media(max-width:1024px){.week-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
.day{border-right:1px solid #f1f5f9;border-bottom:1px solid #f1f5f9;padding:12px;min-height:120px;cursor:pointer;}
.day:hover{background:#f8fafc;}
.date{font-weight:900;font-size:12px;}
.line{margin-top:8px;font-size:12px;color:#475569;line-height:1.45;}
.tag{display:inline-block;font-size:10px;font-weight:900;padding:4px 8px;border-radius:999px;border:1px solid #e2e8f0;background:#f1f5f9;margin-top:8px;margin-right:6px;}
`;

export function mountDietView(container){
  ensureStyle('sb-style-diet', css);
  container.insertAdjacentHTML('beforeend', `
    <div id="view-diet" class="view-section">
      <div class="scrollable-content">
        <div class="h2">饮食</div>
        <div class="muted" style="margin-top:8px;line-height:1.55;" id="dt-summary">—</div>

        <div style="margin-top:14px;" class="grid three">
          <div class="card"><div style="font-weight:900;">含糖饮料</div><div style="margin-top:8px;font-size:22px;font-weight:950;" id="dt-sugar">0</div></div>
          <div class="card"><div style="font-weight:900;">夜宵</div><div style="margin-top:8px;font-size:22px;font-weight:950;" id="dt-late">0</div></div>
          <div class="card"><div style="font-weight:900;">未记录</div><div style="margin-top:8px;font-size:22px;font-weight:950;" id="dt-miss">0</div></div>
        </div>

        <div style="margin-top:16px;display:flex;flex-direction:column;gap:16px;" id="dt-weeks"></div>
      </div>
    </div>
  `);
}

function meals(d){
  return {
    b: d.breakfast ?? d.meals?.breakfast ?? '—',
    l: d.lunch ?? d.meals?.lunch ?? '—',
    di: d.dinner ?? d.meals?.dinner ?? '—'
  };
}

export function initDietView(){
  document.getElementById('dt-summary').textContent = state.diet2w?.summary || '暂无饮食总结';

  const weeks = getDietWeeks().slice(0,2);
  let sugar=0, late=0, miss=0;

  for(const w of weeks){
    for(const d of safeArray(w?.days)){
      const tags = safeArray(d.tags).map(String);
      if (tags.some(t=>t.includes('含糖')||t.includes('奶茶')||t.includes('甜饮'))) sugar++;
      if (tags.some(t=>t.includes('夜宵'))) late++;
      const m = meals(d);
      if ([m.b,m.l,m.di].join(' ').includes('未记录')) miss++;
    }
  }
  document.getElementById('dt-sugar').textContent = String(sugar);
  document.getElementById('dt-late').textContent = String(late);
  document.getElementById('dt-miss').textContent = String(miss);

  const box = document.getElementById('dt-weeks');
  if(!weeks.length){ box.innerHTML = `<div class="card"><div class="muted">无两周饮食数据</div></div>`; return; }

  box.innerHTML = weeks.map((w,idx)=>{
    const days = safeArray(w.days);
    const title = w.week_start ? `周起始：${w.week_start}` : `第 ${idx+1} 周`;
    return `
      <div class="week">
        <div class="week-h">
          <div style="font-weight:900;">${escapeHtml(title)}</div>
          <div class="muted" style="font-size:12px;">点击某天查看细节</div>
        </div>
        <div class="week-grid">
          ${days.map(d=>{
            const m = meals(d);
            const tags = safeArray(d.tags).slice(0,4);
            const payload = JSON.stringify(d).replaceAll('"','&quot;');
            return `
              <div class="day" onclick="Modal.openJson('饮食详情 · ${escapeHtml(d.date||'')}', ${payload})">
                <div class="date">${escapeHtml(d.date||'—')}</div>
                <div class="line">早：${escapeHtml(m.b)}</div>
                <div class="line">午：${escapeHtml(m.l)}</div>
                <div class="line">晚：${escapeHtml(m.di)}</div>
                <div>${tags.map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }).join('');
}
