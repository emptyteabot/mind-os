lucide.createIcons();

const feed = document.getElementById('feed');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const loader = document.getElementById('loader');
const logoContainer = document.getElementById('logo-container');
const proModal = document.getElementById('pro-modal');
const closeModalBtn = document.getElementById('close-modal');
const quotaDisplay = document.getElementById('quota-display');

const STORAGE_KEY = 'ruiping_usage';
const FREE_LIMIT = 50;

function getTodayKey() {
    return new Date().toISOString().split('T')[0];
}

function getLocalUsage() {
    const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (data.date !== getTodayKey()) return { date: getTodayKey(), count: 0 };
    return data;
}

function incrementUsage() {
    const usage = getLocalUsage();
    usage.count++;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(usage));
    return FREE_LIMIT - usage.count;
}

function getRemaining() {
    return Math.max(0, FREE_LIMIT - getLocalUsage().count);
}

function updateQuota(remaining) {
    if (!quotaDisplay) return;
    if (remaining <= 5) {
        quotaDisplay.innerHTML = '<span class="text-red-500">' + remaining + '/' + FREE_LIMIT + '</span>';
    } else {
        quotaDisplay.textContent = remaining + '/' + FREE_LIMIT;
    }
}

updateQuota(getRemaining());

function showModal() {
    proModal.classList.remove('hidden');
    proModal.classList.add('flex');
}

function hideModal() {
    proModal.classList.add('hidden');
    proModal.classList.remove('flex');
}

closeModalBtn.addEventListener('click', hideModal);
proModal.addEventListener('click', function(e) { if (e.target === proModal) hideModal(); });
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') hideModal(); });

input.addEventListener('focus', function() {
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

    if (getRemaining() <= 0) {
        showModal();
        return;
    }

    input.value = '';
    input.style.height = 'auto';
    loader.classList.add('active');

    renderUserCard(text);

    try {
        const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        loader.classList.remove('active');

        if (res.status === 429) {
            showModal();
            return;
        }

        const data = await res.json();
        incrementUsage();
        updateQuota(data.remaining !== undefined ? data.remaining : getRemaining());
        renderAuditCard(data);
    } catch (err) {
        loader.classList.remove('active');
    }
}

function renderUserCard(text) {
    const div = document.createElement('div');
    div.className = 'os-card opacity-60';
    div.innerHTML = '<div class="flex justify-between items-start">' +
        '<h2 class="text-lg font-bold text-black">' + escapeHtml(text) + '</h2>' +
        '<span class="tag-badge">INPUT</span></div>';
    feed.insertBefore(div, feed.firstChild);
}

function renderAuditCard(data) {
    const div = document.createElement('div');
    div.className = 'os-card';

    var dimsHtml = '';
    if (data.dimensions && data.dimensions.length) {
        dimsHtml = '<div class="dims-grid">';
        for (var i = 0; i < data.dimensions.length; i++) {
            var d = data.dimensions[i];
            var cls = d.score >= 7 ? 'score-high' : d.score >= 4 ? 'score-mid' : 'score-low';
            dimsHtml += '<div class="dim-item">' +
                '<div class="dim-header">' +
                '<span class="dim-name">' + d.dim + '</span>' +
                '<span class="dim-score ' + cls + '">' + d.score + '/10</span>' +
                '</div>' +
                '<div class="dim-verdict">' + d.verdict + '</div>' +
                '</div>';
        }
        dimsHtml += '</div>';
    }

    var actionsHtml = '';
    if (data.actions && data.actions.length) {
        actionsHtml = '<div class="action-list">';
        for (var j = 0; j < data.actions.length; j++) {
            actionsHtml += '<div class="action-item">' + data.actions[j] + '</div>';
        }
        actionsHtml += '</div>';
    }

    div.innerHTML = '<div class="flex flex-col gap-3">' +
        '<div class="flex justify-between items-start">' +
        '<h2 class="text-lg font-bold text-black">' + data.bluf + '</h2>' +
        '<span class="tag-badge">' + (data.tag || 'AUDIT') + '</span>' +
        '</div>' +
        dimsHtml +
        actionsHtml +
        '</div>';

    feed.insertBefore(div, feed.firstChild);
    lucide.createIcons();
}

function escapeHtml(text) {
    var d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

sendBtn.onclick = handleSend;
input.onkeydown = function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
};

