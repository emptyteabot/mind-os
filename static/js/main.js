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

function getTodayKey() {
    return new Date().toISOString().split('T')[0];
}

function getLocalUsage() {
    try {
        const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        if (data.date !== getTodayKey()) return { date: getTodayKey(), count: 0 };
        return data;
    } catch {
        return { date: getTodayKey(), count: 0 };
    }
}

function setLocalUsage(count) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ date: getTodayKey(), count }));
}

function getRemainingQuota() {
    return Math.max(0, FREE_LIMIT - getLocalUsage().count);
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
    } else if (remaining <= 5) {
        quotaDisplay.innerHTML = `<span class="text-red-500">${remaining}/${FREE_LIMIT}</span>`;
    } else {
        quotaDisplay.textContent = `${remaining}/${FREE_LIMIT}`;
    }
}

updateQuotaDisplay(getRemainingQuota());

function showProModal() {
    proModal.classList.remove('hidden');
    proModal.classList.add('flex');
    document.body.style.overflow = 'hidden';
}

function hideProModal() {
    proModal.classList.add('hidden');
    proModal.classList.remove('flex');
    document.body.style.overflow = '';
}

closeModalBtn.addEventListener('click', hideProModal);
proModal.addEventListener('click', (e) => { if (e.target === proModal) hideProModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideProModal(); });

input.addEventListener('focus', () => {
    logoContainer.style.marginTop = '-100px';
    logoContainer.style.opacity = '0';
});

input.addEventListener('input', function() {
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

    const tempId = Date.now();
    renderCard(tempId, { bluf: text, tag: 'INPUT', agents: [], actions: [] }, true);

    input.value = '';
    input.style.height = 'auto';
    loader.style.width = '60%';

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        if (response.status === 429) {
            document.getElementById(`card-${tempId}`)?.remove();
            loader.style.width = '0';
            showProModal();
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullJsonStr = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            for (const line of chunk.split('\n')) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.content) fullJsonStr += data.content;
                    if (data.quota !== undefined) {
                        incrementLocalUsage();
                        updateQuotaDisplay(data.quota);
                    }
                } catch {}
            }
        }

        loader.style.width = '100%';
        setTimeout(() => { loader.style.width = '0'; }, 300);

        try {
            const cleanJson = fullJsonStr.replace(/```json/g, '').replace(/```/g, '').trim();
            const structData = JSON.parse(cleanJson);
            document.getElementById(`card-${tempId}`)?.remove();
            renderCard(Date.now(), structData);
        } catch (e) {
            const tempCard = document.getElementById(`card-${tempId}`);
            if (tempCard) tempCard.innerHTML += `<div class="text-red-500 text-xs mt-2">${fullJsonStr}</div>`;
        }
    } catch {
        loader.style.width = '0';
    }
}

function renderCard(id, data, isTemp = false) {
    const div = document.createElement('div');
    div.id = `card-${id}`;
    div.className = `os-card ${isTemp ? 'opacity-60' : ''}`;

    let agentsHtml = '';
    if (data.agents && data.agents.length > 0) {
        agentsHtml = '<div class="agent-grid">' +
            data.agents.map(a =>
                `<div class="agent-card">
                    <div class="agent-role">${a.role}</div>
                    <div class="agent-verdict">${a.verdict}</div>
                </div>`
            ).join('') + '</div>';
    }

    let actionsHtml = '';
    if (data.actions && data.actions.length > 0) {
        actionsHtml = '<div class="action-list">' +
            data.actions.map(act => `<div class="action-item">${act}</div>`).join('') +
            '</div>';
    }

    div.innerHTML = `
        <div class="flex flex-col gap-2">
            <div class="flex justify-between items-start">
                <h2 class="text-lg font-bold text-black leading-snug">${data.bluf}</h2>
                <span class="tag-badge">${data.tag || 'RAW'}</span>
            </div>
            ${agentsHtml}
            ${actionsHtml}
        </div>
    `;

    feed.insertBefore(div, feed.firstChild);
    lucide.createIcons();
}

sendBtn.onclick = handleSend;
input.onkeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
};

