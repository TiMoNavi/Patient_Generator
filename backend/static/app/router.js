export function createRouter() {
  const titleMap = { overview:'OVERVIEW', health:'HEALTH', diet:'DIET', events:'EVENTS', chat:'DIALOG' };

  function setActiveView(v) {
    document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active-view'));
    document.getElementById('view-' + v)?.classList.add('active-view');
  }
  function setActiveNav(v) {
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.getElementById('nav-' + v)?.classList.add('active');
  }
  function setTitle(v) {
    const el = document.getElementById('current-page-title');
    if (el) el.textContent = titleMap[v] || 'OVERVIEW';
  }

  function switchView(v) { setActiveView(v); setActiveNav(v); setTitle(v); }
  return { switchView };
}
