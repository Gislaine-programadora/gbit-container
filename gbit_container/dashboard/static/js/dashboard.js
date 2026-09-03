/**
 * GBit Container Dashboard — Frontend Controller
 * v2.0.0 — ProcessEngine-based: native process management, zero Docker/Podman
 */

const REFRESH_INTERVAL = 5000; // 5 seconds
let refreshTimer = null;
let currentPage = 'overview';
let containersCache = [];
let servicesCache = {};

// ── Utility Functions ──────────────────────────────

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + sizes[i];
}

function formatPercent(pct) {
    return (pct || 0).toFixed(1) + '%';
}

async function apiCall(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        const data = await response.json();

        if (!data.success) {
            showToast(data.error || 'Request failed', 'error');
            return null;
        }

        return data.data;
    } catch (err) {
        showToast('Connection error: ' + err.message, 'error');
        return null;
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle',
    };
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="fas ${icons[type]}"></i><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showLoading(text = 'Processing...') {
    const overlay = document.getElementById('loading-overlay');
    overlay.querySelector('.loading-text').textContent = text;
    overlay.classList.add('active');
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.remove('active');
}

// ── Navigation ──────────────────────────────────

function navigateTo(page) {
    currentPage = page;
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    const pageEl = document.getElementById(`page-${page}`);
    const navEl = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (pageEl) pageEl.classList.add('active');
    if (navEl) navEl.classList.add('active');

    const titles = {
        overview: 'Overview',
        containers: 'Containers',
        services: 'Services',
        runtimes: 'Runtimes',
        volumes: 'Data Volumes',
        networks: 'Network',
        apis: 'APIs',
        logs: 'Logs',
        stacks: 'Stack Templates',
        settings: 'Settings',
    };
    document.getElementById('page-title').textContent = titles[page] || page;

    loadPageData(page);
}

function loadPageData(page) {
    switch (page) {
        case 'overview': loadOverview(); break;
        case 'containers': loadContainers(); break;
        case 'services': loadServices(); break;
        case 'runtimes': loadRuntimes(); break;
        case 'volumes': loadVolumes(); break;
        case 'networks': loadNetworks(); break;
        case 'apis': loadApis(); break;
        case 'logs': loadLogServices(); break;
        case 'stacks': loadStacks(); break;
        case 'settings': loadSettings(); break;
    }
}

// ── Data Loaders ──────────────────────────────────

async function loadSystemInfo() {
    const data = await apiCall('/api/system');
    if (!data) return;

    document.getElementById('cpu-percent').textContent = formatPercent(data.cpu_percent);
    document.getElementById('cpu-bar').style.width = data.cpu_percent + '%';

    document.getElementById('mem-percent').textContent = formatPercent(data.memory.percent);
    document.getElementById('mem-bar').style.width = data.memory.percent + '%';

    document.getElementById('disk-percent').textContent = formatPercent(data.disk.percent);
    document.getElementById('disk-bar').style.width = data.disk.percent + '%';

    // Engine status — ProcessEngine is always available
    const statusDot = document.getElementById('engine-status');
    const statusText = document.getElementById('engine-status-text');
    if (data.engine_available) {
        statusDot.className = 'status-dot connected';
        statusText.textContent = `ProcessEngine v${data.engine_version}`.trim();
    } else {
        statusDot.className = 'status-dot disconnected';
        statusText.textContent = 'Engine Offline';
    }
}

