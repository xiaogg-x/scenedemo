/**
 * render.js —— DOM 渲染模块 (v3：维度注册表驱动)
 *
 * 职责：所有 HTML 元素的创建和更新都集中在此模块。
 * v3 核心变化：
 *   - 权重滑块由 /api/dimensions 动态生成，不再硬编码 3 个
 *   - 匹配详情卡片遍历 dimension_scores 渲染，不再硬编码维度
 *   - 联动滑块逻辑泛化为 N 维通用算法
 */

// ============================================================================
// 工具函数
// ============================================================================

function truncateText(text, maxLen) {
    if (!text) return '';
    return text.length > maxLen ? text.substring(0, maxLen) + '...' : text;
}

function nl2br(text) {
    if (!text) return '';
    const escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    return escaped.replace(/\n/g, '<br>');
}


// ============================================================================
// 得分进度条 (v3：动态维度)
// ============================================================================

/**
 * 生成多色百分比进度条。
 * v3：接受 dimension_scores 对象，自动按维度颜色渲染。
 *
 * @param {object} dimScores - {dimId: {score, weight}, ...}
 * @param {float} totalScore  - 综合得分
 * @returns {string} HTML 字符串
 */
/**
 * 生成多色百分比进度条。
 *
 * v3：接受 dimension_scores 对象，自动按维度颜色渲染。
 * 进度条的每个色块代表一个维度的加权贡献（score × weight）。
 *
 * 例如 3 个维度的贡献分别为 34%、21%、35%，则渲染为
 * [蓝色34%][绿色21%][橙色35%] 的综合进度条。
 *
 * @param {object} dimScores - {dimId: {score, weight}, ...}
 * @param {float} totalScore  - 综合得分（Σ score×weight）
 * @returns {string} HTML 字符串
 */
function scoreBar(dimScores, totalScore) {
    const totalPct = (totalScore * 100).toFixed(1);

    // 获取维度注册表顺序，确保色块按定义顺序排列
    const dims = State.getDimensions() || [];
    const dimOrder = dims.map(d => d.id);

    // 筛选有贡献的维度（score × weight > 0）
    const activeDims = [];
    for (const dimId of dimOrder) {
        const ds = dimScores[dimId];
        if (!ds) continue;
        const contribPct = parseInt((ds.score * ds.weight * 100).toFixed(0));
        if (contribPct === 0) continue;   // 贡献为0不显示色块
        activeDims.push({ dimId, ds, contribPct });
    }

    // 构建色块 HTML
    let barsHtml = '';
    for (let i = 0; i < activeDims.length; i++) {
        const { dimId, ds, contribPct } = activeDims[i];
        const dim = State.getDimensionById(dimId);
        const color = dim ? dim.color : '#94A3B8';
        const label = dim ? dim.score_label : dimId;

        // 圆角逻辑：单色块全圆角，多色块首尾各有圆角，中间无圆角
        let borderRadius = '0';
        if (activeDims.length === 1) {
            borderRadius = '4px';
        } else if (i === 0) {
            borderRadius = '4px 0 0 4px';
        } else if (i === activeDims.length - 1) {
            borderRadius = '0 4px 4px 0';
        }

        // title 属性：悬停时显示详细贡献信息
        const rawPct = (ds.score * 100).toFixed(0);
        const weightPct = (ds.weight * 100).toFixed(0);
        barsHtml += `<div class="score-bar-${dimId}"
            style="width:${contribPct}%;background:${color};border-radius:${borderRadius}"
            title="${label}贡献 ${contribPct}% (原始分 ${rawPct}% × 权重 ${weightPct}%)">
        </div>`;
    }

    return `
        <div class="score-bar-container">
            <div class="score-bar">${barsHtml}</div>
            <span class="score-label">综合 <strong>${totalPct}%</strong></span>
        </div>
    `;
}


// ============================================================================
// 左侧列表渲染 (不变)
// ============================================================================

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
                    <span class="item-tag item-tag-district">${item.district || '未知区域'}</span>
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

    const countEl = document.getElementById('list-count');
    if (countEl) countEl.textContent = `共 ${items.length} 条`;

    const titleEl = document.getElementById('mode-label');
    if (titleEl) titleEl.textContent = mode === 'ability' ? '场景能力列表' : '场景机会列表';
}


