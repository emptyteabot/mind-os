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


PRODUCT_BRIEF = "会锐评的AI（mind-os.onrender.com）。4位AI审计官并行审视用户想法。每天50次免费。差异点：ChatGPT夸你，这个怼你。目标人群：25-35岁职场人、创业者、焦虑型决策者。"

CONTENT_AGENTS = {
    "标题": f"""角色：小红书标题优化师，CTR（点击率）是唯一KPI。

任务：为下面的产品生成6个标题。每个标题必须满足：
- 字数12-18字
- 包含1个情绪触发词（后悔/震惊/原来/终于/偷偷/真相）
- 标题本身就是一个完整的故事暗示

6种必用结构（每种1个）：
1. 后悔体："后悔没早点知道，XX竟然可以XX"
2. 反转体："我以为XX，结果XX"  
3. 数字体："用了X天，我的XX完全变了"
4. 身份体："XX人必看｜XX的正确打开方式"
5. 争议体："说句得罪人的话，XX根本不需要XX"
6. 偷窥体："偷偷用了一个月，说说真实感受"

禁止出现：价格、广告感、"推荐"二字
直接输出6个标题，每行一个，前面加对应序号。

产品：{PRODUCT_BRIEF}""",

    "正文": f"""角色：小红书头部博主（调性：真诚分享型，非卖货型）。

写一条可直接发布的小红书笔记，严格遵守以下框架：

【第1段 - 钩子（30字内）】
用"我+具体行为+意外结果"开头。
例："我把辞职计划发给一个AI，被骂醒了。"
禁止用：你有没有/你是不是/大家好

【第2段 - 痛点场景（50-80字）】
写一个具体的生活场景（时间+地点+行为+内心独白）。
例："凌晨2点，又在刷手机逃避明天的汇报。脑子里全是'要不要跳槽''要不要搞副业'，但每次都是想想就算了。"

【第3段 - 转折体验（80-100字）】  
讲使用体验，重点写"预期vs现实"的反差。
必须包含一句AI的原话引用（用引号框起来）。
不要吹，写真实感受，可以带一点吐槽。

【第4段 - 钩子结尾（30字内）】
用一个二选一的问题收尾，引导评论。
例："你觉得做决定前被骂一顿有用吗？"

排版规则：
- 每段之间空一行
- 短句，一句不超过15字
- 禁止："宝子/姐妹/家人们/墙裂推荐/赶紧冲"
- 可用："说实话/讲真/不吹不黑/试了才知道"
- 正文不提价格
- 结尾带6个标签

字数：200-280字
标签选择方向：AI工具/自我提升/决策/职场/思维方式/独立思考

产品：{PRODUCT_BRIEF}""",

    "封面+评论区": f"""角色：小红书运营专家，负责封面文案和评论区预埋。

任务A - 封面文案（3组）：
要求：每组2行，第1行大字5字以内（黑底白字风格），第2行补充语12字以内
- 第1组：制造恐惧（不用会怎样）
- 第2组：激发好奇（用了发现什么）
- 第3组：身份共鸣（什么人在用）
用"---"分隔三组

任务B - 评论区预埋（5条）：
写5条自然的评论，模拟真实用户的口吻：
- 第1条：惊讶型（"卧槽这也太..."）
- 第2条：追问型（问一个具体使用问题）
- 第3条：共鸣型（分享自己类似经历）
- 第4条：质疑型（温和质疑，博主可回复解释）
- 第5条：求链接型（自然地要链接）
每条20字以内，口语化，不要书面语。

禁止出现价格。

产品：{PRODUCT_BRIEF}""",
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

