/**
 * render.js —— DOM 渲染模块 (v2)
 *
 * 职责：所有 HTML 元素的创建和更新都集中在此模块。
 * 包括：
 *   - 左侧列表渲染（能力列表 / 机会列表）
 *   - 右侧匹配结果卡片（v2：字段对照表 + 领域匹配详情 + 文本重叠关键词 + 明细面板）
 *   - 参数面板渲染
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
 * 将多行文本（含 \n）渲染为带换行的 HTML（用 <br> 替换 \n）。
 *
 * 参数:
 *   text (str): 可能含 \n 的文本
 *
 * 返回:
 *   str: HTML 安全字符串
 */
function nl2br(text) {
    if (!text) return '';
    // 先做 HTML 转义
    const escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    return escaped.replace(/\n/g, '<br>');
}


/**
 * 生成百分比进度条（领域分 + 文本分 双色 + 总分标签）。
 *
 * 参数:
 *   domainScore (float): 领域得分 (0~1)
 *   textScore   (float): 文本得分 (0~1)
 *   totalScore  (float): 综合得分 (0~1)
 *   dw          (float): 领域权重（用于标签显示）
 *   tw          (float): 文本权重（用于标签显示）
 *
 * 返回:
 *   str: 进度条 HTML 字符串
 */