async function loadOverview() {
    await loadSystemInfo();

    const [statusData, containersData] = await Promise.all([
        apiCall('/api/status'),
        apiCall('/api/containers'),
    ]);

    if (statusData) {
        document.getElementById('project-name').textContent = statusData.project || '-';
        document.getElementById('project-status').textContent = statusData.status || '-';

        const running = statusData.running || 0;
        const total = statusData.total || 0;
        document.getElementById('services-running').textContent = `${running} / ${total}`;

        const badge = document.getElementById('project-status-badge');
        const statusLabels = { running: 'Running', stopped: 'Stopped', partial: 'Partial', empty: 'No services' };
        badge.textContent = statusLabels[statusData.status] || statusData.status || 'Unknown';
        const badgeClass = statusData.status === 'running' ? 'running'
            : statusData.status === 'partial' ? 'paused'
            : 'stopped';
        badge.className = 'badge ' + badgeClass;
    }

    if (containersData) {
        containersCache = containersData;
        document.getElementById('container-count').textContent = containersData.length;
        renderContainerGrid(containersData);
    } else {
        document.getElementById('container-count').textContent = '0';
        document.getElementById('container-grid').innerHTML = renderEmptyState('No processes found');
    }
}

function renderContainerGrid(containers) {
    const grid = document.getElementById('container-grid');
    if (!containers || containers.length === 0) {
        grid.innerHTML = renderEmptyState('No processes running');
        return;
    }

    grid.innerHTML = containers.map(c => `
        <div class="container-card" data-name="${escapeHtml(c.name || '')}">
            <div class="container-card-header">
                <span class="container-name">${escapeHtml(c.service || c.name || '-')}</span>
                <span class="container-status-dot ${c.status || 'stopped'}"></span>
            </div>
            <div class="container-meta">
                <span>Command: ${escapeHtml(c.command || c.runtime || '-')}</span>
                <span>Status: ${escapeHtml(c.status || '-')}</span>
                ${c.ports ? '<span>Ports: ' + escapeHtml(c.ports) + '</span>' : ''}
                ${c.pid ? '<span>PID: ' + escapeHtml(String(c.pid)) + '</span>' : ''}
            </div>
            <div class="container-actions">
                ${c.status === 'running' ? `
                    <button class="btn btn-sm btn-down" onclick="containerAction('stop','${escapeHtml(c.name)}')"><i class="fas fa-stop"></i></button>
                    <button class="btn btn-sm btn-restart" onclick="containerAction('restart','${escapeHtml(c.name)}')"><i class="fas fa-redo"></i></button>
                    <button class="btn btn-sm btn-secondary" onclick="containerAction('pause','${escapeHtml(c.name)}')"><i class="fas fa-pause"></i></button>
                ` : c.status === 'paused' ? `
                    <button class="btn btn-sm btn-up" onclick="containerAction('unpause','${escapeHtml(c.name)}')"><i class="fas fa-play"></i></button>
                ` : `
                    <button class="btn btn-sm btn-up" onclick="containerAction('start','${escapeHtml(c.name)}')"><i class="fas fa-play"></i></button>
                `}
                <button class="btn btn-sm btn-secondary" onclick="viewLogs('${escapeHtml(c.service || c.name)}')"><i class="fas fa-file-alt"></i></button>
            </div>
        </div>
    `).join('');
}

function renderEmptyState(msg) {
    return `<div class="empty-state"><i class="fas fa-inbox"></i><p>${escapeHtml(msg)}</p></div>`;
}

async function loadContainers() {
    const data = await apiCall('/api/containers');
    if (!data) return;
    containersCache = data;
    renderContainersTable(data);
}

