import { ensureStyle, escapeHtml, fmtDate, safeArray } from '../app/dom.js';
import { state, getEventKeywords, getEventClusters, getEventItems } from '../app/store.js';

const css = `
.h2{margin:0;font-size:28px;font-weight:950;letter-spacing:-.6px;}
.cluster{padding:12px;border-radius:16px;border:1px solid #f1f5f9;background:#fff;cursor:pointer;display:flex;justify-content:space-between;gap:10px;align-items:center;}
.cluster:hover{background:#f8fafc;}
.event{padding:14px;border:1px solid #f1f5f9;border-radius:16px;background:#fff;cursor:pointer;}
.event:hover{background:#f8fafc;}
`;

let filterTag = '';

export function mountEventsView(container){
  ensureStyle('sb-style-events', css);
  container.insertAdjacentHTML('beforeend', `
    <div id="view-events" class="view-section">
      <div class="scrollable-content">
        <div class="h2">动态</div>
        <div class="muted" style="margin-top:8px;line-height:1.55;" id="ev-digest">—</div>

        <div style="margin-top:14px;" class="card">
          <div style="font-weight:900;">关键词</div>
          <div class="muted" style="margin-top:6px;font-size:13px;">点击关键词筛选</div>
          <div class="chips" style="margin-top:10px;" id="ev-kw"></div>
        </div>

        <div style="margin-top:16px;" class="grid two">
          <div class="card">
            <div style="font-weight:900;">主题聚类</div>
            <div class="muted" style="margin-top:6px;font-size:13px;">点击主题筛选</div>
            <div style="margin-top:12px;display:flex;flex-direction:column;gap:10px;" id="ev-clusters"></div>
          </div>
          <div class="card">
            <div style="font-weight:900;">杂谈信息（可选）</div>
            <div class="muted" style="margin-top:6px;font-size:13px;" id="ev-st-sum">—</div>
            <details style="margin-top:10px;">
              <summary style="cursor:pointer;font-weight:900;">展开</summary>
              <div style="margin-top:10px;display:flex;flex-direction:column;gap:10px;" id="ev-st-detail"></div>
            </details>
          </div>
        </div>

        <div style="margin-top:16px;" class="card">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
            <div>
              <div style="font-weight:900;">近期条目</div>
              <div class="muted" style="margin-top:6px;font-size:13px;">倒序；支持筛选</div>
            </div>
            <div class="chip" id="ev-filter" style="display:none;cursor:pointer;"></div>
          </div>
          <div class="hr"></div>
          <div style="display:flex;flex-direction:column;gap:12px;" id="ev-items"></div>
        </div>
      </div>
    </div>
  `);
}

function setFilter(v){
  filterTag = v || '';
  renderFilters();
  renderItems();
}

function renderFilters(){
  const kwEl = document.getElementById('ev-kw');
  const kws = getEventKeywords().slice(0,16);
  kwEl.innerHTML = kws.map(k=>{
    const active = filterTag === k ? 'active' : '';
    return `<span class="chip ${active}" onclick="event.stopPropagation();(${setFilter.toString()})('${escapeHtml(k)}')">${escapeHtml(k)}</span>`;
  }).join('') || `<span class="muted">无关键词</span>`;

  const clEl = document.getElementById('ev-clusters');
  const clusters = getEventClusters().slice().sort((a,b)=>(b.count||0)-(a.count||0)).slice(0,8);
  clEl.innerHTML = clusters.map(c=>{
    const kws = safeArray(c.keywords).slice(0,4).join('、');
    return `
      <div class="cluster" onclick="(${setFilter.toString()})('${escapeHtml(c.topic||'')}')">
        <div>
          <div style="font-weight:900;">${escapeHtml(c.topic||'主题')}</div>
          <div class="muted" style="margin-top:4px;font-size:12px;">${escapeHtml(kws)}</div>
        </div>
        <div style="font-weight:900;color:#4338ca;">${escapeHtml(String(c.count??''))}</div>
      </div>
    `;
  }).join('') || `<div class="muted">无聚类</div>`;

  const filterEl = document.getElementById('ev-filter');
  if (filterTag) {
    filterEl.style.display = 'inline-flex';
    filterEl.textContent = `筛选：${filterTag} ×`;
    filterEl.onclick = ()=>setFilter('');
  } else {
    filterEl.style.display = 'none';
    filterEl.textContent = '';
    filterEl.onclick = null;
  }
}

function renderItems(){
  const itemsEl = document.getElementById('ev-items');
  const items = getEventItems().slice().sort((a,b)=>String(b.ts||'').localeCompare(String(a.ts||'')));
  const filtered = filterTag
    ? items.filter(it => safeArray(it.tags).map(String).some(t=>t.includes(filterTag)) || String(it.text||'').includes(filterTag))
    : items;

  itemsEl.innerHTML = filtered.length ? filtered.map(it=>{
    const payload = JSON.stringify(it).replaceAll('"','&quot;');
    return `
      <div class="event" onclick="Modal.openJson('事件详情', ${payload})">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline;">
          <div class="muted" style="font-size:12px;font-weight:900;">${escapeHtml(fmtDate(it.ts||''))}</div>
          <div class="muted" style="font-size:12px;font-weight:900;">${escapeHtml(it.type||'')}</div>
        </div>
        <div style="margin-top:8px;font-weight:650;line-height:1.55;">${escapeHtml(it.text||'')}</div>
        <div class="chips" style="margin-top:10px;">${safeArray(it.tags).slice(0,8).map(t=>`<span class="chip">${escapeHtml(t)}</span>`).join('')}</div>
      </div>
    `;
  }).join('') : `<div class="muted">无近期条目</div>`;
}

export function initEventsView(){
  document.getElementById('ev-digest').textContent = state.recentEvents?.digest || '暂无动态摘要';

  document.getElementById('ev-st-sum').textContent = state.smalltalk?.summary || '暂无杂谈信息';
  const topics = safeArray(state.smalltalk?.topics);
  document.getElementById('ev-st-detail').innerHTML = topics.length
    ? topics.map(t=>`<div class="card" style="padding:12px;border-radius:16px;"><div style="font-weight:900;">${escapeHtml(t.key||'topic')}</div><div class="muted" style="margin-top:6px;font-size:13px;line-height:1.55;">${escapeHtml(t.text||'')}</div></div>`).join('')
    : `<div class="muted">无更多内容</div>`;

  filterTag = '';
  renderFilters();
  renderItems();
}
