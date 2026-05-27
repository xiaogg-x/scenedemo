/**
 * render.js —— DOM 渲染模块 (v3：维度注册表驱动)
 *
 * 【模块定位】
 *   本模块是整个前端 SPA 的视图层核心，负责所有 HTML 元素的创建、更新和事件处理。
 *   不直接调用后端 API（由 api.js 负责），也不管理应用状态（由 state.js 负责），
 *   而是通过 State.get* / State.set* 读取和写入状态，驱动 UI 渲染。
 *
 * 【v3 核心变化】
 *   - 权重滑块由 /api/dimensions 动态生成，不再硬编码 3 个
 *   - 匹配详情卡片遍历 dimension_scores 渲染，不再硬编码维度
 *   - 联动滑块逻辑泛化为 N 维通用算法
 *
 * 【导出的全局函数（挂载到 window，供 main.js 调用）】
 *   - openConfigModal / closeConfigModal / saveConfig / cancelConfig / resetConfig
 *   - setConfigStrategy
 *   - _toggleExplain / _refreshExplain（挂载到 window，由 onclick 内联调用）
 */


// ============================================================================
// 工具函数
// ============================================================================

/**
 * 截断超长文本，超过 maxLen 的部分用省略号替代。
 * 用于列表项、卡片标题等空间的有限展示场景。
 *
 * @param {string} text   - 原始文本
 * @param {number} maxLen - 最大字符数
 * @returns {string} 截断后的文本（或空字符串）
 */
function truncateText(text, maxLen) {
    if (!text) return '';
    return text.length > maxLen ? text.substring(0, maxLen) + '...' : text;
}

/**
 * 将纯文本转换为安全的 HTML，实现换行符 → <br> 的转换。
 * 同时对 HTML 特殊字符（& < >）进行转义，防止 XSS 注入。
 * 用于卡片详情文本、LLM 解释等用户/后端生成的内容展示。
 *
 * @param {string} text - 原始纯文本（可能含换行符）
 * @returns {string} 转义后的 HTML 字符串
 */
function nl2br(text) {
    if (!text) return '';
    const escaped = text
        .replace(/&/g, '&amp;')      // 转义 & 符号
        .replace(/</g, '&lt;')       // 转义 < 符号
        .replace(/>/g, '&gt;');      // 转义 > 符号
    return escaped.replace(/\n/g, '<br>');  // 换行符 → <br>
}


// ============================================================================
// 得分进度条 (v3：动态维度)
// ============================================================================

