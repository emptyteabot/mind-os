import json
import os
import requests
import webbrowser
from datetime import datetime
from threading import Timer
from flask import Flask, render_template, request, Response, stream_with_context, redirect, jsonify
from config import DEEPSEEK_API_KEY, MODEL_NAME, DATA_FILE, FLASK_HOST, FLASK_PORT, FLASK_DEBUG

SYSTEM_PROMPT = """
你是「会锐评的AI」—— 多维度思维审计系统。
你由4个独立审计官组成，必须从4个维度并行评审用户输入：

1. 商业审计官：市场可行性、竞争格局、盈利模型
2. 技术审计官：技术难度、实现成本、时间周期
3. 心理审计官：用户动机、认知偏差、逃避行为
4. 执行审计官：行动路径、优先级、风险预判

规则：
- 结论先行，默认质疑假设
- 禁止安慰、鼓励、废话
- 数据不足时标记而非猜测
- 每个审计官独立给出锐评

输出纯JSON：
{
  "bluf": "一句话核心结论",
  "agents": [
    {"role": "商业", "verdict": "锐评"},
    {"role": "技术", "verdict": "锐评"},
    {"role": "心理", "verdict": "锐评"},
    {"role": "执行", "verdict": "锐评"}
  ],
  "actions": ["步骤1", "步骤2", "步骤3"],
  "tag": "标签"
}

仅输出纯JSON，不要Markdown代码块。
"""

FREE_DAILY_LIMIT = 50
USAGE_FILE = "usage_data.json"


def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def load_usage_data():
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_usage_data(data):
    with open(USAGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_and_increment_usage(client_ip):
    today = datetime.now().strftime('%Y-%m-%d')
    usage_data = load_usage_data()
    usage_data = {ip: d for ip, d in usage_data.items() if d.get('date') == today}
    user_data = usage_data.get(client_ip, {'date': today, 'count': 0, 'is_pro': False})

    if user_data.get('is_pro'):
        user_data['count'] += 1
        usage_data[client_ip] = user_data
        save_usage_data(usage_data)
        return True, -1

    if user_data['count'] >= FREE_DAILY_LIMIT:
        return False, 0

    user_data['count'] += 1
    user_data['date'] = today
    usage_data[client_ip] = user_data
    save_usage_data(usage_data)
    return True, FREE_DAILY_LIMIT - user_data['count']


def get_remaining_quota(client_ip):
    today = datetime.now().strftime('%Y-%m-%d')
    usage_data = load_usage_data()
    user_data = usage_data.get(client_ip, {'date': today, 'count': 0, 'is_pro': False})
    if user_data.get('is_pro'):
        return -1
    if user_data.get('date') != today:
        return FREE_DAILY_LIMIT
    return max(0, FREE_DAILY_LIMIT - user_data.get('count', 0))


def load_memory():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def save_memory(history):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


HISTORY = load_memory()
if HISTORY and HISTORY[0].get("role") == "system":
    HISTORY[0]["content"] = SYSTEM_PROMPT
else:
    HISTORY.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

app = Flask(__name__)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/quota', methods=['GET'])
def get_quota():
    client_ip = get_client_ip()
    remaining = get_remaining_quota(client_ip)
    return jsonify({'remaining': remaining, 'limit': FREE_DAILY_LIMIT, 'is_pro': remaining == -1})


@app.route('/chat', methods=['POST'])
def chat():
    client_ip = get_client_ip()
    allowed, remaining = check_and_increment_usage(client_ip)

    if not allowed:
        return jsonify({'error': 'quota_exceeded'}), 429

    user_input = request.json.get('message')
    HISTORY.append({"role": "user", "content": user_input})
    save_memory(HISTORY)

    context = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input}
    ]

    def generate():
        yield f"data: {json.dumps({'quota': remaining})}\n\n"
        url = "https://api.deepseek.com/chat/completions"
        payload = {"model": MODEL_NAME, "messages": context, "stream": True}
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        with requests.post(url, json=payload, headers=headers, stream=True) as r:
            for line in r.iter_lines():
                if not line:
                    continue
                decoded = line.decode('utf-8')
                if decoded.startswith('data: [DONE]'):
                    break
                if decoded.startswith('data: '):
                    try:
                        data = json.loads(decoded[6:])
                        content = data['choices'][0]['delta'].get('content')
                        if content:
                            yield f"data: {json.dumps({'content': content})}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/<path:path>')
def catch_all(path):
    return redirect('/')


def open_browser():
    webbrowser.open_new(f'http://127.0.0.1:{FLASK_PORT}')


if __name__ == '__main__':
    is_production = os.getenv('PORT') or os.getenv('RENDER')
    print(f">>> 会锐评的AI ONLINE: http://127.0.0.1:{FLASK_PORT}")
    if not is_production:
        Timer(1, open_browser).start()
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT, host=FLASK_HOST, use_reloader=False)
