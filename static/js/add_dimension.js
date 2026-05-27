/**
 * add_dimension.js —— 添加匹配维度模态框交互
 *
 * 职责：实现"添加匹配维度"弹窗的完整交互流程。
 *
 * 完整流程：
 *  1. 用户在配置面板点击"添加维度"按钮 → main.js 调用 window.openAddDimensionModal()
 *  2. 模态框打开 → 并行加载匹配方法和字段列表
 *  3. 用户选择匹配方法 → 动态渲染对应参数表单
 *  4. 用户在两侧多选面板中选择参与匹配的字段
 *  5. 用户填写维度名称、图标等基本信息
 *  6. 点击保存 → 表单验证 → POST 到 /api/dimensions
 *  7. 成功后关闭模态框 → 刷新配置面板
 *
 * 依赖模块：
 *  - api.js 间接依赖（通过 fetch(url) 原生调用，非函数封装）
 *  - 使用 window 挂载全局函数：openAddDimensionModal / closeAddDimensionModal / submitAddDimension
 *
 * CSS 类名约定：
 *  - #add-dim-overlay          → 模态框遮罩层
 *  - #add-dim-ability-fields   → 能力侧字段多选面板容器
 *  - #add-dim-opp-fields       → 机会侧字段多选面板容器
 *  - #add-dim-method           → 匹配方法下拉选择器
 *  - #add-dim-method-params    → 方法特定参数动态渲染容器
 *  - .multi-select-actions     → 全选/取消全选按钮行
 *  - .config-section           → 配置项区块（标签+输入框）
 *  - .config-label             → 配置项标签
 *  - .config-text-input        → 文本输入框样式
 *  - .config-number-input      → 数字输入框样式
 *  - .config-select            → 下拉选择器样式
 *  - .config-hint              → 配置提示文字（灰色小字）
 */

