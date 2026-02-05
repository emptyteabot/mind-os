// Mind OS - Main JavaScript

// ================= 初始化 =================
lucide.createIcons();

// DOM 元素
const feed = document.getElementById('feed');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const loader = document.getElementById('loader');
const logoContainer = document.getElementById('logo-container');
const proModal = document.getElementById('pro-modal');
const closeModalBtn = document.getElementById('close-modal');
const quotaDisplay = document.getElementById('quota-display');

// ================= 额度管理 =================
const STORAGE_KEY = 'mindos_usage';
const FREE_LIMIT = 50;

function getTodayKey() {
    return new Date().toISOString().split('T')[0];
}

function getLocalUsage() {
    try {
        const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        const today = getTodayKey();
        if (data.date !== today) {
            return { date: today, count: 0 };
        }
        return data;
    } catch {
        return { date: getTodayKey(), count: 0 };
    }
}

function setLocalUsage(count) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
        date: getTodayKey(),
        count: count
    }));
}

function getRemainingQuota() {
    const usage = getLocalUsage();
    return Math.max(0, FREE_LIMIT - usage.count);
}

function incrementLocalUsage() {
    const usage = getLocalUsage();
    usage.count += 1;
    setLocalUsage(usage.count);
    return FREE_LIMIT - usage.count;
}

function updateQuotaDisplay(remaining) {
    if (!quotaDisplay) return;
    
    if (remaining === -1) {
        quotaDisplay.innerHTML = '<span class="text-green-500">PRO</span>';
    } else if (remaining <= 2) {
        quotaDisplay.innerHTML = `<span class="text-red-500">${remaining}/${FREE_LIMIT}</span>`;
    } else {
        quotaDisplay.textContent = `${remaining}/${FREE_LIMIT}`;
    }
}

// 初始化额度显示
updateQuotaDisplay(getRemainingQuota());

// ================= Pro 模态框 =================
function showProModal() {
    if (proModal) {
        proModal.classList.remove('hidden');
        proModal.classList.add('flex');
        document.body.style.overflow = 'hidden';
    }
}

function hideProModal() {
    if (proModal) {
        proModal.classList.add('hidden');
        proModal.classList.remove('flex');
        document.body.style.overflow = '';
    }
}

if (closeModalBtn) {
    closeModalBtn.addEventListener('click', hideProModal);
}

// 点击背景关闭
if (proModal) {
    proModal.addEventListener('click', (e) => {
        if (e.target === proModal) {
            hideProModal();
        }
    });
}

// ESC 关闭
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        hideProModal();
    }
});

// ================= 输入交互 =================
input.addEventListener('focus', () => {
    logoContainer.style.marginTop = '-100px';
    logoContainer.style.opacity = '0';
});

input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

// ================= 发送消息 =================
async function handleSend() {
    const text = input.value.trim();
    if (!text) return;

    // 前端预检查额度
    const remaining = getRemainingQuota();
    if (remaining <= 0) {
        showProModal();
        return;
    }

    // 乐观 UI
    const tempId = Date.now();
    renderCard(tempId, { 
        bluf: text, 
        tag: 'INPUT', 
        truth: '...', 
        actions: [] 
    }, true);

    input.value = '';
    input.style.height = 'auto';
    loader.style.width = '60%';

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        // 检查是否超出额度
        if (response.status === 429) {
            const errorData = await response.json();
            if (errorData.error === 'quota_exceeded') {
                // 移除临时卡片
                const tempCard = document.getElementById(`card-${tempId}`);
                if (tempCard) tempCard.remove();
                
                loader.style.width = '0';
                showProModal();
                return;
            }
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullJsonStr = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.content) fullJsonStr += data.content;
                        if (data.quota !== undefined) {
                            // 更新本地额度并显示
                            incrementLocalUsage();
                            updateQuotaDisplay(data.quota);
                        }
                    } catch (e) {}
                }
            }
        }

        loader.style.width = '100%';
        setTimeout(() => { loader.style.width = '0'; }, 300);

        try {
            // 清理 markdown 标记
            const cleanJson = fullJsonStr.replace(/```json/g, '').replace(/```/g, '').trim();
            const structData = JSON.parse(cleanJson);
            const tempCard = document.getElementById(`card-${tempId}`);
            if (tempCard) tempCard.remove();
            renderCard(Date.now(), structData);
        } catch (e) {
            console.error(e);
            // 降级显示
            const tempCard = document.getElementById(`card-${tempId}`);
            if (tempCard) tempCard.innerHTML += `<div class="text-red-500 text-xs mt-2">Format Error: ${fullJsonStr}</div>`;
        }

    } catch (err) {
        loader.style.width = '0';
        console.error(err);
    }
}

// ================= 渲染卡片 =================
function renderCard(id, data, isTemp=false) {
    const div = document.createElement('div');
    div.id = `card-${id}`;
    div.className = `os-card ${isTemp ? 'opacity-60' : ''}`;

    // 渲染行动列表
    let actionsHtml = '';
    if (data.actions && data.actions.length > 0) {
        actionsHtml = `<div class="action-list">` + 
            data.actions.map(act => `<div class="action-item">${act}</div>`).join('') + 
            `</div>`;
    }

    // 渲染残酷真相
    let truthHtml = '';
    if (data.truth && data.truth !== '...') {
        truthHtml = `<div class="truth-section">${data.truth}</div>`;
    }

    div.innerHTML = `
        <div class="flex flex-col gap-2">
            <div class="flex justify-between items-start">
                <h2 class="text-lg font-bold text-black leading-snug">${data.bluf}</h2>
                <span class="tag-badge">${data.tag || 'RAW'}</span>
            </div>
            ${truthHtml}
            ${actionsHtml}
        </div>
    `;

    feed.insertBefore(div, feed.firstChild);
    lucide.createIcons();
}

// ================= 事件绑定 =================
sendBtn.onclick = handleSend;
input.onkeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
};
