/**
 * render.js —— DOM 渲染模块
 *
 * 职责：所有 HTML 元素的创建和更新都集中在此模块。
 * 包括：
 *   - 左侧列表渲染（能力列表 / 机会列表）
 *   - 右侧匹配卡片渲染（3 列网格）
 *   - Loading 动画和空状态占位
 */

// ============================================================================
// 工具函数
// ============================================================================

/**
 * 将概述文本截断为指定字符数，超出部分加省略号。
 *
 * 参数:
 *   text   (str): 原始文本
 *   maxLen (int): 最大字符数
 *
 * 返回:
 *   str: 截断后的文本
 */
function truncateText(text, maxLen) {
    if (!text) return '';
    return text.length > maxLen ? text.substring(0, maxLen) + '...' : text;
}


/**
 * 生成百分比进度条 HTML。双色条分别表示领域分和文本分。
 *
 * 参数:
 *   domainScore (float): 领域得分 (0~1)
 *   textScore   (float): 文本得分 (0~1)
 *
 * 返回:
 *   str: 进度条 HTML 字符串
 */
function scoreBar(domainScore, textScore, totalScore) {
    const dPct = (domainScore * 100).toFixed(0);
    const tPct = (textScore   * 100).toFixed(0);
    const totalPct = (totalScore * 100).toFixed(0);
    return `
        <div class="score-bar-container">
            <div class="score-bar">
                <div class="score-bar-domain" style="width:${dPct}%" title="领域分 ${dPct}%"></div>
                <div class="score-bar-text"   style="width:${tPct}%" title="文本分 ${tPct}%"></div>
            </div>
            <span class="score-label">综合 ${totalPct}%</span>
        </div>
    `;
}


// ============================================================================
// 左侧列表渲染
// ============================================================================

/**
 * 渲染左侧列表。
 * 根据当前模式（能力/机会）决定列表项展示的字段。
 * 选中项添加高亮样式。
 */
function renderList() {
    const listEl = document.getElementById('item-list');
    if (!listEl) return;

    const mode  = State.getMode();
    const items = State.getCurrentList();
    const selectedId = State.getSelectedId();

    if (!items || items.length === 0) {
        listEl.innerHTML = '<div class="list-empty">暂无数据</div>';
        return;
    }

    let html = '';
    items.forEach((item, idx) => {
        const isActive = item.id === selectedId;
        const activeCls = isActive ? 'list-item active' : 'list-item';

        if (mode === 'ability') {
            // ---- 能力模式：显示产品名称、企业名称、领域标签 ----
            html += `
                <div class="${activeCls}" data-id="${item.id}" data-mode="ability">
                    <span class="item-index">${idx + 1}</span>
                    <div class="item-info">
                        <div class="item-name">${item.name}</div>
                        <div class="item-meta">${item.company}</div>
                    </div>
                    <span class="item-tag">${item.domain || '未知'}</span>
                </div>
            `;
        } else {
            // ---- 机会模式：显示项目名称、区域、领域标签 ----
            html += `
                <div class="${activeCls}" data-id="${item.id}" data-mode="opportunity">
                    <span class="item-index">${idx + 1}</span>
                    <div class="item-info">
                        <div class="item-name">${item.name}</div>
                        <div class="item-meta">${item.area || ''}</div>
                    </div>
                    <span class="item-tag">${item.domain || '未知'}</span>
                </div>
            `;
        }
    });

    listEl.innerHTML = html;

    // 更新底部计数
    const countEl = document.getElementById('list-count');
    if (countEl) {
        countEl.textContent = `共 ${items.length} 条`;
    }

    // 更新顶栏标题
    const titleEl = document.getElementById('mode-label');
    if (titleEl) {
        titleEl.textContent = mode === 'ability' ? '场景能力列表' : '场景机会列表';
    }
}


// ============================================================================
// 右侧卡片渲染
// ============================================================================

/**
 * 渲染右侧匹配结果卡片（最多 3 列）。
 *
 * 参数:
 *   data ({source, matches}): 后端返回的匹配结果
 */
function renderCards(data) {
    const cardsEl = document.getElementById('match-cards');
    if (!cardsEl) return;

    // 更新选中项的标题展示
    if (data && data.source) {
        const src = data.source;
        const srcTitleEl = document.getElementById('source-title');
        if (srcTitleEl) {
            srcTitleEl.textContent = `${src.name}`;
        }
        const srcSubEl = document.getElementById('source-sub');
        if (srcSubEl) {
            srcSubEl.textContent = src.company || src.domain || '';
        }
    }

    if (!data || !data.matches || data.matches.length === 0) {
        cardsEl.innerHTML = '<div class="cards-empty">未找到匹配项</div>';
        return;
    }

    const rankColors = ['#3B82F6', '#22C55E', '#F59E0B'];  // 第1、2、3名的徽章颜色

    let html = '';
    data.matches.forEach((m, idx) => {
        const t = m.target;
        const rankColor = rankColors[idx] || '#94A3B8';

        if (State.getMode() === 'ability') {
            // ---- 能力→机会：展示场景机会卡片 ----
            html += `
                <div class="match-card">
                    <div class="card-rank" style="background:${rankColor}">#${idx + 1}</div>
                    <div class="card-header">
                        <h3 class="card-title">${t.name}</h3>
                        <span class="card-tag">${t.domain || ''}</span>
                    </div>
                    <p class="card-desc">${truncateText(t.overview, 120)}</p>
                    <div class="card-meta">
                        <span>${t.area || '未知区域'}</span>
                        <span>${truncateText(t.category || '', 20)}</span>
                    </div>
                    ${scoreBar(m.domain_score, m.text_score, m.total_score)}
                </div>
            `;
        } else {
            // ---- 机会→能力：展示场景能力卡片 ----
            html += `
                <div class="match-card">
                    <div class="card-rank" style="background:${rankColor}">#${idx + 1}</div>
                    <div class="card-header">
                        <h3 class="card-title">${t.name}</h3>
                        <span class="card-tag">${t.domain || ''}</span>
                    </div>
                    <p class="card-desc">${truncateText(t.overview, 120)}</p>
                    <div class="card-meta">
                        <span>${t.company || '未知企业'}</span>
                        <span>${truncateText(t.highlight || '', 20)}</span>
                    </div>
                    ${scoreBar(m.domain_score, m.text_score, m.total_score)}
                </div>
            `;
        }
    });

    cardsEl.innerHTML = html;
}


// ============================================================================
// 状态占位渲染
// ============================================================================

/**
 * 显示 Loading 动画（右侧卡片区域）。
 */
function showLoading() {
    const cardsEl = document.getElementById('match-cards');
    if (!cardsEl) return;
    cardsEl.innerHTML = `
        <div class="loading-container">
            <div class="loading-spinner"></div>
            <p>正在匹配...</p>
        </div>
    `;
}


/**
 * 显示空状态提示（右侧卡片区域）。
 */
function showEmpty() {
    const cardsEl = document.getElementById('match-cards');
    if (!cardsEl) return;
    cardsEl.innerHTML = `
        <div class="cards-empty">
            <div class="empty-icon">←</div>
            <p>请从左侧列表中选择一条记录</p>
            <p class="empty-hint">点击后右侧将展示最匹配的 3 条结果</p>
        </div>
    `;
}
