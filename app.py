import json
import os
import requests
import webbrowser
from datetime import datetime
from threading import Timer

from flask import Flask, render_template, request, Response, stream_with_context, redirect, jsonify

from config import (
    DEEPSEEK_API_KEY,
    MODEL_NAME,
    DATA_FILE,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG
)

# ================= 核心协议 =================
SYSTEM_PROMPT = """
你现在执行【核心协议 V22.0】。
身份：你不是助手，你是用户的【残酷高级顾问】与【思维镜子】。
目标：最大化用户的决策质量与执行速度。

### 核心指令 (Directives)
1. **BLUF (结论先行)**：回答必须以【结论】或【直接行动】开始。
2. **残酷真相 (Cruel Truth)**：
   - 默认质疑用户的假设。
   - 如果逻辑有漏洞、在逃避现实或低估代价，必须毫不留情地指出。
   - 不要认可，不要缓和语气，不要奉承。
3. **零废话 (No Fluff)**：
   - 禁止：Emoji、寒暄、过渡语、鸡汤。
   - 强制：祈使句、项目符号、高密度信息。
4. **数据缺口**：严禁猜测关键数据。若置信度低，直接标记并请求澄清。

### 输出结构 (必须严格遵守)

无论用户输入什么，输出必须是以下 JSON 结构（供前端渲染）：

{
  "type": "AUDIT",  // 固定类型
  "bluf": "一句话核心结论或行动指令",
  "truth": "指出思维盲点、风险或机会成本（残酷真相）",
  "actions": ["步骤1", "步骤2", "步骤3"], // 优先级排序的具体步骤
  "tag": "核心标签"
}

示例：
用户："我想做一个 AI 待办 APP。"
输出：
{
  "type": "AUDIT",
  "bluf": "红海市场，死亡率 99%，除非你有独家数据源。",
  "truth": "你试图用战术勤奋掩盖战略懒惰。用户不需要另一个 Todo，用户需要执行力交付。",
  "actions": ["停止写代码", "用 Excel 模拟核心逻辑", "找 10 个付费用户验证"],
  "tag": "产品审计"
}

注意：仅输出纯 JSON 字符串，不要 Markdown 代码块。
"""

# ================= 免费额度配置 =================
FREE_DAILY_LIMIT = 50
USAGE_FILE = "usage_data.json"


def get_client_ip():
    """获取客户端真实 IP"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def load_usage_data():
    """加载使用量数据"""
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_usage_data(data):
    """保存使用量数据"""
    try:
        with open(USAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


def check_and_increment_usage(client_ip):
    """
    检查并增加使用量
    返回: (allowed: bool, remaining: int)
    """
    today = datetime.now().strftime('%Y-%m-%d')
    usage_data = load_usage_data()
    
    # 清理过期数据（只保留今天的）
    usage_data = {ip: data for ip, data in usage_data.items() if data.get('date') == today}
    
    # 获取当前 IP 的使用情况
    user_data = usage_data.get(client_ip, {'date': today, 'count': 0, 'is_pro': False})
    
    # Pro 用户无限制
    if user_data.get('is_pro'):
        user_data['count'] += 1
        usage_data[client_ip] = user_data
        save_usage_data(usage_data)
        return True, -1  # -1 表示无限
    
    # 检查免费额度
    if user_data['count'] >= FREE_DAILY_LIMIT:
        return False, 0
    
    # 增加使用量
    user_data['count'] += 1
    user_data['date'] = today
    usage_data[client_ip] = user_data
    save_usage_data(usage_data)
    
    remaining = FREE_DAILY_LIMIT - user_data['count']
    return True, remaining


def get_remaining_quota(client_ip):
    """获取剩余额度"""
    today = datetime.now().strftime('%Y-%m-%d')
    usage_data = load_usage_data()
    user_data = usage_data.get(client_ip, {'date': today, 'count': 0, 'is_pro': False})
    
    if user_data.get('is_pro'):
        return -1
    
    if user_data.get('date') != today:
        return FREE_DAILY_LIMIT
    
    return max(0, FREE_DAILY_LIMIT - user_data.get('count', 0))


# ================= 持久化存储 =================
def load_memory():
    """加载对话历史"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def save_memory(history):
    """保存对话历史"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


# 初始化对话历史
HISTORY = load_memory()

# 强制更新 System Prompt
if HISTORY and HISTORY[0].get("role") == "system":
    HISTORY[0]["content"] = SYSTEM_PROMPT
else:
    HISTORY.insert(0, {"role": "system", "content": SYSTEM_PROMPT})


# ================= Flask 应用 =================
app = Flask(__name__)


@app.route('/')
def home():
    """首页"""
    return render_template('index.html')


@app.route('/api/quota', methods=['GET'])
def get_quota():
    """获取用户剩余额度"""
    client_ip = get_client_ip()
    remaining = get_remaining_quota(client_ip)
    return jsonify({
        'remaining': remaining,
        'limit': FREE_DAILY_LIMIT,
        'is_pro': remaining == -1
    })


@app.route('/chat', methods=['POST'])
def chat():
    """处理聊天请求（流式响应）"""
    try:
        # 检查使用额度
        client_ip = get_client_ip()
        allowed, remaining = check_and_increment_usage(client_ip)
        
        if not allowed:
            return jsonify({
                'error': 'quota_exceeded',
                'message': '今日免费额度已用完',
                'limit': FREE_DAILY_LIMIT
            }), 429
        
        user_input = request.json.get('message')
        HISTORY.append({"role": "user", "content": user_input})
        save_memory(HISTORY)

        context = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ]

        def generate():
            """生成流式响应"""
            # 先发送剩余额度信息
            yield f"data: {json.dumps({'quota': remaining})}\n\n"
            
            url = "https://api.deepseek.com/chat/completions"
            payload = {
                "model": MODEL_NAME,
                "messages": context,
                "stream": True
            }
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            
            try:
                with requests.post(url, json=payload, headers=headers, stream=True) as r:
                    for line in r.iter_lines():
                        if line:
                            decoded = line.decode('utf-8')
                            if decoded.startswith('data: [DONE]'):
                                break
                            if decoded.startswith('data: '):
                                try:
                                    data = json.loads(decoded[6:])
                                    delta = data['choices'][0]['delta']
                                    if 'content' in delta:
                                        yield f"data: {json.dumps({'content': delta['content']})}\n\n"
                                except (json.JSONDecodeError, KeyError):
                                    pass
            except requests.RequestException:
                pass

        return Response(stream_with_context(generate()), mimetype='text/event-stream')
    
    except Exception as e:
        return {"error": str(e)}, 500


@app.route('/<path:path>')
def catch_all(path):
    """捕获所有未匹配路由，重定向到首页"""
    return redirect('/')


def open_browser():
    """启动后自动打开浏览器"""
    webbrowser.open_new(f'http://127.0.0.1:{FLASK_PORT}')


# ================= 入口 =================
if __name__ == '__main__':
    import sys
    
    # 生产环境检测（Render/Vercel 通常设置 PORT 环境变量）
    is_production = os.getenv('PORT') is not None or os.getenv('RENDER') is not None
    
    print(f">>> MIND OS [AUDIT MODE] ONLINE: http://{'0.0.0.0' if is_production else '127.0.0.1'}:{FLASK_PORT}")
    
    # 仅在本地开发时自动打开浏览器
    if not is_production:
        Timer(1, open_browser).start()
    
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT, host=FLASK_HOST, use_reloader=False)