// ============================================================================
// 参数面板渲染 (v3：动态维度)
// ============================================================================

function renderConfigPanel(config) {
    const panelEl = document.getElementById('config-panel');
    if (!panelEl) return;
    if (!config) { panelEl.innerHTML = ''; return; }

    const dims = State.getDimensions() || [];
    let dimItems = '';
    for (let i = 0; i < dims.length; i++) {
        const d = dims[i];
        const pct = ((config[d.weight_key] || 0) * 100).toFixed(1);
        dimItems += `<span class="config-item">${d.icon || ''} ${d.score_label} <strong>${pct}%</strong></span>`;
        if (i < dims.length - 1) dimItems += '<span class="config-sep">|</span>';
    }

    panelEl.innerHTML = `
        <div class="config-panel-inner">
            <span class="config-panel-title">⚙ 匹配参数</span>
            ${dimItems}
            <span class="config-sep">|</span>
            <span class="config-item">Top <strong>${config.top_n}</strong></span>
            <span class="config-sep">|</span>
            <span class="config-item">截取 <strong>${config.text_max_length || 300}</strong> 字</span>
        </div>
    `;
}


// ============================================================================
// 右侧卡片渲染 (v3：动态维度详情)
// ============================================================================

function renderCards(data) {
    const cardsEl = document.getElementById('match-cards');
    if (!cardsEl) return;

    // 选中源信息
    if (data && data.source) {
        const src = data.source;
        const srcTitleEl = document.getElementById('source-title');
        if (srcTitleEl) srcTitleEl.textContent = src.name;
        const srcSubEl = document.getElementById('source-sub');
        if (srcSubEl) srcSubEl.textContent = src.company || src.domain || '';
    }

    // 参数面板
    if (data && data.config) renderConfigPanel(data.config);

    if (!data || !data.matches || data.matches.length === 0) {
        cardsEl.innerHTML = '<div class="cards-empty">未找到匹配项</div>';
        return;
    }

    const rankColors = ['#3B82F6', '#22C55E', '#F59E0B'];
    const dims = State.getDimensions() || [];

    let html = '';

    data.matches.forEach((m, idx) => {
        const t = m.target;
        const rankColor = rankColors[idx] || '#94A3B8';
        const sf = m.source_fields || {};
        const tf = m.target_fields || {};
        const dimScores = m.dimension_scores || {};

        // 1) 排名徽章 + 标题
        html += `
        <div class="match-card">
            <div class="card-rank" style="background:${rankColor}">#${idx + 1}</div>
            <div class="card-header">
                <h3 class="card-title">${t.name}</h3>
                <span class="card-tag">${t.domain || ''}</span>
            </div>`;

        // 2) 字段对照表
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
                </div>`;
        }
        html += '</div></div>';

        // 3) 遍历维度详情
        for (const dim of dims) {
            const dimId = dim.id;
            const ds = dimScores[dimId] || { score: 0, detail: '', weight: 0 };
            const rawScore = (ds.score * 100);
            const contrib = (ds.score * ds.weight * 100);

            html += `<div class="card-section">
                <div class="card-section-title">
                    ${dim.icon || ''} ${dim.label}
                    <span class="section-score">原始得分：${dim.detail_type === 'bigram' ? rawScore.toFixed(1) : rawScore.toFixed(0)}%</span>
                    <span class="section-score section-score-weighted">加权贡献：${contrib.toFixed(0)}%</span>
                </div>`;

            if (dim.detail_type === 'bigram') {
                // 文本匹配详情
                const td = ds.detail || {};
                const bigrams = td.overlapping_bigrams || [];
                const overlapCnt = td.overlap_count || 0;
                const unionCnt = td.union_count || 0;

                html += `
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
                </div>`;

                if (bigrams.length > 0) {
                    html += '<div class="bigram-tags"><span class="bigram-tags-label">重叠关键词(2-gram)：</span>';
                    bigrams.forEach(bg => { html += `<span class="bigram-tag">${bg}</span>`; });
                    html += '</div>';
                } else {
                    html += '<div class="bigram-tags"><span class="bigram-tags-empty">无重叠关键词</span></div>';
                }
            } else {
                // 文本/区域等通用文本详情
                html += `<div class="card-detail-text">${nl2br(ds.detail || '无匹配信息')}</div>`;
            }

            html += '</div>';
        }

        // 4) 得分进度条
        html += scoreBar(dimScores, m.total_score);

        html += '</div>';
    });

    cardsEl.innerHTML = html;
}


// ============================================================================
// 状态占位渲染
// ============================================================================

function showLoading() {
    const cardsEl = document.getElementById('match-cards');
    if (!cardsEl) return;
    cardsEl.innerHTML = `
        <div class="loading-container">
            <div class="loading-spinner"></div>
            <p>正在匹配...</p>
        </div>`;
    renderConfigPanel(null);
}

function showEmpty() {
    const cardsEl = document.getElementById('match-cards');
    if (!cardsEl) return;
    cardsEl.innerHTML = `
        <div class="cards-empty">
            <div class="empty-icon">←</div>
            <p>请从左侧列表中选择一条记录</p>
            <p class="empty-hint">点击后右侧将展示最匹配的结果</p>
        </div>`;
    renderConfigPanel(null);
}


// ============================================================================
// 配置模态框交互逻辑 (v3：动态维度)
// ============================================================================

let _configStrategy = 'free';
let _linkedBusy = false;

/** 所有动态注册的滑块事件引用，方便解绑 */
let _sliderEventRefs = [];


async function _refetchCurrentMatch() {
    const selectedId = State.getSelectedId();
    if (selectedId == null) return;
    showLoading();
    try {
        const mode = State.getMode();
        let result;
        if (mode === 'ability') {
            result = await fetchMatchForAbility(selectedId);
        } else {
            result = await fetchMatchForOpportunity(selectedId);
        }
        if (result && result.config) State.setConfig(result.config);
        renderCards(result);
    } catch (err) {
        console.error('[refetchCurrentMatch] 匹配请求失败:', err);
        document.getElementById('match-cards').innerHTML =
            '<div class="cards-empty">匹配请求失败，请重试</div>';
        renderConfigPanel(null);
    }
}


function _configHasChanged(newConfig) {
    const backup = State.getConfigBackup();
    if (!backup) return true;

    // 比较所有 config 中可能影响匹配结果的 key（动态获取）
    const keys = new Set([...Object.keys(newConfig), ...Object.keys(backup)]);
    for (const k of keys) {
        if (k === 'top_n' || k.endsWith('_weight') || k.endsWith('_length')) {
            if (newConfig[k] !== backup[k]) return true;
        }
    }
    return false;
}


// ---- 动态滑块生成 ----

/**
 * 根据维度元信息生成权重滑块 HTML。
 *
 * 每个维度渲染为一个 .config-section，包含：
 *   - 维度标签（icon + label + weight_key）
 *   - 权重百分比显示（如 40.0%）
 *   - 删除按钮（仅在维度数 > 1 时显示，保证至少保留 1 个）
 *   - range 滑块（0~1000，每步 0.1%，即显示时 ÷10）
 *   - 0% / 50% / 100% 刻度标签
 *
 * 最后追加一个「➕ 添加匹配维度」按钮。
 */
function _buildWeightSlidersHTML(dims, config) {
    let html = '';
    const canDelete = dims.length > 1;  // 至少保留 1 个维度时不可删除
    for (const dim of dims) {
        // 当前配置中的权重值，转为 0~1000 范围（0.1% 精度）
        const rawVal = Math.round((config[dim.weight_key] || dim.default_weight || 0) * 1000);
        const deleteBtn = canDelete
            ? `<button class="dim-delete-btn" data-dim-id="${dim.id}" title="删除此维度">🗑 删除</button>`
            : '';
        html += `
        <div class="config-section dim-config-section" data-dim-id="${dim.id}">
            <div class="config-label">
                <span class="dim-label-text">${dim.icon || ''} ${dim.label}（${dim.weight_key}）</span>
                <span class="config-value-display" id="display-${dim.id}">${(rawVal / 10).toFixed(1)}%</span>
                ${deleteBtn}
            </div>
            <input type="range" id="slider-${dim.id}"
                   class="config-slider" min="0" max="1000" value="${rawVal}"
                   step="1" data-dim="${dim.id}">
            <div class="slider-labels"><span>0%</span><span>50%</span><span>100%</span></div>
        </div>`;
    }
    // 添加维度按钮（始终显示）
    html += `
        <div class="config-section" style="text-align:center;">
            <button id="btn-add-dimension" class="config-btn config-btn-secondary">
                ➕ 添加匹配维度
            </button>
        </div>`;
    return html;
}


/**
 * 生成维度私有参数表单（如文本匹配的 max_length）。
 */
function _buildDimParamsHTML(dims, config) {
    let html = '';
    for (const dim of dims) {
        if (!dim.params) continue;
        for (const pk in dim.params) {
            const pv = dim.params[pk];
            const configKey = pv.config_key || `${dim.id}_${pk}`;
            const val = config[configKey] != null ? config[configKey] : pv.default;
            html += `
            <div class="config-section">
                <div class="config-label">${pv.label}（${configKey}）</div>
                <div class="config-input-row">
                    <input type="range" id="slider-${configKey}"
                           class="config-slider config-slider-short"
                           min="${pv.min || 0}" max="${pv.slider_max || pv.max || 100}"
                           value="${val}" step="${pv.step || 1}" data-dim-param="${configKey}">
                    <input type="number" id="input-${configKey}"
                           class="config-number-input"
                           min="${pv.min || 0}" max="${pv.max || 9999}"
                           value="${val}" step="${pv.step || 1}" data-dim-param-num="${configKey}">
                </div>
                ${pv.hint ? `<div class="config-hint">${pv.hint}</div>` : ''}
            </div>`;
        }
    }
    return html;
}


// ---- 打开/关闭模态框 ----

async function openConfigModal() {
    // 确保维度已加载
    let dims = State.getDimensions();
    if (!dims || dims.length === 0) {
        try {
            const data = await fetchDimensions();
            State.setDimensions(data.dimensions);
            if (data.config) State.setConfig(data.config);
            dims = data.dimensions;
        } catch (e) {
            console.error('加载维度信息失败:', e);
            dims = [];
        }
    }

    const cfg = State.getConfig() || State.getDefaultConfig();
    State.setConfigBackup(cfg);

    const overlay = document.getElementById('config-overlay');
    if (overlay) overlay.style.display = 'flex';

    // 动态生成权重滑块
    const slidersContainer = document.getElementById('config-weight-sliders');
    if (slidersContainer && dims.length > 0) {
        slidersContainer.innerHTML = _buildWeightSlidersHTML(dims, cfg);
    }

    // 动态生成维度私有参数
    const paramsContainer = document.getElementById('config-dim-params');
    if (paramsContainer && dims.length > 0) {
        paramsContainer.innerHTML = _buildDimParamsHTML(dims, cfg);
    }

    // TopN 和 text_max_length 用回原有的静态控件（text_max_length 已迁移到动态，TopN 保留）
    const topN = cfg.top_n || 3;
    const sn = document.getElementById('slider-top-n');
    const inputN = document.getElementById('input-top-n');
    if (sn) sn.value = topN;
    if (inputN) inputN.value = topN;

    // 初始化策略
    _configStrategy = 'free';
    _initStrategyButtons();
    _updateStrategyHint();
    _updateWeightSum();

    // 绑定事件
    _bindSliderEvents();
}


function closeConfigModal() {
    const overlay = document.getElementById('config-overlay');
    if (overlay) overlay.style.display = 'none';
    _unbindSliderEvents();
}


// ---- 保存/取消/重置 ----

/**
 * 保存配置：从各控件收集当前值 → POST /api/config → 刷新匹配结果。
 *
 * 收集内容：
 *   1) 所有维度权重滑块值（0~1000 → 转为 0~1）
 *   2) 维度私有参数（如 text_max_length）
 *   3) TopN 输入框值
 *
 * 自由模式下如果权重和 ≠ 1000，自动等比例缩放至和为 1.0（最后一个用减法兜底）。
 */
async function saveConfig() {
    const dims = State.getDimensions() || [];
    const newConfig = {};

    // ---- 1) 收集所有维度权重（范围 0~1000，存时转为 0~1） ----
    let sumPct = 0;
    for (const dim of dims) {
        const slider = document.getElementById(`slider-${dim.id}`);
        const val = slider ? parseInt(slider.value) || 0 : Math.round(dim.default_weight * 1000);
        sumPct += val;
        newConfig[dim.weight_key] = val / 1000;
    }

    // ---- 自由模式下权重自动缩放 ----
    // 如果 sumPct ≠ 1000（即权重和 ≠ 100%），等比例缩放至和为 1.0
    if (_configStrategy === 'free' && sumPct !== 1000 && sumPct !== 0) {
        let scaledSum = 0;
        const weightKeys = dims.map(d => d.weight_key);
        // 前 N-1 个按比例缩放
        for (let i = 0; i < weightKeys.length - 1; i++) {
            const val = newConfig[weightKeys[i]] * 1000;
            const scaled = Math.round(val * 1000 / sumPct) / 1000;
            newConfig[weightKeys[i]] = Math.max(0, Math.min(1, scaled));
            scaledSum += newConfig[weightKeys[i]];
        }
        // 最后一个用减法兜底，保证精度
        const lastKey = weightKeys[weightKeys.length - 1];
        newConfig[lastKey] = Math.max(0, Math.min(1, Math.round((1 - scaledSum) * 1000) / 1000));
    }

    // ---- 2) 收集维度私有参数（每个维度的 params 定义） ----
    for (const dim of dims) {
        if (!dim.params) continue;
        for (const pk in dim.params) {
            const configKey = dim.params[pk].config_key || `${dim.id}_${pk}`;
            const numInput = document.getElementById(`input-${configKey}`);
            const val = numInput ? parseInt(numInput.value) : dim.params[pk].default;
            newConfig[configKey] = val;
        }
    }

    // ---- 3) TopN ----
    const topN = parseInt(document.getElementById('input-top-n').value) || 3;
    newConfig.top_n = Math.max(1, Math.min(20, topN));

    try {
        const saved = await updateConfigAPI(newConfig);
        State.setConfig(saved);
        renderConfigPanel(saved);
        closeConfigModal();
        // 如果配置有变化，自动重新匹配
        if (_configHasChanged(newConfig)) await _refetchCurrentMatch();
    } catch (err) {
        alert('保存失败：' + err.message);
    }
}


function cancelConfig() { closeConfigModal(); }


function resetConfig() {
    const dims = State.getDimensions() || [];
    const cfg = State.getConfig() || State.getDefaultConfig();

    for (const dim of dims) {
        const slider = document.getElementById(`slider-${dim.id}`);
        const val = Math.round(dim.default_weight * 1000);
        if (slider) slider.value = val;
    }

    // 重置维度私有参数
    for (const dim of dims) {
        if (!dim.params) continue;
        for (const pk in dim.params) {
            const configKey = dim.params[pk].config_key || `${dim.id}_${pk}`;
            const slider = document.getElementById(`slider-${configKey}`);
            const numInput = document.getElementById(`input-${configKey}`);
            const def = dim.params[pk].default;
            if (slider) slider.value = def;
            if (numInput) numInput.value = def;
        }
    }

    // 重置 TopN
    const sn = document.getElementById('slider-top-n');
    const inN = document.getElementById('input-top-n');
    if (sn) sn.value = 3;
    if (inN) inN.value = 3;

    _syncDisplayFromSliders();
}


// ---- 内部辅助函数 ----

function _updateWeightSum() {
    const dims = State.getDimensions() || [];
    let sum = 0;
    for (const dim of dims) {
        const slider = document.getElementById(`slider-${dim.id}`);
        if (slider) sum += parseInt(slider.value) || 0;
    }

    const valEl = document.getElementById('weight-sum-val');
    const statusEl = document.getElementById('weight-sum-status');
    const barEl = document.getElementById('weight-sum-bar');

    if (valEl) valEl.textContent = (sum / 10).toFixed(1) + '%';
    if (statusEl) {
        if (sum === 1000) statusEl.textContent = '✓ 正常';
        else if (sum === 0) statusEl.textContent = '⚠ 均为0';
        else statusEl.textContent = '⚠ 将自动缩放至100%';
    }
    if (barEl) barEl.className = 'config-weight-sum' + (sum === 1000 ? '' : ' warning');
}


function _syncDisplayFromSliders() {
    const dims = State.getDimensions() || [];
    for (const dim of dims) {
        const slider = document.getElementById(`slider-${dim.id}`);
        const display = document.getElementById(`display-${dim.id}`);
        if (slider && display) {
            display.textContent = (parseInt(slider.value) / 10).toFixed(1) + '%';
        }
    }
    _updateWeightSum();
}


/**
 * 联动模式核心算法（N 维通用）。
 *
 * 当用户拖动某个权重滑块时，其余滑块的剩余空间（1000 - newValue）
 * 按比例等比例分配给其他维度，保证始终合计 = 1000（即 100%）。
 *
 * 算法：
 *   1) 收集中改动的维度之外的所有滑块及其当前值
 *   2) 计算这些值的总和 sumOthers
 *   3) 将剩余量 remain 按 各值/sumOthers 的比例分配
 *   4) 前 N-2 个用比例计算，最后一个用减法兜底避免精度损失
 *
 * 使用 _linkedBusy 全局锁防止滑块事件递归触发。
 *
 * @param {string} changedId - 被用户拖动的维度 id
 * @param {number} newValue  - 该滑块的当前值（0~1000）
 */
function _updateLinkedSliders(changedId, newValue) {
    _linkedBusy = true;   // 上锁，防止本函数内设置滑块值时再次触发 input 事件

    const dims = State.getDimensions() || [];
    const remain = Math.max(0, 1000 - newValue);  // 剩余要分配的量

    // 收集其他维度的滑块和当前值
    const others = [];
    let sumOthers = 0;
    for (const dim of dims) {
        if (dim.id === changedId) continue;  // 跳过被改动的那个
        const slider = document.getElementById(`slider-${dim.id}`);
        if (!slider) continue;
        const val = parseInt(slider.value) || 0;
        others.push({ dim, slider, val });
        sumOthers += val;
    }

    if (others.length === 0) { _linkedBusy = false; return; }

    // 按比例分配：每个维度分得 remain × (自己当前值 / 总和)
    const safeSum = sumOthers || 1;  // 避免除零
    let allocated = 0;
    for (let i = 0; i < others.length - 1; i++) {
        const newVal = Math.round(remain * others[i].val / safeSum);
        others[i].slider.value = newVal;
        allocated += newVal;
    }
    // 最后一个用减法兜底（确保合计精确 = 1000）
    if (others.length > 0) {
        others[others.length - 1].slider.value = remain - allocated;
    }

    _syncDisplayFromSliders();  // 刷新所有显示值
    _linkedBusy = false;        // 解锁
}


function _initStrategyButtons() {
    const btns = document.querySelectorAll('#strategy-switch .strategy-btn');
    btns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.strategy === _configStrategy);
    });
}


function _updateStrategyHint() {
    const hint = document.getElementById('strategy-hint');
    if (!hint) return;
    if (_configStrategy === 'free') {
        hint.textContent = '当前：自由调整，保存时若权重之和≠100% 将自动等比例缩放至100%。';
    } else {
        hint.textContent = '当前：联动调整，修改一个权重将自动等比例缩放其他，始终保持合计100%。';
    }
}


// ---- 事件绑定/解绑（v3：按 DIMENSIONS 注册表动态绑定） ----

/**
 * 绑定所有动态滑块的事件监听器。
 *
 * 每次打开配置模态框时调用，确保所有滑块有正确的交互行为：
 *   - 权重滑块：input 事件 → 自由模式更新显示，联动模式触发 _updateLinkedSliders
 *   - 维度私有参数滑块 ↔ 数字输入框：双向同步
 *   - TopN 滑块 ↔ 数字输入框：双向同步
 *
 * 所有事件引用保存在 _sliderEventRefs 中，方便关闭模态框时解绑。
 */
function _bindSliderEvents() {
    _unbindSliderEvents();  // 先解绑旧的

    const dims = State.getDimensions() || [];

    // ---- 权重滑块事件 ----
    for (const dim of dims) {
        const slider = document.getElementById(`slider-${dim.id}`);
        if (!slider) continue;

        const handler = function () {
            if (_linkedBusy) return;  // 联动模式更新中，跳过（防止递归）
            if (_configStrategy === 'linked') {
                _updateLinkedSliders(dim.id, parseInt(this.value));
                return;
            }
            _syncDisplayFromSliders();  // 自由模式：只刷新显示
        };
        slider.addEventListener('input', handler);
        _sliderEventRefs.push({ el: slider, type: 'input', handler });
    }

    // ---- 维度私有参数：滑块 ↔ 数字框双向同步 ----
    for (const dim of dims) {
        if (!dim.params) continue;
        for (const pk in dim.params) {
            const configKey = dim.params[pk].config_key || `${dim.id}_${pk}`;
            const paramSlider = document.getElementById(`slider-${configKey}`);
            const numInput = document.getElementById(`input-${configKey}`);

            if (paramSlider && numInput) {
                const sliderHandler = function () { numInput.value = this.value; };
                const numHandler = function () { paramSlider.value = this.value; };
                paramSlider.addEventListener('input', sliderHandler);
                numInput.addEventListener('change', numHandler);
                _sliderEventRefs.push({ el: paramSlider, type: 'input', handler: sliderHandler });
                _sliderEventRefs.push({ el: numInput, type: 'change', handler: numHandler });
            }
        }
    }

    // ---- TopN：滑块 ↔ 数字框双向同步 ----
    const sn = document.getElementById('slider-top-n');
    const inN = document.getElementById('input-top-n');
    if (sn && inN) {
        const h1 = function () { inN.value = this.value; };
        const h2 = function () { sn.value = this.value; };
        sn.addEventListener('input', h1);
        inN.addEventListener('change', h2);
        _sliderEventRefs.push({ el: sn, type: 'input', handler: h1 });
        _sliderEventRefs.push({ el: inN, type: 'change', handler: h2 });
    }
}

/**
 * 解绑所有动态绑定的事件监听器。
 * 关闭模态框时调用，防止内存泄漏和重复绑定。
 */
function _unbindSliderEvents() {
    for (const ref of _sliderEventRefs) {
        ref.el.removeEventListener(ref.type, ref.handler);
    }
    _sliderEventRefs = [];
}


// ============================================================================
// 暴露到全局（供 main.js）
// ============================================================================

window.openConfigModal  = openConfigModal;
window.closeConfigModal = closeConfigModal;
window.saveConfig       = saveConfig;
window.cancelConfig     = cancelConfig;
window.resetConfig      = resetConfig;

window.setConfigStrategy = function (strategy) {
    _configStrategy = strategy;
    _initStrategyButtons();
    _updateStrategyHint();

    if (_configStrategy === 'linked') {
        _linkedBusy = true;
        const dims = State.getDimensions() || [];
        let sum = 0;
        const vals = [];
        for (const dim of dims) {
            const slider = document.getElementById(`slider-${dim.id}`);
            const val = slider ? parseInt(slider.value) || 0 : Math.round(dim.default_weight * 1000);
            vals.push({ dim, slider, val });
            sum += val;
        }
        const safeSum = sum || 1;

        if (vals.length > 0) {
            let allocated = 0;
            for (let i = 0; i < vals.length - 1; i++) {
                const newVal = Math.round(vals[i].val * 1000 / safeSum);
                vals[i].slider.value = newVal;
                allocated += newVal;
            }
            vals[vals.length - 1].slider.value = 1000 - allocated;
        }
        _syncDisplayFromSliders();
        _linkedBusy = false;
    }
};