function scoreBar(domainScore, textScore, totalScore, dw, tw) {
    const dPct = (domainScore * dw * 100).toFixed(0);
    const tPct = (textScore   * tw * 100).toFixed(0);
    const totalPct = (totalScore * 100).toFixed(1);
    return `
        <div class="score-bar-container">
            <div class="score-bar">
                <div class="score-bar-domain" style="width:${dPct}%" title="领域贡献 ${dPct}% (原始分 ${(domainScore*100).toFixed(0)}% × 权重 ${(dw*100).toFixed(0)}%)"></div>
                <div class="score-bar-text"   style="width:${tPct}%" title="文本贡献 ${tPct}% (原始分 ${(textScore*100).toFixed(0)}% × 权重 ${(tw*100).toFixed(0)}%)"></div>
            </div>
            <span class="score-label">综合 <strong>${totalPct}%</strong></span>
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
// 参数面板渲染
// ============================================================================

/**
 * 在右侧面板顶部渲染匹配参数信息条。
 * 展示当前使用的权重、TopN、文本截取长度。
 *
 * 参数:
 *   config (dict): {domain_weight, text_weight, top_n, text_max_length}
 */
function renderConfigPanel(config) {
    const panelEl = document.getElementById('config-panel');
    if (!panelEl) return;
    if (!config) {
        panelEl.innerHTML = '';
        return;
    }

    const dw = (config.domain_weight * 100).toFixed(0);
    const tw = (config.text_weight   * 100).toFixed(0);

    panelEl.innerHTML = `
        <div class="config-panel-inner">
            <span class="config-panel-title">⚙ 匹配参数</span>
            <span class="config-item">领域权重 <strong>${dw}%</strong></span>
            <span class="config-sep">|</span>
            <span class="config-item">文本权重 <strong>${tw}%</strong></span>
            <span class="config-sep">|</span>
            <span class="config-item">返回 Top <strong>${config.top_n}</strong></span>
            <span class="config-sep">|</span>
            <span class="config-item">文本截取 <strong>${config.text_max_length}</strong> 字</span>
        </div>
    `;
}


// ============================================================================
// 右侧卡片渲染 (v2：详细匹配明细)
// ============================================================================

/**
 * 渲染右侧匹配结果卡片。
 * v2 新增：字段对照表、领域匹配详情、文本重叠关键词标签。
 *
 * 参数:
 *   data ({source, matches, config}): 后端返回的匹配结果（含配置）
 */
function renderCards(data) {
    const cardsEl = document.getElementById('match-cards');
    if (!cardsEl) return;

    // ---- 更新选中源信息 ----
    if (data && data.source) {
        const src = data.source;
        const srcTitleEl = document.getElementById('source-title');
        if (srcTitleEl) {
            srcTitleEl.textContent = src.name;
        }
        const srcSubEl = document.getElementById('source-sub');
        if (srcSubEl) {
            srcSubEl.textContent = src.company || src.domain || '';
        }
    }

    // ---- 渲染参数面板 ----
    if (data && data.config) {
        renderConfigPanel(data.config);
    }

    if (!data || !data.matches || data.matches.length === 0) {
        cardsEl.innerHTML = '<div class="cards-empty">未找到匹配项</div>';
        return;
    }

    const rankColors = ['#3B82F6', '#22C55E', '#F59E0B'];
    const dw = (data.config && data.config.domain_weight) || 0.6;
    const tw = (data.config && data.config.text_weight)   || 0.4;

    let html = '';

    data.matches.forEach((m, idx) => {
        const t    = m.target;
        const rankColor = rankColors[idx] || '#94A3B8';
        const sf   = m.source_fields || {};
        const tf   = m.target_fields || {};

        // ---- 1) 排名徽章 + 标题 ----
        html += `
        <div class="match-card">
            <div class="card-rank" style="background:${rankColor}">#${idx + 1}</div>
            <div class="card-header">
                <h3 class="card-title">${t.name}</h3>
                <span class="card-tag">${t.domain || ''}</span>
            </div>
        `;

        // ---- 2) 字段对照表 ----
        html += '<div class="card-section"><div class="card-section-title">📋 匹配字段对照</div>';
        html += '<div class="field-compare">';

        const sfKeys = Object.keys(sf);
        const tfKeys = Object.keys(tf);
        const maxLen = Math.max(sfKeys.length, tfKeys.length);

        for (let i = 0; i < maxLen; i++) {
            const sKey = sfKeys[i] || '';
            const tKey = tfKeys[i] || '';
            const sVal = sf[sKey] ? truncateText(sf[sKey], 60) : '';
            const tVal = tf[tKey] ? truncateText(tf[tKey], 60) : '';

            html += `
                <div class="field-row">
                    <div class="field-col field-col-left">
                        <span class="field-label">${sKey}</span>
                        <span class="field-value">${sVal}</span>
                    </div>
                    <div class="field-arrow">→</div>
                    <div class="field-col field-col-right">
                        <span class="field-label">${tKey}</span>
                        <span class="field-value">${tVal}</span>
                    </div>
                </div>
            `;
        }

        html += '</div></div>';  // 关闭字段对照

        // ---- 3) 领域匹配详情 ----
        html += `
            <div class="card-section">
                <div class="card-section-title">
                    🔍 领域匹配
                    <span class="section-score">原始得分：${(m.domain_score * 100).toFixed(0)}%</span>
                    <span class="section-score section-score-weighted">加权贡献：${(m.domain_score * dw * 100).toFixed(0)}%</span>
                </div>
                <div class="card-detail-text">${nl2br(m.domain_match_detail)}</div>
            </div>
        `;

        // ---- 4) 文本匹配详情 ----
        const td = m.text_match_detail || {};
        const bigrams = td.overlapping_bigrams || [];
        const overlapCnt = td.overlap_count || 0;
        const unionCnt   = td.union_count || 0;

        html += `
            <div class="card-section">
                <div class="card-section-title">
                    📐 文本匹配
                    <span class="section-score">原始得分：${(m.text_score * 100).toFixed(1)}%</span>
                    <span class="section-score section-score-weighted">加权贡献：${(m.text_score * tw * 100).toFixed(1)}%</span>
                </div>
                <div class="text-stats">
                    <div class="text-stat">
                        <span class="text-stat-label">重叠 Bigram</span>
                        <span class="text-stat-val">${overlapCnt} / ${unionCnt}</span>
                        <span class="text-stat-hint">（交集/并集）</span>
                    </div>
                    <div class="text-stat">
                        <span class="text-stat-label">文本A Bigram 数</span>
                        <span class="text-stat-val">${td.a_bigram_count || 0}</span>
                    </div>
                    <div class="text-stat">
                        <span class="text-stat-label">文本B Bigram 数</span>
                        <span class="text-stat-val">${td.b_bigram_count || 0}</span>
                    </div>
                </div>
                <div class="text-snippets">
                    <div class="text-snippet-label">文本A摘要（能力侧）：</div>
                    <div class="text-snippet-val">${td.text_a_snippet || '--'}</div>
                    <div class="text-snippet-label">文本B摘要（机会侧）：</div>
                    <div class="text-snippet-val">${td.text_b_snippet || '--'}</div>
                </div>
        `;

        // 重叠 bigram 关键词标签
        if (bigrams.length > 0) {
            html += '<div class="bigram-tags">';
            html += '<span class="bigram-tags-label">重叠关键词(2-gram)：</span>';
            bigrams.forEach(bg => {
                html += `<span class="bigram-tag">${bg}</span>`;
            });
            html += '</div>';
        } else {
            html += '<div class="bigram-tags"><span class="bigram-tags-empty">无重叠关键词</span></div>';
        }

        html += '</div>';  // 关闭文本匹配

        // ---- 5) 得分进度条 ----
        html += scoreBar(m.domain_score, m.text_score, m.total_score, dw, tw);

        html += '</div>';  // 关闭 match-card
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
    // 清空参数面板
    renderConfigPanel(null);
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
    // 清空参数面板
    renderConfigPanel(null);
}
