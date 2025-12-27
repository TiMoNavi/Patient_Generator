import { safeArray } from './dom.js';

export const state = {
  userId: 'u_demo_young_male',
  profileStatic: null,
  smalltalk: null,
  healthRecord: null,
  diet2w: null,
  recentEvents: null,
  habits: null
};

export function getUserIdFromUrl(defaultId = 'u_demo_young_male') {
  const url = new URL(window.location.href);
  return url.searchParams.get('user_id') || defaultId;
}

async function fetchJson(url) {
  const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!resp.ok) throw new Error(`GET ${url} failed: ${resp.status}`);
  return await resp.json();
}

export async function loadUserData(userId) {
  state.userId = userId;

  // 1) manifest
  try {
    const manifest = await fetchJson(`/api/local/manifest/${encodeURIComponent(userId)}`);
    const files = manifest?.files || {};
    const base = manifest?.base_path || `/data/users/${encodeURIComponent(userId)}/`;
    const getUrl = (k, defaultName) => {
      const name = files[k] || defaultName;
      if (!name) return null;
      if (String(name).startsWith('/') || String(name).startsWith('http')) return name;
      return base + name;
    };

    const urls = {
      profileStatic: getUrl('profile_static', 'profile_static.json'),
      smalltalk: getUrl('smalltalk', 'smalltalk.json'),
      healthRecord: getUrl('health_record', 'health_record.json'),
      diet2w: getUrl('diet_2w', 'diet_2w.json'),
      recentEvents: getUrl('recent_events', 'recent_events.json'),
      habits: getUrl('habits', 'habits.json')
    };

    const [ps, st, hr, d2, re, hb] = await Promise.all([
      urls.profileStatic ? fetchJson(urls.profileStatic) : null,
      urls.smalltalk ? fetchJson(urls.smalltalk) : null,
      urls.healthRecord ? fetchJson(urls.healthRecord) : null,
      urls.diet2w ? fetchJson(urls.diet2w) : null,
      urls.recentEvents ? fetchJson(urls.recentEvents) : null,
      urls.habits ? fetchJson(urls.habits) : null
    ]);

    state.profileStatic = ps;
    state.smalltalk = st;
    state.healthRecord = hr;
    state.diet2w = d2;
    state.recentEvents = re;
    state.habits = hb;
    return state;
  } catch (_) {}

  // 2) per-module endpoints
  const mod = async (name) => { try { return await fetchJson(`/api/local/${name}/${encodeURIComponent(userId)}`); } catch { return null; } };
  const [ps, st, hr, d2, re, hb] = await Promise.all([
    mod('profile_static'), mod('smalltalk'), mod('health_record'),
    mod('diet_2w'), mod('recent_events'), mod('habits')
  ]);
  if (ps || st || hr || d2 || re || hb) {
    state.profileStatic = ps; state.smalltalk = st; state.healthRecord = hr;
    state.diet2w = d2; state.recentEvents = re; state.habits = hb;
    return state;
  }

  // 3) static files
  const base = `/data/users/${encodeURIComponent(userId)}/`;
  const f = async (file) => { try { return await fetchJson(base + file); } catch { return null; } };
  state.profileStatic = await f('profile_static.json');
  state.smalltalk = await f('smalltalk.json');
  state.healthRecord = await f('health_record.json');
  state.diet2w = await f('diet_2w.json');
  state.recentEvents = await f('recent_events.json');
  state.habits = await f('habits.json');
  return state;
}

// getters（对字段名不强绑定，尽量宽容）
export function getBasic() { return state.profileStatic?.basic || {}; }
export function getGoals() { return state.profileStatic?.health_goal || {}; }

export function getConditions() { return safeArray(state.healthRecord?.conditions); }
export function getLabs() { return safeArray(state.healthRecord?.labs); }
export function getMeds() { return safeArray(state.healthRecord?.medications); }

export function getDietWeeks() { return safeArray(state.diet2w?.weeks); }

export function getEventKeywords() { return safeArray(state.recentEvents?.summary_keywords); }
export function getEventClusters() { return safeArray(state.recentEvents?.clusters); }
export function getEventItems() { return safeArray(state.recentEvents?.items); }

export function getRoutines() { return safeArray(state.habits?.routines); }
export function getRules() { return safeArray(state.habits?.rules); }