function renderContainersTable(containers, filter = 'all') {
    const tbody = document.getElementById('containers-tbody');
    let filtered = containers;
    if (filter !== 'all') {
        filtered = containers.filter(c => c.status === filter);
    }

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6">${renderEmptyState('No processes match the filter')}</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(c => `
        <tr>
            <td><span class="status-badge ${c.status || 'stopped'}"><span class="dot"></span>${escapeHtml(c.status || 'unknown')}</span></td>
            <td class="mono">${escapeHtml(c.name || '-')}</td>
            <td>${escapeHtml(c.service || '-')}</td>
            <td class="mono">${escapeHtml(c.command || c.runtime || '-')}</td>
            <td class="mono">${escapeHtml(c.ports || '-')}</td>
            <td>
                <div style="display:flex;gap:4px">
                    ${c.status === 'running' ? `
                        <button class="btn btn-sm btn-down" onclick="containerAction('stop','${escapeHtml(c.name)}')" title="Stop"><i class="fas fa-stop"></i></button>
                        <button class="btn btn-sm btn-restart" onclick="containerAction('restart','${escapeHtml(c.name)}')" title="Restart"><i class="fas fa-redo"></i></button>
                    ` : `
                        <button class="btn btn-sm btn-up" onclick="containerAction('start','${escapeHtml(c.name)}')" title="Start"><i class="fas fa-play"></i></button>
                    `}
                </div>
            </td>
        </tr>
    `).join('');
}

async function loadServices() {
    const data = await apiCall('/api/services');
    if (!data) return;
    servicesCache = data;
    renderServicesList(data);
}

function renderServicesList(services) {
    const container = document.getElementById('services-list');
    const keys = Object.keys(services);
    if (keys.length === 0) {
        container.innerHTML = renderEmptyState('No services configured');
        return;
    }

    container.innerHTML = keys.map(name => {
        const svc = services[name];
        return `
            <div class="service-card">
                <div class="service-name"><i class="fas fa-cube"></i> ${escapeHtml(name)}</div>
                <div class="service-detail">
                    <span class="service-detail-key">Command</span>
                    <span class="service-detail-value">${escapeHtml(svc.command || svc.start_cmd || 'custom')}</span>
                </div>
                ${svc.runtime ? `<div class="service-detail"><span class="service-detail-key">Runtime</span><span class="service-detail-value">${escapeHtml(svc.runtime)}</span></div>` : ''}
                ${svc.ports ? `<div class="service-detail"><span class="service-detail-key">Ports</span><span class="service-detail-value">${escapeHtml(svc.ports)}</span></div>` : ''}
                ${svc.environment ? `<div class="service-detail"><span class="service-detail-key">Env Vars</span><span class="service-detail-value">${Object.keys(svc.environment).length}</span></div>` : ''}
                ${svc.volumes ? `<div class="service-detail"><span class="service-detail-key">Volumes</span><span class="service-detail-value">${Array.isArray(svc.volumes) ? svc.volumes.length : Object.keys(svc.volumes).length}</span></div>` : ''}
                ${svc.depends_on ? `<div class="service-detail"><span class="service-detail-key">Depends On</span><span class="service-detail-value">${escapeHtml(Array.isArray(svc.depends_on) ? svc.depends_on.join(', ') : Object.keys(svc.depends_on).join(', '))}</span></div>` : ''}
                ${svc.restart ? `<div class="service-detail"><span class="service-detail-key">Restart</span><span class="service-detail-value">${escapeHtml(svc.restart)}</span></div>` : ''}
            </div>
        `;
    }).join('');
}

async function loadRuntimes() {
    const data = await apiCall('/api/services');
    if (!data) return;
    const tbody = document.getElementById('runtimes-tbody');
    const keys = Object.keys(data);
    if (keys.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3">${renderEmptyState('No runtimes configured')}</td></tr>`;
        return;
    }
    tbody.innerHTML = keys.map(name => {
        const svc = data[name];
        return `<tr>
            <td>${escapeHtml(name)}</td>
            <td class="mono">${escapeHtml(svc.command || svc.start_cmd || 'custom')}</td>
            <td>${escapeHtml(svc.runtime || 'native')}</td>
        </tr>`;
    }).join('');
}

async function loadVolumes() {
    const data = await apiCall('/api/config');
    if (!data || !data.volumes) {
        document.getElementById('volumes-tbody').innerHTML = `<tr><td colspan="2">${renderEmptyState('No volumes defined')}</td></tr>`;
        return;
    }
    const tbody = document.getElementById('volumes-tbody');
    const keys = Object.keys(data.volumes);
    tbody.innerHTML = keys.map(name => {
        const vol = data.volumes[name];
        return `<tr>
            <td class="mono">${escapeHtml(name)}</td>
            <td>${escapeHtml(vol.driver || 'local')}</td>
        </tr>`;
    }).join('');
}

