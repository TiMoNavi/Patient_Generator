import { ensureStyle } from '../app/dom.js';
import { state } from '../app/store.js';

const css = `
/* Chat */
#view-chat { height: 100%; }
.chat-scroll-area { flex: 1; overflow-y: auto; padding: 20px 10%; display: flex; flex-direction: column; gap: 20px; scroll-behavior: smooth; }
.chat-input-area { flex-shrink: 0; padding: 24px 10%; background: white; border-top: 1px solid #f1f5f9; z-index: 30; }
.input-wrapper { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 16px; padding: 8px 16px; display: flex; align-items: center; transition: all 0.3s; }
.input-wrapper:focus-within { background: white; border-color: #4f46e5; box-shadow: 0 4px 12px rgba(79, 70, 229, 0.1); }
textarea { width: 100%; border: none; background: transparent; resize: none; outline: none; height: 24px; max-height: 100px; font-size: 15px;}
.row { display: flex; width: 100%; }
.row.assistant { justify-content: flex-start; }
.row.user { justify-content: flex-end; }
.bubble { max-width: 80%; padding: 16px; border-radius: 16px; font-size: 15px; line-height: 1.6; word-break: break-word; }
.row.assistant .bubble { background: white; border: 1px solid #e2e8f0; color: #334155; border-bottom-left-radius: 4px; }
.row.user .bubble { background: #4f46e5; color: white; border-bottom-right-radius: 4px; }

/* Proactive Bubble Style */
.bubble.proactive {
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.9) 0%, rgba(248, 250, 252, 0.9) 100%);
  border: 1px solid rgba(79, 70, 229, 0.2);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.08);
}
.bubble.proactive::before {
  content: '✨ 主动关怀';
  display: block; font-size: 11px; font-weight: 700; color: #4f46e5; margin-bottom: 6px; letter-spacing: 0.5px;
}

@media (max-width: 768px) {
  .chat-scroll-area, .chat-input-area { padding-left: 16px; padding-right: 16px; }
}
`;

const html = `
<div id="view-chat" class="view-section">
  <div class="chat-scroll-area" id="chat">
  </div>

  <div class="chat-input-area">
    <form id="composer" class="input-wrapper">
      <textarea id="input" rows="1" placeholder="告诉 SugarBuddy 你的新进展..."></textarea>
      <button id="send" type="submit" style="background:transparent; border:none; color:#4f46e5; cursor:pointer;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
      </button>
    </form>
  </div>
</div>
`;

let initialized = false;

export function mountChatView(container) {
  ensureStyle('sb-style-chat', css);
  container.insertAdjacentHTML('beforeend', html);
}

export function initChatView() {
  if (initialized) return;
  initialized = true;

  const chatEl = document.getElementById('chat');
  const formEl = document.getElementById('composer');
  const inputEl = document.getElementById('input');
  const sendBtn = document.getElementById('send');

  if(!chatEl || !formEl || !inputEl || !sendBtn) return;

  // 清空示例气泡
  chatEl.innerHTML = '';

  const scrollBottom = () => { chatEl.scrollTop = chatEl.scrollHeight; };
  const appendBubble = (role, text, meta) => {
    const row = document.createElement('div'); row.className = `row ${role}`;
    const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = text;
    if (meta && meta.mode === 'proactive') bubble.classList.add('proactive');
    row.appendChild(bubble); chatEl.appendChild(row); scrollBottom();
    return bubble;
  };

  const connectStateStream = () => {
    try {
      const es = new EventSource(`/api/state/stream?user_id=${encodeURIComponent(state.userId || 'u_demo_young_male')}`);
      es.addEventListener('chat_message', (e) => {
        const data = JSON.parse(e.data || '{}');
        if (!data.text) return;
        const meta = data.meta || {};
        // 只展示主动推送，避免被动消息重复
        if (meta.mode === 'proactive') {
          const role = data.role === 'user' ? 'user' : 'assistant';
          appendBubble(role, data.text, meta);
        }
      });
    } catch(e) { console.log('State stream inactive (local mode)'); }
  };

  // --- 对话流式逻辑 ---
  const parseSseBlock = (block) => {
    let eventName = 'message'; let dataLine = '';
    block.split('\n').forEach(line => {
      if(line.trim().startsWith('event:')) eventName = line.trim().slice(6).trim();
      if(line.trim().startsWith('data:')) dataLine = line.trim().slice(5).trim();
    });
    return { event: eventName, dataLine };
  };

  const extractText = (jsonStr) => {
    try { const obj = JSON.parse(jsonStr); return obj.delta || obj.text || obj.answer || ''; } catch { return jsonStr; }
  };

  const streamChat = async (text) => {
    appendBubble('user', text);
    const assistantBubble = appendBubble('assistant', '');
    sendBtn.disabled = true; inputEl.value = '';

    try {
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while(true) {
        const { done, value } = await reader.read();
        if(done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop();

        for(const block of blocks) {
          const { dataLine } = parseSseBlock(block);
          if(dataLine) {
            const txt = extractText(dataLine);
            if(txt) { assistantBubble.textContent += txt; scrollBottom(); }
          }
        }
      }
    } catch(e) {
      assistantBubble.textContent = "[演示模式] 后端未连接。";
    } finally { sendBtn.disabled = false; inputEl.focus(); }
  };

  formEl.addEventListener('submit', (e) => { e.preventDefault(); if(inputEl.value.trim()) streamChat(inputEl.value.trim()); });
  inputEl.addEventListener('keydown', (e) => { if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); formEl.dispatchEvent(new Event('submit')); } });

  connectStateStream();
}
