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
.bubble h3, .bubble h4 { margin: 0 0 8px 0; font-size: 16px; font-weight: 700; line-height: 1.4; }
.bubble ul, .bubble ol { margin: 8px 0 8px 18px; padding: 0; }
.bubble li { margin: 4px 0; }
.bubble blockquote { margin: 8px 0; padding: 8px 12px; border-left: 3px solid #cbd5e1; background: #f8fafc; border-radius: 8px; color: #475569; }
.bubble strong { font-weight: 700; }

/* Markdown readability */
.bubble p { margin: 0 0 10px 0; }
.bubble p:last-child { margin-bottom: 0; }

.bubble a { color: #4f46e5; text-decoration: underline; }
.row.user .bubble a { color: rgba(255,255,255,.95); }

.bubble code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 13px;
}

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

  // 更稳定的 Markdown 规范化：补空行、避免标题/列表粘连
  const normalizeMarkdown = (text) => {
    if (!text) return '';
    let t = text.replace(/\r\n/g, '\n');

    // 标题前后尽量留空行（让渲染更稳定）
    t = t.replace(/([^\n])\n(#{3,4}\s)/g, '$1\n\n$2');
    t = t.replace(/^(#{3,4} .+)\n(?!\n)/gm, '$1\n\n');

    // 列表前留空行（避免“粘连成一段”）
    t = t.replace(/([^\n])\n([-*]\s|\d+\.\s)/g, '$1\n\n$2');

    // 保守拆行：常见中文句末后紧跟结构符时，插入空行
    t = t.replace(/([。！？；])\s*(#{3,4}\s)/g, '$1\n\n$2');
    t = t.replace(/([。！？；])\s*([-*]\s)/g, '$1\n\n$2');
    t = t.replace(/([。！？；])\s*(\d+\.\s)/g, '$1\n\n$2');

    return t.trim();
  };

  // 行级解析器：正确输出 h3/h4、blockquote、ul/ol、p，避免正则乱套
  const renderMarkdown = (raw) => {
    const text = normalizeMarkdown(raw);
    if (!text) return '';

    const escapeHtml = (s) =>
      s.replace(/&/g, '&amp;')
       .replace(/</g, '&lt;')
       .replace(/>/g, '&gt;');

    const escapeAttr = (s) =>
      s.replace(/&/g, '&amp;')
       .replace(/"/g, '&quot;')
       .replace(/'/g, '&#39;')
       .replace(/</g, '&lt;')
       .replace(/>/g, '&gt;');

    const inline = (s) => {
      let out = escapeHtml(s);

      // 粗体
      out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

      // 行内代码
      out = out.replace(/`([^`]+)`/g, '<code>$1</code>');

      // 链接：[label](https://...)
      out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, label, url) => {
        const u = (url || '').trim();
        if (/^https?:\/\//i.test(u)) {
          const safeUrl = escapeAttr(u);
          return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
        }
        return escapeHtml(label);
      });

      return out;
    };

    const lines = text.split('\n');

    let htmlParts = [];
    let para = [];
    let quote = [];

    let listType = null; // 'ul' | 'ol' | null
    let listItems = [];

    const flushPara = () => {
      if (!para.length) return;
      htmlParts.push(`<p>${para.join('<br>')}</p>`);
      para = [];
    };

    const flushQuote = () => {
      if (!quote.length) return;
      htmlParts.push(`<blockquote>${quote.join('<br>')}</blockquote>`);
      quote = [];
    };

    const flushList = () => {
      if (!listType || !listItems.length) {
        listType = null;
        listItems = [];
        return;
      }
      htmlParts.push(`<${listType}>${listItems.join('')}</${listType}>`);
      listType = null;
      listItems = [];
    };

    for (let i = 0; i < lines.length; i++) {
      const lineRaw = lines[i];
      const line = lineRaw.replace(/\s+$/g, ''); // rtrim

      // 空行：结束段落/列表/引用
      if (!line.trim()) {
        flushPara();
        flushList();
        flushQuote();
        continue;
      }

      // 标题：### / ####
      const h = line.match(/^(#{3,4})\s+(.+)$/);
      if (h) {
        flushPara();
        flushList();
        flushQuote();
        const tag = h[1].length === 3 ? 'h3' : 'h4';
        htmlParts.push(`<${tag}>${inline(h[2])}</${tag}>`);
        continue;
      }

      // 引用：> ...
      if (/^\s*>\s?/.test(line)) {
        flushPara();
        flushList();
        const q = line.replace(/^\s*>\s?/, '');
        quote.push(inline(q));
        continue;
      } else {
        // 遇到非引用行，先把之前累计的引用块关掉
        flushQuote();
      }

      // 无序列表：- / *
      if (/^\s*[-*]\s+/.test(line)) {
        flushPara();
        const item = line.replace(/^\s*[-*]\s+/, '');
        if (listType && listType !== 'ul') flushList();
        listType = 'ul';
        listItems.push(`<li>${inline(item)}</li>`);
        continue;
      }

      // 有序列表：1. 2. ...
      if (/^\s*\d+\.\s+/.test(line)) {
        flushPara();
        const item = line.replace(/^\s*\d+\.\s+/, '');
        if (listType && listType !== 'ol') flushList();
        listType = 'ol';
        listItems.push(`<li>${inline(item)}</li>`);
        continue;
      }

      // 普通文本：结束列表，进段落
      flushList();
      para.push(inline(line));
    }

    flushPara();
    flushList();
    flushQuote();

    return htmlParts.join('');
  };

  const appendBubble = (role, text, meta) => {
    const row = document.createElement('div'); row.className = `row ${role}`;
    const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.innerHTML = renderMarkdown(text);
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
    let assistantText = '';
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
            if(txt) {
              assistantText += txt;
              assistantBubble.innerHTML = renderMarkdown(assistantText);
              scrollBottom();
            }
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