async function loadNetworks() {
    const data = await apiCall('/api/networks');
    const tbody = document.getElementById('networks-tbody');
    const services = data && data.services ? data.services : [];

    if (services.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4">${renderEmptyState('No services defined yet — run gbit-container init')}</td></tr>`;
        return;
    }

    tbody.innerHTML = services.map(svc => {
        const listening = svc.listening;
        const badgeClass = listening ? 'running' : (svc.status === 'running' ? 'paused' : 'stopped');
        const badgeLabel = listening ? 'Listening' : (svc.status === 'running' ? 'Starting...' : 'Down');
        const url = svc.url
            ? `<a href="${escapeHtml(svc.url)}" target="_blank" class="mono" style="color: var(--accent-blue);">${escapeHtml(svc.url)}</a>`
            : '<span class="dim">-</span>';
        return `<tr>
            <td class="mono">${escapeHtml(svc.name)}</td>
            <td class="mono">${svc.port ? escapeHtml(String(svc.port)) : '-'}</td>
            <td>${url}</td>
            <td><span class="status-badge ${badgeClass}"><span class="dot"></span>${badgeLabel}</span></td>
        </tr>`;
    }).join('');
}

let apisCache = [];

async function loadApis() {
    const data = await apiCall('/api/apis');
    const tbody = document.getElementById('apis-tbody');
    const services = data && data.services ? data.services : [];
    apisCache = services;

    // Populate the tester's service dropdown too
    const select = document.getElementById('api-test-service');
    if (select) {
        const current = select.value;
        select.innerHTML = '<option value="">Select service...</option>' +
            services.filter(s => s.port).map(s => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)} (:${s.port})</option>`).join('');
        if (current) select.value = current;
    }

    if (services.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5">${renderEmptyState('No services with a port defined')}</td></tr>`;
        return;
    }

    tbody.innerHTML = services.map(svc => {
        if (!svc.port) {
            return `<tr>
                <td class="mono">${escapeHtml(svc.name)}</td>
                <td class="dim">-</td>
                <td class="dim">no port</td>
                <td class="dim">-</td>
                <td></td>
            </tr>`;
        }

        const root = svc.root;
        let rootCell = '<span class="dim">not running</span>';
        let latencyCell = '<span class="dim">-</span>';
        if (root) {
            const ok = root.ok && root.status_code && root.status_code < 400;
            const cls = ok ? 'running' : 'stopped';
            const label = root.status_code ? `HTTP ${root.status_code}` : (root.error || 'no response');
            rootCell = `<span class="status-badge ${cls}"><span class="dot"></span>${escapeHtml(String(label))}</span>`;
            latencyCell = `${root.elapsed_ms} ms`;
        }

        return `<tr>
            <td class="mono">${escapeHtml(svc.name)}</td>
            <td><a href="${escapeHtml(svc.url)}" target="_blank" class="mono" style="color: var(--accent-blue);">${escapeHtml(svc.url)}</a></td>
            <td>${rootCell}</td>
            <td>${latencyCell}</td>
            <td><button class="btn btn-sm btn-secondary" onclick="prefillApiTest('${escapeHtml(svc.name)}')"><i class="fas fa-flask"></i> Test</button></td>
        </tr>`;
    }).join('');
}

function prefillApiTest(serviceName) {
    const select = document.getElementById('api-test-service');
    if (select) select.value = serviceName;
    switchPage('apis');
    document.getElementById('api-test-path').focus();
}

