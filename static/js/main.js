lucide.createIcons();

const feed = document.getElementById('feed');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const loader = document.getElementById('loader');
const logoContainer = document.getElementById('logo-container');
const proModal = document.getElementById('pro-modal');
const closeModalBtn = document.getElementById('close-modal');
const quotaDisplay = document.getElementById('quota-display');

const STORAGE_KEY = 'mindos_usage';
const FREE_LIMIT = 50;

const AGENT_LABELS = {
    '商业': {color: '#007AFF', icon: 'briefcase'},
    '技术': {color: '#34C759', icon: 'cpu'},
    '心理': {color: '#FF3B30', icon: 'brain'},
    '执行': {color: '#FF9500', icon: 'list-checks'},
};

function getTodayKey() {
    return new Date().toISOString().split('T')[0];
}

function getLocalUsage() {
    try {
        const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        if (data.date !== getTodayKey()) return {date: getTodayKey(), count: 0};
        return data;
    } catch {
        return {date: getTodayKey(), count: 0};
    }
}

function incrementUsage() {
    const usage = getLocalUsage();
    usage.count++;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(usage));
    return FREE_LIMIT - usage.count;
}

function getRemainingQuota() {
    const usage = getLocalUsage();
    return Math.max(0, FREE_LIMIT - usage.count);
}

function updateQuotaDisplay(n) {
    if (!quotaDisplay) return;
    if (n === -1) {
        quotaDisplay.innerHTML = '<span style="color:#34C759">PRO</span>';
    } else if (n <= 5) {
        quotaDisplay.innerHTML = `<span style="color:#FF3B30">${n}/${FREE_LIMIT}</span>`;
    } else {
        quotaDisplay.textContent = `${n}/${FREE_LIMIT}`;
    }
}

updateQuotaDisplay(getRemainingQuota());

function showProModal() {
    proModal.classList.remove('hidden');
    proModal.classList.add('flex');
}

function hideProModal() {
    proModal.classList.add('hidden');
    proModal.classList.remove('flex');
}

closeModalBtn.addEventListener('click', hideProModal);
proModal.addEventListener('click', e => { if (e.target === proModal) hideProModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideProModal(); });

input.addEventListener('focus', () => {
    logoContainer.style.marginTop = '-100px';
    logoContainer.style.opacity = '0';
});

input.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = this.scrollHeight + 'px';
});

async function handleSend() {
    const text = input.value.trim();
    if (!text) return;

    if (getRemainingQuota() <= 0) {
        showProModal();
        return;
    }

    const cardId = Date.now();
    renderInputCard(cardId, text);

    input.value = '';
    input.style.height = 'auto';
    loader.style.width = '40%';

    try {
        const res = await fetch('/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: text})
        });

        if (res.status === 429) {
            document.getElementById(`card-${cardId}`)?.remove();
            loader.style.width = '0';
            showProModal();
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        const resultCard = createResultCard(cardId);

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            for (const line of chunk.split('\n')) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.quota !== undefined) {
                        incrementUsage();
                        updateQuotaDisplay(data.quota);
                        loader.style.width = '60%';
                    }
                    if (data.agent && data.verdict) {
                        appendAgentResult(resultCard, data.agent, data.verdict);
                        loader.style.width = `${60 + Math.random() * 30}%`;
                    }
                    if (data.done) {
                        loader.style.width = '100%';
                        setTimeout(() => { loader.style.width = '0'; }, 300);
                    }
                } catch {}
            }
        }
    } catch (err) {
        loader.style.width = '0';
    }
}

function renderInputCard(id, text) {
    const div = document.createElement('div');
    div.id = `card-${id}`;
    div.className = 'os-card opacity-60';
    div.innerHTML = `
        <div class="flex justify-between items-start">
            <h2 class="text-lg font-bold text-black leading-snug">${escapeHtml(text)}</h2>
            <span class="tag-badge">INPUT</span>
        </div>`;
    feed.insertBefore(div, feed.firstChild);
}

function createResultCard(inputCardId) {
    const inputCard = document.getElementById(`card-${inputCardId}`);
    if (inputCard) inputCard.classList.remove('opacity-60');

    const div = document.createElement('div');
    div.className = 'os-card';
    div.innerHTML = '<div class="agent-grid"></div>';
    if (inputCard) {
        inputCard.after(div);
    } else {
        feed.insertBefore(div, feed.firstChild);
    }
    return div.querySelector('.agent-grid');
}

function appendAgentResult(container, agentName, verdict) {
    const meta = AGENT_LABELS[agentName] || {color: '#999', icon: 'message-circle'};
    const panel = document.createElement('div');
    panel.className = 'agent-panel fade-in';
    panel.innerHTML = `
        <div class="agent-header">
            <i data-lucide="${meta.icon}" style="width:14px;height:14px;color:${meta.color}"></i>
            <span class="agent-name" style="color:${meta.color}">${agentName}审计</span>
        </div>
        <p class="agent-verdict">${escapeHtml(verdict)}</p>`;
    container.appendChild(panel);
    lucide.createIcons();
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

sendBtn.onclick = handleSend;
input.onkeydown = e => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
};

