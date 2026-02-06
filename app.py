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


PRODUCT_BRIEF = "产品名：会锐评的AI。链接：mind-os.onrender.com。功能：4位AI审计官同时审视你的想法，指出盲点和逻辑漏洞。每天50次免费。和ChatGPT的区别：这个不会夸你，只会怼你。"

CONTENT_AGENTS = {
    "小红书": f"你是小红书爆款文案写手。根据以下产品信息写一条小红书笔记。要求：300字以内，口语化，有情绪钩子，带话题标签，不要写价格。产品信息：{PRODUCT_BRIEF}",
    "短视频": f"你是短视频编导。根据以下产品信息写一条15-30秒短视频脚本。格式：【画面】+【旁白/文案】+【结尾CTA】。产品信息：{PRODUCT_BRIEF}",
    "知乎": f"你是知乎高赞答主。根据以下产品信息写一条知乎风格的回答（回答问题：有哪些能提升决策能力的AI工具？）。要求：理性、有逻辑、300字以内。产品信息：{PRODUCT_BRIEF}",
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