async function sendApiTest() {
    const service = document.getElementById('api-test-service').value;
    const method = document.getElementById('api-test-method').value;
    const path = document.getElementById('api-test-path').value || '/';
    const resultEl = document.getElementById('api-test-result');

    if (!service) {
        showToast('Select a service first', 'warning');
        return;
    }

    resultEl.textContent = `Sending ${method} ${path} to ${service}...`;

    try {
        const response = await fetch('/api/apis/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ service, method, path }),
        });
        const json = await response.json();

        if (!json.success) {
            resultEl.textContent = `Error: ${json.error || 'request failed'}`;
            return;
        }

        const r = json.data;
        const statusLine = r.status_code
            ? `${r.method || method} ${r.url}  ->  HTTP ${r.status_code}  (${r.elapsed_ms} ms)`
            : `${method} ${r.url}  ->  FAILED (${r.elapsed_ms} ms): ${r.error || 'no response'}`;

        let body = r.body || '';
        try {
            body = JSON.stringify(JSON.parse(body), null, 2);
        } catch (_) { /* not JSON, leave as-is */ }

        resultEl.textContent = `${statusLine}\n\n${body}`;
    } catch (err) {
        resultEl.textContent = `Connection error: ${err.message}`;
    }
}

function loadLogServices() {
    const select = document.getElementById('log-service-select');
    // Populate from cached containers/services
    const names = containersCache.map(c => c.service || c.name).filter(Boolean);
    const svcNames = Object.keys(servicesCache);
    const allNames = [...new Set([...svcNames, ...names])];

    if (allNames.length === 0) {
        select.innerHTML = '<option value="">No services available</option>';
        return;
    }
    select.innerHTML = '<option value="">Select service...</option>' +
        allNames.map(n => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join('');
}

async function loadLogs() {
    const service = document.getElementById('log-service-select').value;
    if (!service) {
        showToast('Please select a service', 'warning');
        return;
    }
    const logContent = document.getElementById('log-content');
    logContent.innerHTML = '<div class="log-line-info">Loading...</div>';

    const data = await apiCall(`/api/action/logs?service=${encodeURIComponent(service)}&tail=300`);
    if (!data) {
        logContent.textContent = 'Failed to load logs';
        return;
    }
    if (data.success === false) {
        logContent.innerHTML = `<div class="log-line-warn">${escapeHtml(data.error || 'No logs found')}</div>`;
        return;
    }

    const lines = Array.isArray(data.logs) ? data.logs : [];
    if (lines.length === 0) {
        logContent.innerHTML = '<div class="log-line-info">(sem logs ainda \u2014 inicie o servico com Up para gerar logs)</div>';
        return;
    }

    // Colorize log lines
    logContent.innerHTML = lines.map(line => {
        let cls = 'log-line-info';
        const lower = line.toLowerCase();
        if (lower.includes('error') || lower.includes('fatal') || lower.includes('critical')) cls = 'log-line-error';
        else if (lower.includes('warn') || lower.includes('warning')) cls = 'log-line-warn';
        return `<div class="${cls}">${escapeHtml(line)}</div>`;
    }).join('');

    logContent.scrollTop = logContent.scrollHeight;
}

async function loadStacks() {
    const data = await apiCall('/api/stacks');
    if (!data) return;
    const grid = document.getElementById('stacks-grid');
    if (data.length === 0) {
        grid.innerHTML = renderEmptyState('No stack templates available');
        return;
    }

    grid.innerHTML = data.map(s => `
        <div class="stack-card">
            <div class="stack-name">${escapeHtml(s.name)}</div>
            <div class="stack-desc">${escapeHtml(s.description)}</div>
            <div class="stack-services">
                ${s.services.map(svc => `<span class="stack-service-tag">${escapeHtml(svc)}</span>`).join('')}
            </div>
        </div>
    `).join('');
}

async function loadSettings() {
    const [sysData, configData] = await Promise.all([
        apiCall('/api/system'),
        apiCall('/api/config'),
    ]);

    if (sysData) {
        const infoEl = document.getElementById('system-info');
        infoEl.innerHTML = [
            ['GBit Version', sysData.gbit_version],
            ['Platform', sysData.platform],
            ['Architecture', sysData.architecture],
            ['Python', sysData.python_version],
            ['Engine', 'ProcessEngine (native)'],
            ['Engine Version', `v${sysData.engine_version}`],
            ['CPU', formatPercent(sysData.cpu_percent)],
            ['Memory', `${formatBytes(sysData.memory.used)} / ${formatBytes(sysData.memory.total)}`],
            ['Disk', `${formatBytes(sysData.disk.used)} / ${formatBytes(sysData.disk.total)}`],
        ].map(([k, v]) => `
            <div class="info-row">
                <span class="info-label">${k}</span>
                <span class="info-value">${escapeHtml(String(v))}</span>
            </div>
        `).join('');
    }

    if (configData) {
        const yaml = document.getElementById('config-yaml');
        yaml.textContent = JSON.stringify(configData, null, 2);
    }
}

// ── Action Handlers ────────────────────────────────────

async function handleAction(endpoint, body = {}, loadingText = 'Processing...') {
    showLoading(loadingText);
    const result = await apiCall(endpoint, {
        method: 'POST',
        body: JSON.stringify(body),
    });
    hideLoading();
    if (result) {
        showToast('Action completed successfully', 'success');
        refresh();
    }
    return result;
}

function containerAction(action, name) {
    const endpoints = {
        start: '/api/action/up',
        stop: '/api/action/stop',
        restart: '/api/action/restart',
        pause: '/api/action/pause',
        unpause: '/api/action/unpause',
    };
    const labels = {
        start: 'Starting process...',
        stop: 'Stopping process...',
        restart: 'Restarting process...',
        pause: 'Pausing process...',
        unpause: 'Unpausing process...',
    };
    handleAction(endpoints[action], { services: [name] }, labels[action]);
}

function viewLogs(service) {
    navigateTo('logs');
    setTimeout(() => {
        document.getElementById('log-service-select').value = service;
        loadLogs();
    }, 200);
}

// ── Refresh & Auto-Update ──────────────────────

function refresh() {
    const btn = document.getElementById('btn-refresh');
    btn.classList.add('spinning');
    loadPageData(currentPage);
    setTimeout(() => btn.classList.remove('spinning'), 1000);
}

function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
        loadPageData(currentPage);
    }, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

