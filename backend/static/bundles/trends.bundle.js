import { ensureStyle } from '../app/dom.js';

const css = `
/* Trends - reserved for future */
`;

const html = `
<div id="view-trends" class="view-section">
  <div class="scrollable-content" style="text-align:center; padding-top:100px; color:#94a3b8;">
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>
    <h3>趋势分析模块即将上线</h3>
  </div>
</div>
`;

export function mountTrendsView(container) {
  ensureStyle('sb-style-trends', css);
  container.insertAdjacentHTML('beforeend', html);
}
