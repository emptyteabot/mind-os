import json
import os
import requests
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Timer

from flask import (
    Flask, render_template, request,
    Response, stream_with_context, redirect, jsonify
)
from config import (
    DEEPSEEK_API_KEY, AGENT_MODEL, DATA_FILE,
    FLASK_HOST, FLASK_PORT, FLASK_DEBUG
)

AGENT_PROMPTS = {
    "商业": "你是商业审计官。用2-3句话评估这个想法的商业可行性、市场竞争、盈利模式。直说不废话，纯文本输出。",
    "技术": "你是技术审计官。用2-3句话评估技术实现难度、时间成本、技术风险。直说不废话，纯文本输出。",
    "心理": "你是心理审计官。用2-3句话指出用户的思维盲点、逃避行为、认知偏差。直说不废话，纯文本输出。",
    "执行": "你是执行审计官。给出3个优先级排序的具体行动步骤，每步一句话。纯文本输出。",
}

FREE_DAILY_LIMIT = 50
USAGE_FILE = "usage_data.json"


def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def load_usage():
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_usage(data):
    try:
        with open(USAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


def check_and_increment(ip):
    today = datetime.now().strftime('%Y-%m-%d')
    usage = load_usage()
    usage = {k: v for k, v in usage.items() if v.get('date') == today}
    rec = usage.get(ip, {'date': today, 'count': 0})

    if rec.get('is_pro'):
        rec['count'] += 1
        usage[ip] = rec
        save_usage(usage)
        return True, -1

    if rec['count'] >= FREE_DAILY_LIMIT:
        return False, 0

    rec['count'] += 1
    rec['date'] = today
    usage[ip] = rec
    save_usage(usage)
    return True, FREE_DAILY_LIMIT - rec['count']


def get_remaining(ip):
    today = datetime.now().strftime('%Y-%m-%d')
    usage = load_usage()
    rec = usage.get(ip, {'date': today, 'count': 0})
    if rec.get('is_pro'):
        return -1
    if rec.get('date') != today:
        return FREE_DAILY_LIMIT
    return max(0, FREE_DAILY_LIMIT - rec.get('count', 0))


def call_agent(name, prompt, user_input):
    url = "https://api.deepseek.com/chat/completions"
    payload = {
        "model": AGENT_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input}
        ],
        "max_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        data = r.json()
        return data['choices'][0]['message']['content']
    except Exception:
        return "分析超时"


app = Flask(__name__)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/quota')
def quota():
    ip = get_client_ip()
    remaining = get_remaining(ip)
    return jsonify({'remaining': remaining, 'limit': FREE_DAILY_LIMIT})


@app.route('/chat', methods=['POST'])
def chat():
    ip = get_client_ip()
    allowed, remaining = check_and_increment(ip)

    if not allowed:
        return jsonify({'error': 'quota_exceeded'}), 429

    user_input = request.json.get('message')

    def generate():
        yield f"data: {json.dumps({'quota': remaining})}\n\n"

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(call_agent, name, prompt, user_input): name
                for name, prompt in AGENT_PROMPTS.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                verdict = future.result()
                yield f"data: {json.dumps({'agent': name, 'verdict': verdict})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


PRODUCT_BRIEF = "产品：会锐评的AI（mind-os.onrender.com）。4位AI审计官同时审视你的想法，指出盲点和逻辑漏洞。每天50次免费。核心差异：ChatGPT只会夸你，这个专门怼你。"

XHS_TITLE_PROMPT = f"""你是小红书10万粉博主，擅长写爆款标题。

规则：
- 生成5个不同风格的标题
- 每个标题15字以内
- 必须用以下至少一种公式：
  1. 数字冲击："我用了X天，发现..."
  2. 反差对比："别人在XX，我在XX"
  3. 身份代入："打工人/创业者必看"
  4. 悬念留白："千万别让XX看到这个"
  5. 痛点直击："为什么你的XX总是失败"
- 不要写价格

产品信息：{PRODUCT_BRIEF}

直接输出5个标题，每行一个，不要编号不要解释。"""

XHS_BODY_PROMPT = f"""你是小红书爆款笔记写手，粉丝黏性极高。

写一条完整的小红书笔记正文，严格遵守：

结构：
1. 开头（第1段）：用"我+动作+结果"的叙事句式开头，制造代入感。禁止用"你有没有""你是不是"开头。
2. 痛点放大（第2段）：描述目标用户的真实困境，用具体场景而非抽象描述。
3. 产品体验（第3段）：用第一人称讲述使用体验，重点写"意外感"——预期是X，结果是Y。
4. 结尾钩子（第4段）：留一个悬念或争议点，引导评论区讨论。

语气：
- 像跟闺蜜/兄弟吐槽一样自然
- 短句为主，一句话不超过20字
- 禁止用"宝子""姐妹""家人们"
- 可以用"说实话""不吹不黑""讲真"

字数：200-300字
不要写价格
结尾加5-8个相关话题标签

产品信息：{PRODUCT_BRIEF}"""

XHS_HOOK_PROMPT = f"""你是小红书封面文案专家。

为以下产品生成3组封面文案（用于图片配文）：

要求：
- 每组2行，第1行大字（6字以内），第2行小字（12字以内）
- 第1组：恐惧诉求（不用这个会怎样）
- 第2组：好奇诉求（用了之后发现什么）
- 第3组：身份认同（什么样的人在用）
- 不要写价格

直接输出，不要解释。用"---"分隔三组。

产品信息：{PRODUCT_BRIEF}"""

CONTENT_AGENTS = {
    "标题": XHS_TITLE_PROMPT,
    "正文": XHS_BODY_PROMPT,
    "封面文案": XHS_HOOK_PROMPT,
}


@app.route('/admin')
def admin():
    return render_template('admin.html')


@app.route('/api/generate-content', methods=['POST'])
def generate_content():
    def gen():
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(call_agent, name, prompt, "生成今日推广内容"): name
                for name, prompt in CONTENT_AGENTS.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                content = future.result()
                yield f"data: {json.dumps({'platform': name, 'content': content})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(stream_with_context(gen()), mimetype='text/event-stream')


@app.route('/<path:path>')
def catch_all(path):
    return redirect('/')


def open_browser():
    webbrowser.open_new(f'http://127.0.0.1:{FLASK_PORT}')


if __name__ == '__main__':
    import sys
    is_prod = os.getenv('PORT') or os.getenv('RENDER')
    print(f">>> http://{'0.0.0.0' if is_prod else '127.0.0.1'}:{FLASK_PORT}")
    if not is_prod:
        Timer(1, open_browser).start()
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT, host=FLASK_HOST, use_reloader=False)

