import json
import os
import requests
import webbrowser
from datetime import datetime
from threading import Timer
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, render_template, request, redirect, jsonify
from config import (
    DEEPSEEK_API_KEY, DATA_FILE,
    FLASK_HOST, FLASK_PORT, FLASK_DEBUG
)

FREE_DAILY_LIMIT = 50
USAGE_FILE = "usage_data.json"

AGENTS = {
    "商业": "你是商业分析师。用2句话锐评这个想法的市场可行性。评分1-10。仅输出纯JSON：{\"dim\":\"商业\",\"verdict\":\"你的锐评\",\"score\":数字}",
    "技术": "你是技术架构师。用2句话锐评技术可行性和成本。评分1-10。仅输出纯JSON：{\"dim\":\"技术\",\"verdict\":\"你的锐评\",\"score\":数字}",
    "心理": "你是认知心理学家。用2句话指出决策者的思维盲点。评分1-10。仅输出纯JSON：{\"dim\":\"心理\",\"verdict\":\"你的锐评\",\"score\":数字}",
    "执行": "你是项目管理专家。用2句话评估执行路径，给3个步骤。评分1-10。仅输出纯JSON：{\"dim\":\"执行\",\"verdict\":\"你的锐评\",\"actions\":[\"步骤1\",\"步骤2\",\"步骤3\"],\"score\":数字}"
}

app = Flask(__name__)


def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def load_usage():
    if not os.path.exists(USAGE_FILE):
        return {}
    with open(USAGE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_usage(data):
    with open(USAGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def check_quota(ip):
    today = datetime.now().strftime('%Y-%m-%d')
    usage = load_usage()
    usage = {k: v for k, v in usage.items() if v.get('date') == today}
    user = usage.get(ip, {'date': today, 'count': 0})
    if user.get('date') != today:
        user = {'date': today, 'count': 0}
    if user['count'] >= FREE_DAILY_LIMIT:
        return False, 0
    user['count'] += 1
    usage[ip] = user
    save_usage(usage)
    return True, FREE_DAILY_LIMIT - user['count']


def get_remaining(ip):
    today = datetime.now().strftime('%Y-%m-%d')
    usage = load_usage()
    user = usage.get(ip, {'date': today, 'count': 0})
    if user.get('date') != today:
        return FREE_DAILY_LIMIT
    return max(0, FREE_DAILY_LIMIT - user.get('count', 0))


def call_agent(name, prompt, user_input):
    r = requests.post("https://api.deepseek.com/chat/completions", json={
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input}
        ]
    }, headers={
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    })
    content = r.json()['choices'][0]['message']['content']
    clean = content.replace('```json', '').replace('```', '').strip()
    return json.loads(clean)


def run_agents(user_input):
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(call_agent, n, p, user_input): n
            for n, p in AGENTS.items()
        }
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception:
                pass

    scores = {r['dim']: r['score'] for r in results if 'score' in r}
    avg = round(sum(scores.values()) / len(scores), 1) if scores else 0

    actions = []
    for r in results:
        if 'actions' in r:
            actions = r['actions']
            break

    if avg < 4:
        bluf = f"综合 {avg}/10 — 高风险，建议暂停"
    elif avg < 7:
        bluf = f"综合 {avg}/10 — 有潜力但需验证"
    else:
        bluf = f"综合 {avg}/10 — 可执行"

    return {
        "bluf": bluf,
        "dimensions": results,
        "actions": actions,
        "tag": "多维审计",
        "avg_score": avg
    }


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/quota')
def quota():
    remaining = get_remaining(get_client_ip())
    return jsonify({'remaining': remaining, 'limit': FREE_DAILY_LIMIT})


@app.route('/chat', methods=['POST'])
def chat():
    ip = get_client_ip()
    allowed, remaining = check_quota(ip)
    if not allowed:
        return jsonify({'error': 'quota_exceeded'}), 429

    user_input = request.json.get('message')
    result = run_agents(user_input)
    result['remaining'] = remaining
    return jsonify(result)


@app.route('/<path:path>')
def catch_all(path):
    return redirect('/')


def open_browser():
    webbrowser.open_new(f'http://127.0.0.1:{FLASK_PORT}')


if __name__ == '__main__':
    is_prod = os.getenv('PORT') or os.getenv('RENDER')
    print(f">>> 会锐评的AI [ONLINE]: http://127.0.0.1:{FLASK_PORT}")
    if not is_prod:
        Timer(1, open_browser).start()
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT, host=FLASK_HOST, use_reloader=False)