(function () {
    'use strict';

    const BASE = '';

    /* ====================================================================
     * 多选字段面板工具函数
     *
     * 提供字段 checkbox 列表的渲染、选中值收集、计数更新、HTML 转义等
     * 通用功能。能力侧和机会侧面板复用同一套逻辑。
     * ==================================================================== */

    /**
     * 向指定容器填充字段 checkbox 列表（含全选/取消全选按钮）。
     *
     * 生成的 HTML 结构：
     *   <div class="multi-select-actions">
     *     <button data-action="select-all" data-target="<containerId>">全选</button>
     *     <button data-action="deselect-all" data-target="<containerId>">取消全选</button>
     *   </div>
     *   <label><input type="checkbox" value="<字段名>" data-target="<containerId>"> <字段名></label>
     *   ...
     *
     * 安全考虑：字段值通过 _escapeHtml 转义，防止 XSS（虽然字段名来自后端）
     *
     * @param {string} containerId - 字段面板容器元素的 ID
     * @param {string[]} fields - 字段名数组
     * @param {string} countId - 已选计数显示元素的 ID
     */
    function _populateFieldCheckboxes(containerId, fields, countId) {
        const container = document.getElementById(containerId);
        const countEl   = document.getElementById(countId);
        if (!container) return;

        // 构建全选/取消全选按钮行 + checkbox 列表
        let html = '<div class="multi-select-actions">';
        html += `<button type="button" data-action="select-all" data-target="${containerId}">全选</button>`;
        html += `<button type="button" data-action="deselect-all" data-target="${containerId}">取消全选</button>`;
        html += '</div>';

        // 为每个字段生成一个带 checkbox 的 label
        fields.forEach(f => {
            html += `<label><input type="checkbox" value="${_escapeHtml(f)}" data-target="${containerId}"> ${_escapeHtml(f)}</label>`;
        });

        container.innerHTML = html;
        _updateFieldCount(containerId, countId);
    }

    /**
     * 从多选面板收集所有已选中字段值。
     *
     * @param {string} containerId - 字段面板容器 ID
     * @returns {string[]} 已选中的字段值数组
     */
    function _getSelectedFields(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return [];
        const cbs = container.querySelectorAll('input[type="checkbox"]:checked');
        return Array.from(cbs).map(cb => cb.value);
    }

    /**
     * 更新已选字段计数显示文本。
     *
     * 显示格式：
     *  - 已选 > 0 个 → "（已选 N 个）"
     *  - 未选择     → "（未选择）"
     *
     * @param {string} containerId - 字段面板容器 ID
     * @param {string} countId - 计数显示元素 ID
     */
    function _updateFieldCount(containerId, countId) {
        const selected = _getSelectedFields(containerId);
        const el = document.getElementById(countId);
        if (el) {
            el.textContent = selected.length > 0
                ? `（已选 ${selected.length} 个）`
                : '（未选择）';
        }
    }

    /**
     * 简单 HTML 转义——防止字段值中包含 HTML 特殊字符导致的渲染问题。
     *
     * 原理：利用浏览器 innerHTML/textContent 的自动转义机制。
     * 创建一个临时 div → textContent 赋值（无 HTML 解析）→ 读取 innerHTML（转义后）。
     *
     * @param {string} str - 原始字符串
     * @returns {string} HTML 转义后的安全字符串
     */
    function _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    /**
     * 多选面板 checkbox 变化的代理处理。
     *
     * 当用户勾选/取消勾选任一字段时：
     *  1. 判断属于哪个面板（能力侧还是机会侧）
     *  2. 更新对应计数显示
     *
     * 通过事件委托绑定在面板容器上，避免给每个 checkbox 单独绑定。
     *
     * @param {Event} e - change 事件对象
     */
    function _onFieldCheckboxChange(e) {
        const cb = e.target.closest('input[type="checkbox"]');
        if (!cb) return;

        // 通过 data-target 属性判断是哪个面板的 checkbox
        const targetId = cb.dataset.target;
        if (targetId === 'add-dim-ability-fields') {
            _updateFieldCount('add-dim-ability-fields', 'ability-field-count');
        } else if (targetId === 'add-dim-opp-fields') {
            _updateFieldCount('add-dim-opp-fields', 'opp-field-count');
        }
    }

    /**
     * 全选/取消全选按钮点击代理。
     *
     * 流程：
     *  1. 通过 data-action 判断是"全选"还是"取消全选"
     *  2. 通过 data-target 找到对应的面板容器
     *  3. 遍历容器内所有 checkbox，统一设置 checked 状态
     *  4. 更新计数显示
     *
     * @param {Event} e - click 事件对象
     */
    function _onSelectAllClick(e) {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;

        const action   = btn.dataset.action;    // 'select-all' 或 'deselect-all'
        const targetId = btn.dataset.target;    // 目标面板容器 ID
        const container = document.getElementById(targetId);
        if (!container) return;

        const cbs = container.querySelectorAll('input[type="checkbox"]');
        const check = (action === 'select-all');  // 全选 → true，取消全选 → false

        // 统一设置所有 checkbox 的选中状态
        cbs.forEach(cb => { cb.checked = check; });

        // 更新对应面板的计数显示
        if (targetId === 'add-dim-ability-fields') {
            _updateFieldCount('add-dim-ability-fields', 'ability-field-count');
        } else if (targetId === 'add-dim-opp-fields') {
            _updateFieldCount('add-dim-opp-fields', 'opp-field-count');
        }
    }

    /* ====================================================================
     * 模态框打开
     *
     * 流程：
     *  1. 显示遮罩层（display: flex）
     *  2. 并行加载匹配方法列表 + 字段列表
     *  3. 填充方法下拉框 + 两侧字段多选面板
     *  4. 渲染默认方法对应的参数表单
     * ==================================================================== */

    /**
     * 打开"添加匹配维度"模态框。
     *
     * 加载顺序：
     *  1. 显示遮罩层
     *  2. 并行请求 /api/dimensions/methods 和 /api/fields
     *  3. 填充 UI：方法下拉框 → 能力侧字段 → 机会侧字段
     *  4. 初始化参数表单（调用 _renderMethodParams，默认方法为空时清空）
     *
     * @returns {Promise<void>}
     */
    async function openAddModal() {
        // 显示模态框遮罩层（flex 布局居中模态内容）
        const overlay = document.getElementById('add-dim-overlay');
        if (overlay) overlay.style.display = 'flex';

        try {
            // 并行加载两个数据源，减少等待时间
            const [methodsRes, fieldsRes] = await Promise.all([
                fetch(`${BASE}/api/dimensions/methods`),
                fetch(`${BASE}/api/fields`),
            ]);
            const methods = await methodsRes.json();
            const fields  = await fieldsRes.json();

            // ---- 填充方法下拉框 ----
            const ms = document.getElementById('add-dim-method');
            ms.innerHTML = '<option value="">-- 请选择 --</option>';
            Object.keys(methods).forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                ms.appendChild(opt);
            });

            // ---- 填充能力侧字段多选面板 ----
            _populateFieldCheckboxes(
                'add-dim-ability-fields',
                fields.ability || [],
                'ability-field-count'
            );

            // ---- 填充机会侧字段多选面板 ----
            _populateFieldCheckboxes(
                'add-dim-opp-fields',
                fields.opportunity || [],
                'opp-field-count'
            );

            // ---- 初始化方法参数区（当前方法为空，参数区为空） ----
            _renderMethodParams();
        } catch (e) {
            console.error('[AddDim] 加载失败:', e);
        }
    }

    // 挂载到全局，供 main.js 配置面板的"添加维度"按钮调用
    window.openAddDimensionModal = openAddModal;

    /* ====================================================================
     * 模态框关闭
     * ==================================================================== */

    /**
     * 关闭"添加匹配维度"模态框。
     *
     * 实现：隐藏遮罩层。下次打开时会重新加载数据，因此不需要清理表单状态。
     */
    function closeAddModal() {
        const overlay = document.getElementById('add-dim-overlay');
        if (overlay) overlay.style.display = 'none';
    }

    // 挂载到全局，供关闭按钮和遮罩点击事件调用
    window.closeAddDimensionModal = closeAddModal;

    /* ====================================================================
     * 方法特定参数动态渲染
     *
     * 当用户切换匹配方法时（change 事件），根据方法类型动态渲染
     * 对应的参数表单。不同方法有不同的参数项：
     *
     *  string_match    → 能力侧标签 + 机会侧标签（两个文本框）
     *  bigram          → 文本截取长度（数字框）
     *  vector_semantic → 嵌入模型选择 + 相似度阈值（下拉框 + 数字框）
     *
     * 所有参数表单使用一致的 CSS 类名体系，确保视觉风格统一。
     * ==================================================================== */

    /**
     * 根据当前选中的匹配方法，动态渲染对应的参数输入区。
     *
     * 通过 document.getElementById('add-dim-method').value 获取当前方法。
     * 支持的三种方法各渲染不同的表单结构。
     *
     * @returns {void}
     */
    function _renderMethodParams() {
        const method  = document.getElementById('add-dim-method').value;
        const container = document.getElementById('add-dim-method-params');
        if (!container) return;
        container.innerHTML = '';  // 清空旧参数表单

        if (method === 'string_match') {
            // 字符串文本匹配：需要为能力侧和机会侧分别设置
            // method_labels（在匹配详情中显示的标签名）
            container.innerHTML = `
                <div class="config-section">
                    <div class="config-label">能力侧标签（详情中显示）</div>
                    <input type="text" id="add-dim-ml-ability"
                           class="config-text-input"
                           placeholder="如：能力领域">
                </div>
                <div class="config-section">
                    <div class="config-label">机会侧标签（详情中显示）</div>
                    <input type="text" id="add-dim-ml-opp"
                           class="config-text-input"
                           placeholder="如：欢迎合作方向">
                </div>`;

        } else if (method === 'bigram') {
            // 二元组文本匹配：核心参数是文本截取长度
            // 范围 50-2000，步长 10，默认 300
            container.innerHTML = `
                <div class="config-section">
                    <div class="config-label">文本截取长度（max_length）</div>
                    <input type="number" id="add-dim-bigram-len"
                           class="config-number-input"
                           value="300" min="50" max="2000" step="10">
                </div>`;

        } else if (method === 'vector_semantic') {
            // 语义向量匹配：需要选择嵌入模型和设置相似度阈值
            // bge-small：体积小速度快，适合离线环境
            // bge-large：精度高但体积大（326MB），首次需下载
            container.innerHTML = `
                <div class="config-section">
                    <div class="config-label">嵌入模型</div>
                    <select id="add-dim-vec-model" class="config-select">
                        <option value="BAAI/bge-small-zh-v1.5">
                            bge-small-zh (95MB · 快速)
                        </option>
                        <option value="BAAI/bge-large-zh-v1.5">
                            bge-large-zh (326MB · 精准)
                        </option>
                    </select>
                    <div class="config-hint" style="font-size:11px;color:#94a3b8;margin-top:4px;">
                        模型首次使用时自动从 HuggingFace 下载。
                    </div>
                </div>
                <div class="config-section">
                    <div class="config-label">最低相似度阈值</div>
                    <input type="number" id="add-dim-vec-threshold"
                           class="config-number-input"
                           value="0.0" min="0" max="1" step="0.05">
                    <div class="config-hint" style="font-size:11px;color:#94a3b8;margin-top:4px;">
                        低于此值的匹配结果直接得 0 分。0.0 表示不过滤。
                    </div>
                </div>`;
        }
        // 其他方法：参数区为空，使用后端默认参数
    }

    /* ====================================================================
     * 表单提交处理
     *
     * 验证规则：
     *  1. 维度名称（label）必填
     *  2. 匹配方法（method）必选
     *  3. 能力侧字段至少选一个
     *  4. 机会侧字段至少选一个
     *
     * 提交数据格式：
     *  {
     *    label: "维度名称",
     *    method: "string_match",
     *    ability_fields: ["field1", "field2"],
     *    opportunity_fields: ["field3"],
     *    icon: "📊",              // 可选
     *    focus_description: "...", // 可选
     *    method_labels: {ability: "...", opportunity: "..."}  // string_match 可选
     *  }
     * ==================================================================== */

    /**
     * 提交添加维度的表单数据。
     *
     * 流程：
     *  1. 收集表单所有字段值
     *  2. 逐项验证（名称→方法→能力字段→机会字段）
     *  3. 根据方法类型组装特殊参数
     *  4. POST 到后端 API
     *  5. 成功后关闭模态框并刷新配置面板
     *
     * @returns {Promise<void>}
     */
    async function submitAdd() {
        // ---- 收集表单数据 ----
        const label        = (document.getElementById('add-dim-label')?.value || '').trim();
        const method       = document.getElementById('add-dim-method')?.value || '';
        const abilityFields = _getSelectedFields('add-dim-ability-fields');
        const oppFields     = _getSelectedFields('add-dim-opp-fields');
        const icon         = (document.getElementById('add-dim-icon')?.value || '').trim();
        const focusDesc    = (document.getElementById('add-dim-focus')?.value || '').trim();

        // ---- 表单必填验证（逐项检查，早期返回避免无效提交） ----
        if (!label)         { alert('请填写维度名称'); return; }
        if (!method)        { alert('请选择匹配方法'); return; }
        if (!abilityFields.length) { alert('请至少选择一个能力侧字段'); return; }
        if (!oppFields.length)     { alert('请至少选择一个机会侧字段'); return; }

        // ---- 组装提交数据（核心字段） ----
        const dimDef = {
            label:            label,
            method:           method,
            ability_fields:   abilityFields,
            opportunity_fields: oppFields,
        };

        // ---- 可选字段（有值才添加，避免发送空字符串） ----
        if (icon) dimDef.icon = icon;
        if (focusDesc) dimDef.focus_description = focusDesc;

        // ---- 方法特定参数组装 ----
        // string_match 的方法标签：用于在匹配详情中标识两侧字段
        if (method === 'string_match') {
            const mA = (document.getElementById('add-dim-ml-ability')?.value || '').trim();
            const mO = (document.getElementById('add-dim-ml-opp')?.value || '').trim();
            if (mA || mO) {
                dimDef.method_labels = {};
                if (mA) dimDef.method_labels.ability     = mA;
                if (mO) dimDef.method_labels.opportunity = mO;
            }
        }
        // bigram 的参数（如 text_max_length）和 vector_semantic 的参数
        // 可在后端设置默认值，前端非必填

        // ---- 提交到后端 ----
        try {
            const res  = await fetch(`${BASE}/api/dimensions`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(dimDef),
            });
            const data = await res.json();

            // HTTP 状态码检查（后端可能在 200 响应体中包含 error 字段）
            if (!res.ok) { alert('添加失败：' + (data.error || res.status)); return; }

            // 添加成功
            alert('添加成功！');
            closeAddModal();

            // 刷新父级配置面板——关闭后延时重开，让后端数据更新生效
            if (window.closeConfigModal) window.closeConfigModal();
            setTimeout(() => { if (window.openConfigModal) window.openConfigModal(); }, 100);
        } catch (e) {
            // 网络错误等异常情况
            alert('添加失败：' + e.message);
        }
    }

    // 挂载到全局，供模态框"保存"按钮的 click 事件调用
    window.submitAddDimension = submitAdd;

    /* ====================================================================
     * DOMContentLoaded —— 一次性事件绑定
     *
     * 在页面 DOM 就绪后绑定所有模态框内部交互事件。
     * 绑定的交互项：
     *  1. 方法下拉框切换 → 动态渲染参数表单
     *  2. 能力侧字段面板 checkbox 变化 → 更新计数
     *  3. 机会侧字段面板 checkbox 变化 → 更新计数
     *  4. 全选/取消全选按钮点击
     *  5. 关闭按钮（×）
     *  6. 取消按钮
     *  7. 保存按钮
     *  8. 遮罩层点击关闭
     *
     * 使用事件委托模式的场景：
     *  - checkbox 变化（change 事件委托在容器上）
     *  - 全选/取消全选点击（click 事件委托在容器上）
     *
     * 优势：避免给每个动态生成的 checkbox 单独绑定事件。
     * ==================================================================== */
    document.addEventListener('DOMContentLoaded', () => {
        // ---- 1. 方法下拉框切换 → 重新渲染参数表单 ----
        const ms = document.getElementById('add-dim-method');
        if (ms) ms.addEventListener('change', _renderMethodParams);

        // ---- 2. 能力侧字段面板 checkbox 变化 → 更新已选计数 ----
        const abContainer = document.getElementById('add-dim-ability-fields');
        if (abContainer) abContainer.addEventListener('change', _onFieldCheckboxChange);

        // ---- 3. 机会侧字段面板 checkbox 变化 → 更新已选计数 ----
        const opContainer = document.getElementById('add-dim-opp-fields');
        if (opContainer) opContainer.addEventListener('change', _onFieldCheckboxChange);

        // ---- 4. 全选/取消全选按钮点击（事件委托在面板容器上） ----
        if (abContainer) abContainer.addEventListener('click', _onSelectAllClick);
        if (opContainer) opContainer.addEventListener('click', _onSelectAllClick);

        // ---- 5. 关闭按钮（右上角 ×） ----
        const closeX = document.getElementById('add-dim-close-x');
        if (closeX) closeX.addEventListener('click', closeAddModal);

        // ---- 6. 取消按钮 ----
        const cancel = document.getElementById('add-dim-cancel');
        if (cancel) cancel.addEventListener('click', closeAddModal);

        // ---- 7. 保存按钮 → 调用 submitAdd 提交表单 ----
        const save = document.getElementById('add-dim-save');
        if (save) save.addEventListener('click', submitAdd);

        // ---- 8. 点击遮罩层关闭模态框（仅点击 overlay 本身时） ----
        const ov = document.getElementById('add-dim-overlay');
        if (ov) ov.addEventListener('click', e => { if (e.target === ov) closeAddModal(); });
    });
})();