/**
 * 生成多色百分比进度条。
 *
 * v3：接受 dimension_scores 对象，自动按维度颜色渲染。
 * 进度条的每个色块代表一个维度的加权贡献（score × weight）。
 *
 * 例如 3 个维度的贡献分别为 34%、21%、35%，则渲染为
 * [蓝色34%][绿色21%][橙色35%] 的综合进度条。
 *
 * @param {object} dimScores - {dimId: {score, weight}, ...} 各维度的原始分和权重
 * @param {float} totalScore  - 综合得分（Σ score×weight）
 * @returns {string} HTML 字符串，包含进度条容器和综合百分比标签
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
    // 综合得分转百分比，保留 1 位小数
    const totalPct = (totalScore * 100).toFixed(1);

    // 获取维度注册表顺序，确保色块按定义顺序排列
    const dims = State.getDimensions() || [];
    const dimOrder = dims.map(d => d.id);

    // 筛选有贡献的维度（score × weight > 0），跳过无贡献的维度以简化显示
    const activeDims = [];
    for (const dimId of dimOrder) {
        const ds = dimScores[dimId];
        if (!ds) continue;
        const contribPct = parseInt((ds.score * ds.weight * 100).toFixed(0));
        if (contribPct === 0) continue;   // 贡献为0不显示色块
        activeDims.push({ dimId, ds, contribPct });
    }

    // 构建色块 HTML —— 每个有贡献的维度生成一个 <div> 色条
    let barsHtml = '';
    for (let i = 0; i < activeDims.length; i++) {
        const { dimId, ds, contribPct } = activeDims[i];
        const dim = State.getDimensionById(dimId);    // 从注册表查找维度元信息
        const color = dim ? dim.color : '#94A3B8';    // 维度颜色（兜底灰色）
        const label = dim ? dim.score_label : dimId;   // 维度显示名称

        // 圆角逻辑：单色块全圆角，多色块首尾各有圆角，中间无圆角
        let borderRadius = '0';
        if (activeDims.length === 1) {
            borderRadius = '4px';                          // 唯一色块 → 全圆角
        } else if (i === 0) {
            borderRadius = '4px 0 0 4px';                 // 首个色块 → 左侧圆角
        } else if (i === activeDims.length - 1) {
            borderRadius = '0 4px 4px 0';                 // 末尾色块 → 右侧圆角
        }
        // 中间色块 borderRadius 保持 '0'（无圆角），与相邻色块无缝衔接

        // title 属性：鼠标悬停时显示该维度的详细贡献信息（原始分 × 权重 = 贡献%）
        const rawPct = (ds.score * 100).toFixed(0);
        const weightPct = (ds.weight * 100).toFixed(0);
        barsHtml += `<div class="score-bar-${dimId}"
            style="width:${contribPct}%;background:${color};border-radius:${borderRadius}"
            title="${label}贡献 ${contribPct}% (原始分 ${rawPct}% × 权重 ${weightPct}%)">
        </div>`;
    }

    // 返回进度条容器：内含 flex 布局的色条 + 右侧综合得分百分比标签
    return `
        <div class="score-bar-container">
            <div class="score-bar">${barsHtml}</div>
            <span class="score-label">综合 <strong>${totalPct}%</strong></span>
        </div>
    `;
}


// ============================================================================
// 左侧列表渲染
// ============================================================================

/**
 * 渲染左侧数据列表（能力列表或机会列表）。
 *
 * 根据当前模式（State.getMode()）从 State 中取出对应的列表数据，
 * 为每条记录生成一个列表项 DOM，显示序号、名称、公司/区域、领域标签等。
 * 选中项（State.getSelectedId()）会高亮显示。
 *
 * 列表项通过 data-id 和 data-mode 属性标记，供 main.js 中的点击事件使用。
 */