// ── Initialization ────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navigateTo(item.dataset.page);
        });
    });

    // Top bar actions
    document.getElementById('btn-up').addEventListener('click', () => {
        handleAction('/api/action/up', {}, 'Starting services...');
    });

    document.getElementById('btn-down').addEventListener('click', () => {
        if (confirm('Are you sure you want to stop all services?')) {
            handleAction('/api/action/down', {}, 'Stopping services...');
        }
    });

    document.getElementById('btn-restart').addEventListener('click', () => {
        handleAction('/api/action/restart', {}, 'Restarting services...');
    });

    document.getElementById('btn-build').addEventListener('click', () => {
        handleAction('/api/action/build', {}, 'Installing dependencies...');
    });

    document.getElementById('btn-refresh').addEventListener('click', refresh);

    // Container filter
    document.getElementById('container-filter').addEventListener('change', (e) => {
        renderContainersTable(containersCache, e.target.value);
    });

    // Logs
    document.getElementById('btn-load-logs').addEventListener('click', loadLogs);
    document.getElementById('btn-refresh-apis').addEventListener('click', loadApis);
    document.getElementById('btn-send-api-test').addEventListener('click', sendApiTest);
    document.getElementById('btn-clear-logs').addEventListener('click', () => {
        document.getElementById('log-content').textContent = '';
    });

    // Build button label update
    const buildBtn = document.getElementById('btn-build');
    if (buildBtn) {
        buildBtn.querySelector('span').textContent = 'Build';
        buildBtn.title = 'Install Dependencies';
    }

    // Sidebar toggle
    document.getElementById('menu-toggle').addEventListener('click', () => {
        const sidebar = document.getElementById('sidebar');
        const main = document.querySelector('.main-content');
        sidebar.classList.toggle('collapsed');
        main.classList.toggle('expanded');
    });

    // Initial load
    navigateTo('overview');
    startAutoRefresh();
});
