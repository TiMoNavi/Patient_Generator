import { getUserIdFromUrl, loadUserData } from './store.js';
import { createRouter } from './router.js';

import { mountSidebar, updateSidebar } from '../bundles/sidebar.bundle.js';
import { mountTopbar } from '../bundles/topbar.bundle.js';
import { mountModal } from '../bundles/modal.bundle.js';

import { mountOverviewView, initOverviewView } from '../bundles/overview.bundle.js';
import { mountHealthView, initHealthView } from '../bundles/health.bundle.js';
import { mountDietView, initDietView } from '../bundles/diet.bundle.js';
import { mountEventsView, initEventsView } from '../bundles/events.bundle.js';

// 注意：chat.bundle.js 保持你现有版本，不要动
import { mountChatView, initChatView } from '../bundles/chat.bundle.js';

async function bootstrap() {
  window.Modal = mountModal(document.getElementById('modal-root'));

  mountSidebar(document.getElementById('sidebar-root'));
  mountTopbar(document.getElementById('topbar-root'));

  const vc = document.getElementById('view-container');
  mountOverviewView(vc);
  mountHealthView(vc);
  mountDietView(vc);
  mountEventsView(vc);
  mountChatView(vc);

  const router = createRouter();
  let refreshing = false;
  async function refreshAll() {
    if (refreshing) return;
    refreshing = true;
    const userId = getUserIdFromUrl();
    try {
      await loadUserData(userId);
      initOverviewView();
      initHealthView();
      initDietView();
      initEventsView();
      initChatView();
      updateSidebar();
    } finally {
      refreshing = false;
    }
  }

  window.switchView = async (v) => {
    await refreshAll();
    router.switchView(v);
  };

  await refreshAll();
  router.switchView('overview');
}

bootstrap().catch(err => {
  console.error(err);
  alert('初始化失败：请检查数据接口与静态资源路径。');
});