function renderList() {
    const listEl = document.getElementById('item-list');
    if (!listEl) return;

    const mode  = State.getMode();           // 当前模式：'ability' 或 'opportunity'
    const items = State.getCurrentList();    // 当前模式下的数据列表
    const selectedId = State.getSelectedId(); // 当前选中的记录 ID

    // 空列表 → 显示占位提示
    if (!items || items.length === 0) {
        listEl.innerHTML = '<div class="list-empty">暂无数据</div>';
        return;
    }

    // 遍历列表数据，为每条记录生成列表项 HTML
    let html = '';
    items.forEach((item, idx) => {
        const isActive = item.id === selectedId;
        const activeCls = isActive ? 'list-item active' : 'list-item';

        if (mode === 'ability') {
            // 能力列表项：显示序号、名称、公司、领域标签、区域标签
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
            // 机会列表项：显示序号、名称、面积、领域标签（无区域标签）
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

    // 更新底部的列表计数标签
    const countEl = document.getElementById('list-count');
    if (countEl) countEl.textContent = `共 ${items.length} 条`;

    // 更新顶栏左侧的模式标签（"场景能力列表" 或 "场景机会列表"）
    const titleEl = document.getElementById('mode-label');
    if (titleEl) titleEl.textContent = mode === 'ability' ? '场景能力列表' : '场景机会列表';
}


// ============================================================================
// 参数面板渲染 (v3：动态维度)
// ============================================================================

/**
 * 渲染右侧顶部的匹配参数概览面板。
 *
 * 该面板展示当前匹配使用的参数摘要，包括：
 *   - 各维度权重百分比
 *   - Top N 返回条数
 *   - 文本截取字数
 *
 * 参数面板用于让用户在不打开配置模态框的情况下，快速了解当前匹配参数。
 *
 * @param {object|null} config - 匹配配置对象，null 时清空面板
 */
function renderConfigPanel(config) {
    const panelEl = document.getElementById('config-panel');
    if (!panelEl) return;
    if (!config) { panelEl.innerHTML = ''; return; }

    // 遍历维度注册表，生成各维度的权重显示标签
    const dims = State.getDimensions() || [];
    let dimItems = '';
    for (let i = 0; i < dims.length; i++) {
        const d = dims[i];
        const pct = ((config[d.weight_key] || 0) * 100).toFixed(1);
        dimItems += `<span class="config-item">${d.icon || ''} ${d.score_label} <strong>${pct}%</strong></span>`;
        if (i < dims.length - 1) dimItems += '<span class="config-sep">|</span>';
    }

    // 拼装面板 HTML：维度权重 + TopN + 截取字数，用分隔符 | 连接
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

/**
 * 渲染右侧匹配结果卡片列表。
 *
 * 这是视图层最复杂的函数，负责将后端返回的匹配结果渲染为完整的卡片 DOM。
 * 每张卡片的结构：
 *   1) 排名徽章（#1/#2/#3）+ 标题 + 领域标签
 *   2) 字段对照表（源字段 → 目标字段的双列对比）
 *   3) 各维度的匹配详情（按维度注册表顺序遍历）：
 *      - bigram 类型：重叠关键词统计 + 文本摘要 + bigram 标签
 *      - vector 类型：余弦相似度 + 阈值 + 文本摘要 + LLM 推理
 *      - 其他类型：纯文本展示
 *   4) 得分进度条（多色综合进度条）
 *   5) LLM 解释按钮 + 流式内容区域
 *
 * @param {object} data - 匹配结果数据，包含 source（选中源）、config（配置）、matches（匹配列表）
 */
function renderCards(data) {
    const cardsEl = document.getElementById('match-cards');
    if (!cardsEl) return;

    // ---- 更新右侧顶部的选中源信息 ----
    if (data && data.source) {
        const src = data.source;
        const srcTitleEl = document.getElementById('source-title');
        if (srcTitleEl) srcTitleEl.textContent = src.name;
        const srcSubEl = document.getElementById('source-sub');
        if (srcSubEl) srcSubEl.textContent = src.company || src.domain || '';
    }

    // ---- 更新参数概览面板 ----
    if (data && data.config) renderConfigPanel(data.config);

    // 无匹配结果 → 显示空状态
    if (!data || !data.matches || data.matches.length === 0) {
        cardsEl.innerHTML = '<div class="cards-empty">未找到匹配项</div>';
        return;
    }

    // 前三名排名徽章颜色：蓝、绿、黄，其余灰色
    const rankColors = ['#3B82F6', '#22C55E', '#F59E0B'];
    const dims = State.getDimensions() || [];  // 维度注册表

    let html = '';

    // ---- 遍历每条匹配结果，生成卡片 ----
    data.matches.forEach((m, idx) => {
        const t = m.target;                    // 匹配目标（能力或机会）
        const rankColor = rankColors[idx] || '#94A3B8';  // 排名颜色
        const sf = m.source_fields || {};       // 源字段对照
        const tf = m.target_fields || {};       // 目标字段对照
        const dimScores = m.dimension_scores || {};  // 各维度得分

        // 1) 排名徽章 + 卡片头部（标题 + 领域标签）
        html += `
        <div class="match-card">
            <div class="card-rank" style="background:${rankColor}">#${idx + 1}</div>
            <div class="card-header">
                <h3 class="card-title">${t.name}</h3>
                <span class="card-tag">${t.domain || ''}</span>
            </div>`;

        // 2) 字段对照表：将源字段和目标字段按行并排展示
        html += '<div class="card-section"><div class="card-section-title">📋 匹配字段对照</div>';
        html += '<div class="field-compare">';
        const sfKeys = Object.keys(sf);   // 源字段名列表
        const tfKeys = Object.keys(tf);   // 目标字段名列表
        const maxLen = Math.max(sfKeys.length, tfKeys.length);
        for (let i = 0; i < maxLen; i++) {
            // 取对应位置的字段名和值（不足的用空字符串填充）
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

        // 3) 遍历维度注册表，渲染每个维度的匹配详情
        for (const dim of dims) {
            const dimId = dim.id;
            // 获取该维度的得分数据（score 原始分、detail 详情、weight 权重）
            const ds = dimScores[dimId] || { score: 0, detail: '', weight: 0 };
            const rawScore = (ds.score * 100);           // 原始分转百分比
            const contrib = (ds.score * ds.weight * 100); // 加权贡献转百分比

            // 维度分区标题：显示维度图标 + 名称 + 原始得分 + 加权贡献
            html += `<div class="card-section">
                <div class="card-section-title">
                    ${dim.icon || ''} ${dim.label}
                    <span class="section-score">原始得分：${dim.detail_type === 'bigram' ? rawScore.toFixed(1) : rawScore.toFixed(0)}%</span>
                    <span class="section-score section-score-weighted">加权贡献：${contrib.toFixed(0)}%</span>
                </div>`;

            // ---- 根据维度类型渲染不同的详情内容 ----
            if (dim.detail_type === 'bigram') {
                // [bigram 类型] 文本匹配详情：基于 2-gram 交集/并集计算相似度
                const td = ds.detail || {};
                const bigrams = td.overlapping_bigrams || [];  // 重叠的 2-gram 列表
                const overlapCnt = td.overlap_count || 0;       // 交集大小
                const unionCnt = td.union_count || 0;           // 并集大小

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

                // 渲染重叠关键词标签列表
                if (bigrams.length > 0) {
                    html += '<div class="bigram-tags"><span class="bigram-tags-label">重叠关键词(2-gram)：</span>';
                    bigrams.forEach(bg => { html += `<span class="bigram-tag">${bg}</span>`; });
                    html += '</div>';
                } else {
                    html += '<div class="bigram-tags"><span class="bigram-tags-empty">无重叠关键词</span></div>';
                }
            } else if (dim.detail_type === 'vector') {
                // [vector 类型] 语义向量匹配详情：基于文本嵌入的余弦相似度
                const vd = (typeof ds.detail === 'object' && ds.detail) ? ds.detail : {};
                const simPct = ((vd.similarity || 0) * 100).toFixed(1);     // 相似度百分比
                const thresholdPct = ((vd.threshold || 0) * 100).toFixed(0); // 最低阈值百分比

                html += `
                <div class="text-stats">
                    <div class="text-stat">
                        <span class="text-stat-label">余弦相似度</span>
                        <span class="text-stat-val">${simPct}%</span>
                    </div>
                    <div class="text-stat">
                        <span class="text-stat-label">最低阈值</span>
                        <span class="text-stat-val">${thresholdPct}%</span>
                    </div>
                </div>
                <div class="text-snippets">
                    <div class="text-snippet-label">能力侧文本：</div>
                    <div class="text-snippet-val">${vd.text_a_snippet || '--'}</div>
                    <div class="text-snippet-label">机会侧文本：</div>
                    <div class="text-snippet-val">${vd.text_b_snippet || '--'}</div>
                </div>
                <div class="card-detail-text">${nl2br(vd.reason || '无匹配信息')}</div>`;
            } else {
                // [其他类型] 通用文本详情：直接显示 detail 文本（如区域匹配说明）
                html += `<div class="card-detail-text">${nl2br(ds.detail || '无匹配信息')}</div>`;
            }

            html += '</div>';
        }

        // 4) 综合得分进度条（多色，各维度色块叠加）
        html += scoreBar(dimScores, m.total_score);

        // 5) LLM 解释交互区域
        //    - 展开/收起按钮（首次展开自动请求 AI 解释）
        //    - 刷新按钮（强制清除后端缓存后重新请求）
        //    - 流式文本显示区（通过 SSE 实时更新）
        html += `
        <div class="explain-section">
            <button class="explain-btn"
                    data-ability-id="${data.source.id}"
                    data-opp-id="${t.id}"
                    data-match-idx="${idx}"
                    data-mode="${State.getMode()}"
                    onclick="window._toggleExplain(this)">
                🤖 查看 AI 解释
            </button>
            <div class="explain-content" style="display:none;">
                <div class="explain-toolbar">
                    <button class="explain-refresh-btn"
                            onclick="window._refreshExplain(this.parentElement.parentElement)">
                        🔄 刷新解释
                    </button>
                    <span class="explain-status"></span>
                </div>
                <div class="explain-text"></div>
            </div>
        </div>`;

        html += '</div>';  // 关闭 .match-card
    });

    cardsEl.innerHTML = html;
}


// ============================================================================
// 状态占位渲染（加载中 / 空状态）
// ============================================================================

/**
 * 显示匹配加载中的占位 UI。
 * 在发起匹配请求后立即调用，展示旋转加载动画和提示文字。
 * 同时清空参数面板，避免显示过期参数。
 */
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

/**
 * 显示右侧空状态占位 UI。
 * 在用户尚未选择任何列表项时显示，引导用户点击左侧列表。
 */
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

// ---- 模态框内部状态变量 ----
let _configStrategy = 'free';    // 当前权重调整策略：'free'（自由）/ 'linked'（联动）
let _linkedBusy = false;         // 联动模式锁，防止滑块 input 事件递归触发

/** 所有动态注册的滑块事件引用，方便关闭模态框时批量解绑，避免内存泄漏 */
let _sliderEventRefs = [];


/**
 * 重新发起当前选中项的匹配请求并刷新卡片。
 * 在配置保存后、且配置有变化时自动调用。
 * 根据当前模式（ability/opportunity）选择对应的 API 请求函数。
 */
async function _refetchCurrentMatch() {
    const selectedId = State.getSelectedId();
    if (selectedId == null) return;
    showLoading();   // 显示加载中占位
    try {
        const mode = State.getMode();
        let result;
        if (mode === 'ability') {
            result = await fetchMatchForAbility(selectedId);    // 能力 → 机会匹配
        } else {
            result = await fetchMatchForOpportunity(selectedId); // 机会 → 能力匹配
        }
        // 更新 State 中的配置缓存并重新渲染卡片
        if (result && result.config) State.setConfig(result.config);
        renderCards(result);
    } catch (err) {
        console.error('[refetchCurrentMatch] 匹配请求失败:', err);
        document.getElementById('match-cards').innerHTML =
            '<div class="cards-empty">匹配请求失败，请重试</div>';
        renderConfigPanel(null);
    }
}


/**
 * 比较新配置与备份配置，判断是否有关键参数变化。
 * 仅检查影响匹配结果的字段：top_n、各维度权重（*_weight）、截取长度（*_length）。
 *
 * @param {object} newConfig - 新的配置对象
 * @returns {boolean} 是否有变化
 */
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
 *
 * @param {Array} dims   - 维度注册表数组
 * @param {object} config - 当前配置对象
 * @returns {string} 各维度滑块的 HTML 字符串
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
 * 遍历每个维度的 params 定义，为每个参数生成滑块 + 数字输入框的双向联动控件。
 *
 * @param {Array} dims   - 维度注册表数组
 * @param {object} config - 当前配置对象
 * @returns {string} 参数表单的 HTML 字符串
 */
function _buildDimParamsHTML(dims, config) {
    let html = '';
    for (const dim of dims) {
        if (!dim.params) continue;  // 该维度无私有参数则跳过
        for (const pk in dim.params) {
            const pv = dim.params[pk];
            const configKey = pv.config_key || `${dim.id}_${pk}`;  // 配置对象中的键名
            const val = config[configKey] != null ? config[configKey] : pv.default;  // 当前值或默认值
            // 滑块和数字输入框并排，双向联动
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

/**
 * 打开配置模态框。
 *
 * 流程：
 *   1) 确保维度元信息已加载（首次打开时从 /api/dimensions 获取）
 *   2) 备份当前配置（用于关闭时恢复 / 保存时比较变化）
 *   3) 动态生成权重滑块和维度私有参数
 *   4) 初始化 TopN 控件值
 *   5) 设置默认策略为"自由调整"并绑定所有滑块事件
 */
async function openConfigModal() {
    // 确保维度已加载
    let dims = State.getDimensions();
    if (!dims || dims.length === 0) {
        try {
            const data = await fetchDimensions();    // 首次从后端获取维度注册表
            State.setDimensions(data.dimensions);
            if (data.config) State.setConfig(data.config);  // 同步后端返回的默认配置
            dims = data.dimensions;
        } catch (e) {
            console.error('加载维度信息失败:', e);
            dims = [];
        }
    }

    const cfg = State.getConfig() || State.getDefaultConfig();
    State.setConfigBackup(cfg);  // 备份当前配置，供取消/比较使用

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


/**
 * 关闭配置模态框。
 * 隐藏遮罩层，并解绑所有动态滑块事件（防止内存泄漏）。
 */
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
        newConfig[dim.weight_key] = val / 1000;  // 转为 0~1 的权重值
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
        // 最后一个用减法兜底，保证精度（避免浮点累加误差）
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

    // ---- 3) TopN（限制在 1~20 范围内） ----
    const topN = parseInt(document.getElementById('input-top-n').value) || 3;
    newConfig.top_n = Math.max(1, Math.min(20, topN));

    try {
        // 调用后端 API 保存配置
        const saved = await updateConfigAPI(newConfig);
        State.setConfig(saved);          // 更新本地状态
        renderConfigPanel(saved);        // 刷新参数概览面板
        closeConfigModal();              // 关闭模态框
        // 如果配置有变化，自动重新匹配当前选中项
        if (_configHasChanged(newConfig)) await _refetchCurrentMatch();
    } catch (err) {
        alert('保存失败：' + err.message);
    }
}


/** 取消配置编辑，直接关闭模态框（不保存、不恢复旧值） */
function cancelConfig() { closeConfigModal(); }


/**
 * 重置所有配置控件到默认值。
 * 遍历维度注册表，将每个权重滑块和私有参数控件重置为默认值。
 */
function resetConfig() {
    const dims = State.getDimensions() || [];
    const cfg = State.getConfig() || State.getDefaultConfig();

    // 重置各维度权重滑块到默认值
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

    // 重置 TopN 为默认值 3
    const sn = document.getElementById('slider-top-n');
    const inN = document.getElementById('input-top-n');
    if (sn) sn.value = 3;
    if (inN) inN.value = 3;

    // 刷新所有百分比显示和权重合计条
    _syncDisplayFromSliders();
}


// ---- 内部辅助函数 ----

/**
 * 更新权重合计条的显示状态。
 * 读取所有权重滑块的值，计算合计百分比，并根据合计值显示不同状态：
 *   - 1000（100%）→ 绿色 ✓ 正常
 *   - 0 → 黄色 ⚠ 均为0
 *   - 其他 → 黄色 ⚠ 将自动缩放至100%
 */
function _updateWeightSum() {
    const dims = State.getDimensions() || [];
    let sum = 0;
    for (const dim of dims) {
        const slider = document.getElementById(`slider-${dim.id}`);
        if (slider) sum += parseInt(slider.value) || 0;
    }

    // 更新合计值文本和状态提示
    const valEl = document.getElementById('weight-sum-val');
    const statusEl = document.getElementById('weight-sum-status');
    const barEl = document.getElementById('weight-sum-bar');

    if (valEl) valEl.textContent = (sum / 10).toFixed(1) + '%';
    if (statusEl) {
        if (sum === 1000) statusEl.textContent = '✓ 正常';
        else if (sum === 0) statusEl.textContent = '⚠ 均为0';
        else statusEl.textContent = '⚠ 将自动缩放至100%';
    }
    // 合计不为 1000 时添加警告样式
    if (barEl) barEl.className = 'config-weight-sum' + (sum === 1000 ? '' : ' warning');
}


/**
 * 从各权重滑块同步更新百分比显示。
 * 遍历所有维度滑块，读取当前值并更新对应的百分比标签。
 * 同时调用 _updateWeightSum() 刷新权重合计条。
 */
function _syncDisplayFromSliders() {
    const dims = State.getDimensions() || [];
    for (const dim of dims) {
        const slider = document.getElementById(`slider-${dim.id}`);
        const display = document.getElementById(`display-${dim.id}`);
        if (slider && display) {
            // 滑块值范围 0~1000，显示时 ÷10 得到 0.0%~100.0%
            display.textContent = (parseInt(slider.value) / 10).toFixed(1) + '%';
        }
    }
    _updateWeightSum();  // 同步刷新权重合计条
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


/**
 * 初始化策略切换按钮的激活状态。
 * 遍历策略按钮组，根据当前策略设置 active 类。
 */
function _initStrategyButtons() {
    const btns = document.querySelectorAll('#strategy-switch .strategy-btn');
    btns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.strategy === _configStrategy);
    });
}


/**
 * 更新策略提示文字。
 * 根据当前策略（free/linked）显示不同的操作说明。
 */
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
    _unbindSliderEvents();  // 先解绑旧的，防止重复绑定

    const dims = State.getDimensions() || [];

    // ---- 权重滑块事件 ----
    for (const dim of dims) {
        const slider = document.getElementById(`slider-${dim.id}`);
        if (!slider) continue;

        const handler = function () {
            if (_linkedBusy) return;  // 联动模式更新中，跳过（防止递归）
            if (_configStrategy === 'linked') {
                // 联动模式：拖动一个滑块时，按比例自动调整其他滑块
                _updateLinkedSliders(dim.id, parseInt(this.value));
                return;
            }
            _syncDisplayFromSliders();  // 自由模式：只刷新百分比显示
        };
        slider.addEventListener('input', handler);
        _sliderEventRefs.push({ el: slider, type: 'input', handler });  // 保存引用以便解绑
    }

    // ---- 维度私有参数：滑块 ↔ 数字框双向同步 ----
    for (const dim of dims) {
        if (!dim.params) continue;
        for (const pk in dim.params) {
            const configKey = dim.params[pk].config_key || `${dim.id}_${pk}`;
            const paramSlider = document.getElementById(`slider-${configKey}`);
            const numInput = document.getElementById(`input-${configKey}`);

            if (paramSlider && numInput) {
                // 滑块变化 → 同步到数字框
                const sliderHandler = function () { numInput.value = this.value; };
                // 数字框变化 → 同步到滑块
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
        const h1 = function () { inN.value = this.value; };  // 滑块 → 数字框
        const h2 = function () { sn.value = this.value; };    // 数字框 → 滑块
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
// LLM 解释交互逻辑
// ============================================================================

/** 存储正在进行的 SSE 请求控制器，用于取消（key 格式：abilityId-oppId） */
const _explainControllers = {};

/**
 * 切换解释区域的显示/隐藏。
 * 首次展开时自动触发 LLM 请求；再次点击则收起并取消进行中的请求。
 */
window._toggleExplain = function (btn) {
    const section = btn.parentElement;
    const content = section.querySelector('.explain-content');
    const textEl = section.querySelector('.explain-text');
    const statusEl = section.querySelector('.explain-status');

    if (!content || !textEl) return;

    // 如果已展开 → 收起，并取消进行中的 SSE 请求
    if (content.style.display !== 'none') {
        content.style.display = 'none';
        btn.textContent = '🤖 查看 AI 解释';
        const key = _explainKey(section);
        if (_explainControllers[key]) {
            _explainControllers[key].abort();  // 取消进行中的 SSE 流
            delete _explainControllers[key];
        }
        return;
    }

    // 展开
    content.style.display = 'block';
    btn.textContent = '🤖 收起 AI 解释';

    // 如果已有解释文本 → 不重复请求（避免浪费 token）
    if (textEl.textContent.trim()) return;

    // 发起 LLM 解释请求（非强制刷新模式）
    _doExplain(section, false);
};

/**
 * 刷新解释（清除后端缓存后重新请求）。
 * 由卡片内"🔄 刷新解释"按钮触发。
 */
window._refreshExplain = function (refreshBtn) {
    const section = refreshBtn.closest('.explain-content').parentElement;
    const textEl = section.querySelector('.explain-text');
    const statusEl = section.querySelector('.explain-status');
    if (textEl) textEl.textContent = '';   // 清空旧解释
    if (statusEl) statusEl.textContent = '';

    // 发起 LLM 解释请求（强制刷新模式，忽略后端缓存）
    _doExplain(section, true);
};

/** 生成解释区域的唯一 key（基于能力 ID 和机会 ID），用于管理 SSE 请求控制器 */
function _explainKey(section) {
    const btn = section.querySelector('.explain-btn');
    if (!btn) return '';
    return `${btn.dataset.abilityId}-${btn.dataset.oppId}`;
}

/**
 * 发起 SSE（Server-Sent Events）流式解释请求。
 *
 * 通过 api.js 中的 fetchExplain 函数与后端通信：
 *   - onChunk：每收到一段文本就追加到显示区域（实现打字机效果）
 *   - onDone：流式传输完成，显示完成/缓存状态
 *   - onError：请求失败，显示错误信息
 *
 * @param {HTMLElement} section     - 解释区域的 DOM 容器
 * @param {boolean} forceRefresh    - 是否强制刷新（true 则清除后端缓存后重新生成）
 */
function _doExplain(section, forceRefresh) {
    const btn = section.querySelector('.explain-btn');
    const textEl = section.querySelector('.explain-text');
    const statusEl = section.querySelector('.explain-status');

    if (!btn || !textEl) return;

    // 从按钮的 data-* 属性中提取请求参数
    const abilityId = parseInt(btn.dataset.abilityId);
    const oppId = parseInt(btn.dataset.oppId);
    const matchIdx = parseInt(btn.dataset.matchIdx);
    const mode = btn.dataset.mode;

    if (isNaN(abilityId) || isNaN(oppId)) {
        textEl.textContent = '[错误] 无法获取匹配 ID';
        return;
    }

    // 如果有正在进行的请求，先取消（避免多个请求同时写入同一区域）
    const key = _explainKey(section);
    if (_explainControllers[key]) {
        _explainControllers[key].abort();
        delete _explainControllers[key];
    }

    // 清空旧内容，显示加载状态
    textEl.textContent = '';
    if (statusEl) statusEl.textContent = '⏳ 正在生成...';

    // 发起 SSE 流式请求
    const controller = fetchExplain(
        { ability_id: abilityId, opp_id: oppId, match_index: matchIdx, mode, force_refresh: forceRefresh },
        // onChunk —— 每收到一段文本就追加（打字机效果）
        (chunk) => {
            textEl.textContent += chunk;
        },
        // onDone —— 流式传输完成
        ({ cached }) => {
            if (statusEl) {
                statusEl.textContent = cached ? '✅ 已缓存' : '✅ 生成完成';
            }
            delete _explainControllers[key];  // 清除请求引用
        },
        // onError —— 请求失败
        (error) => {
            textEl.textContent = `[错误] ${error}`;
            if (statusEl) statusEl.textContent = '❌ 请求失败';
            delete _explainControllers[key];
        }
    );

    // 保存 AbortController 引用，以便收起时可以取消请求
    _explainControllers[key] = controller;
}


// ============================================================================
// 暴露到全局（供 main.js 调用）
// ============================================================================
// 以下函数通过 window 对象导出，因为项目采用原生 JS 无打包工具，
// 各模块通过全局变量进行跨文件通信。

window.openConfigModal  = openConfigModal;
window.closeConfigModal = closeConfigModal;
window.saveConfig       = saveConfig;
window.cancelConfig     = cancelConfig;
window.resetConfig      = resetConfig;

/**
 * 设置权重调整策略（free / linked）。
 * 切换为联动模式时，立即将所有滑块按当前比例重新归一化到合计 1000。
 *
 * @param {string} strategy - 'free'（自由调整）或 'linked'（联动调整）
 */
window.setConfigStrategy = function (strategy) {
    _configStrategy = strategy;
    _initStrategyButtons();
    _updateStrategyHint();

    // 切换到联动模式时，立即对当前值进行归一化
    if (_configStrategy === 'linked') {
        _linkedBusy = true;  // 上锁防止事件递归
        const dims = State.getDimensions() || [];
        let sum = 0;
        const vals = [];
        for (const dim of dims) {
            const slider = document.getElementById(`slider-${dim.id}`);
            const val = slider ? parseInt(slider.value) || 0 : Math.round(dim.default_weight * 1000);
            vals.push({ dim, slider, val });
            sum += val;
        }
        const safeSum = sum || 1;  // 避免除零

        // 按比例归一化到合计 1000
        if (vals.length > 0) {
            let allocated = 0;
            for (let i = 0; i < vals.length - 1; i++) {
                const newVal = Math.round(vals[i].val * 1000 / safeSum);
                vals[i].slider.value = newVal;
                allocated += newVal;
            }
            // 最后一个用减法兜底，保证合计精确 = 1000
            vals[vals.length - 1].slider.value = 1000 - allocated;
        }
        _syncDisplayFromSliders();
        _linkedBusy = false;  // 解锁
    }
};
