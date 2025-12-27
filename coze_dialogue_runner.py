import os
import time
import json
import argparse
import requests
from datetime import datetime

ENDPOINT_DEFAULT = "https://4mg62nt46x.coze.site/stream_run"

# ===== 这里是你要“依次发送”的用户脚本 =====
TURNS = [
    "你好，我想测一下：我这周空腹血糖基本在6.2~6.6之间，我是不是已经糖尿病了？",
    "我昨晚11点才吃完宵夜（泡面+火腿），今天早上空腹6.6，这个是不是被宵夜影响很大？",
    "我有点搞不懂：空腹偏高，但我餐后2小时有时候才7点多，是不是我测错了？",
    "我买的血糖仪有时候差好多，比如同一滴血测出来5.8和6.4，这正常吗？",
    "我今天早餐吃了两片全麦面包+牛奶，2小时8.9，我现在就很焦虑，我是不是以后碳水都不能吃了？",
    "我朋友说“无糖饮料也会升糖”，我昨天喝了无糖奶茶，餐后反而更高，这到底怎么理解？",
    "我最近晚上总起夜，眼睛也有点模糊，但我又怕自己过度紧张。你觉得我该先做什么检查比较靠谱？",
    "如果我想先不去医院，先在家自测一周，你能给我一个最简单的测量计划吗？（别太复杂）",
]

def load_token() -> str:
    t = os.getenv("COZE_TOKEN")
    if t:
        return t.strip()
    token_file = os.path.join(os.path.dirname(__file__), "token.txt")
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    raise RuntimeError("Missing token: set COZE_TOKEN or create token.txt next to this script.")

def build_payload(project_id: int, text: str) -> dict:
    return {
        "content": {"query": {"prompt": [{"type": "text", "content": {"text": text}}]}},
        "type": "query",
        "project_id": project_id,
    }

def stream_once(endpoint: str, token: str, project_id: int, text: str,
                connect_timeout: int = 10, read_timeout: int = 60, max_seconds: int = 120) -> str:
    """
    发一次 stream_run（SSE），把所有 type=answer 的 content.answer 拼成完整文本返回。
    """
    s = requests.Session()
    s.trust_env = False  # 避免系统代理把请求搞挂（Windows常见）

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Connection": "close",
    }
    payload = build_payload(project_id, text)

    t0 = time.time()
    parts = []

    with s.post(endpoint, headers=headers, json=payload, stream=True,
                timeout=(connect_timeout, read_timeout)) as r:
        if r.status_code != 200:
            try:
                body = r.text
            except Exception:
                body = ""
            raise RuntimeError(f"HTTP {r.status_code} {r.reason}\n{body[:800]}")

        for raw in r.iter_lines(decode_unicode=True, chunk_size=1):
            if time.time() - t0 > max_seconds:
                break
            if not raw:
                continue
            line = raw.strip()
            if not line.startswith("data:"):
                continue

            data_str = line[5:].lstrip()
            if data_str == "[DONE]":
                break

            try:
                evt = json.loads(data_str)
            except Exception:
                continue

            evt_type = evt.get("type")
            content = evt.get("content") or {}

            if evt_type == "answer":
                piece = content.get("answer")
                if isinstance(piece, str) and piece:
                    parts.append(piece)

            if evt_type == "message_end":
                break

    return "".join(parts).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=ENDPOINT_DEFAULT)
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--delay", type=float, default=1.2, help="seconds between turns")
    ap.add_argument("--save", default="transcript.md", help="save transcript markdown path")
    ap.add_argument("--read-timeout", type=int, default=60)
    args = ap.parse_args()

    token = load_token()
    history = []  # list of (role, text)

    # 写文件头
    with open(args.save, "a", encoding="utf-8") as f:
        f.write(f"\n\n# Run {datetime.now().isoformat()}\n")

    for idx, user_text in enumerate(TURNS, start=1):
        print(f"\n==================== TURN {idx} ====================")
        print(f"USER: {user_text}")

        # 把历史拼成对话上下文（如果你Agent本身有记忆，也不影响；这里是“保险”）
        # 注意：只让模型输出“助手”一句话，不要输出“用户：”
        context = ""
        for role, t in history[-10:]:
            context += f"{role}：{t}\n"
        prompt = (
            "请继续一段自然的中文对话，你是血糖管理助手。"
            "回复要像真人说话，给可执行建议，最后只问1个明确问题。\n"
            f"{context}"
            f"用户：{user_text}\n"
            f"助手："
        )

        t0 = time.time()
        try:
            reply = stream_once(
                endpoint=args.endpoint,
                token=token,
                project_id=args.project_id,
                text=prompt,
                read_timeout=args.read_timeout,
            )
        except KeyboardInterrupt:
            print("\n[Interrupted]")
            break

        cost = time.time() - t0
        print(f"ASSISTANT ({cost:.2f}s): {reply}")

        history.append(("用户", user_text))
        history.append(("助手", reply))

        # 追加保存
        with open(args.save, "a", encoding="utf-8") as f:
            f.write(f"\n**Turn {idx}**\n\n- 用户：{user_text}\n- 助手：{reply}\n")

        time.sleep(args.delay)

    print(f"\nDone. Transcript saved to: {args.save}")

if __name__ == "__main__":
    main()
