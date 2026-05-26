/**
 * add_dimension.js —— 添加匹配维度模态框交互
 *
 * 依赖：api.js（fetchDimensionMethods, fetchFields, addDimensionAPI）
 * 挂载到全局：openAddDimensionModal, closeAddDimensionModal
 */

(function () {
    'use strict';

    const BASE = '';

    /* ====================================================================
     * 多选字段面板工具函数
     * ==================================================================== */

    /**
     * 向指定容器填充字段 checkbox 列表（含全选/取消全选按钮）
     */
    function _populateFieldCheckboxes(containerId, fields, countId) {
        const container = document.getElementById(containerId);
        const countEl   = document.getElementById(countId);
        if (!container) return;

        // 全选/取消行 + checkbox 列表
        let html = '<div class="multi-select-actions">';
        html += `<button type="button" data-action="select-all" data-target="${containerId}">全选</button>`;
        html += `<button type="button" data-action="deselect-all" data-target="${containerId}">取消全选</button>`;
        html += '</div>';

        fields.forEach(f => {
            html += `<label><input type="checkbox" value="${_escapeHtml(f)}" data-target="${containerId}"> ${_escapeHtml(f)}</label>`;
        });

        container.innerHTML = html;
        _updateFieldCount(containerId, countId);
    }

    /** 从多选面板收集所有已选中字段值 */
    function _getSelectedFields(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return [];
        const cbs = container.querySelectorAll('input[type="checkbox"]:checked');
        return Array.from(cbs).map(cb => cb.value);
    }

    /** 更新已选计数显示 */
    function _updateFieldCount(containerId, countId) {
        const selected = _getSelectedFields(containerId);
        const el = document.getElementById(countId);
        if (el) {
            el.textContent = selected.length > 0
                ? `（已选 ${selected.length} 个）`
                : '（未选择）';
        }
    }

    /** 简单 HTML 转义 */
    function _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    /** 多选面板的 change 事件代理 */
    function _onFieldCheckboxChange(e) {
        const cb = e.target.closest('input[type="checkbox"]');
        if (!cb) return;
        const targetId = cb.dataset.target;
        if (targetId === 'add-dim-ability-fields') {
            _updateFieldCount('add-dim-ability-fields', 'ability-field-count');
        } else if (targetId === 'add-dim-opp-fields') {
            _updateFieldCount('add-dim-opp-fields', 'opp-field-count');
        }
    }

    /** 全选/取消全选按钮代理 */
    function _onSelectAllClick(e) {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;
        const action   = btn.dataset.action;
        const targetId = btn.dataset.target;
        const container = document.getElementById(targetId);
        if (!container) return;

        const cbs = container.querySelectorAll('input[type="checkbox"]');
        const check = (action === 'select-all');

        cbs.forEach(cb => { cb.checked = check; });

        // 更新计数
        if (targetId === 'add-dim-ability-fields') {
            _updateFieldCount('add-dim-ability-fields', 'ability-field-count');
        } else if (targetId === 'add-dim-opp-fields') {
            _updateFieldCount('add-dim-opp-fields', 'opp-field-count');
        }
    }

    /* ====================================================================
     * 打开添加模态框
     * ==================================================================== */
    async function openAddModal() {
        const overlay = document.getElementById('add-dim-overlay');
        if (overlay) overlay.style.display = 'flex';

        try {
            const [methodsRes, fieldsRes] = await Promise.all([
                fetch(`${BASE}/api/dimensions/methods`),
                fetch(`${BASE}/api/fields`),
            ]);
            const methods = await methodsRes.json();
            const fields  = await fieldsRes.json();

            // 方法下拉
            const ms = document.getElementById('add-dim-method');
            ms.innerHTML = '<option value="">-- 请选择 --</option>';
            Object.keys(methods).forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                ms.appendChild(opt);
            });

            // 能力侧字段（多选）
            _populateFieldCheckboxes(
                'add-dim-ability-fields',
                fields.ability || [],
                'ability-field-count'
            );

            // 机会侧字段（多选）
            _populateFieldCheckboxes(
                'add-dim-opp-fields',
                fields.opportunity || [],
                'opp-field-count'
            );

            _renderMethodParams();
        } catch (e) {
            console.error('[AddDim] 加载失败:', e);
        }
    }

    window.openAddDimensionModal = openAddModal;

    /* ====================================================================
     * 关闭模态框
     * ==================================================================== */
    function closeAddModal() {
        const overlay = document.getElementById('add-dim-overlay');
        if (overlay) overlay.style.display = 'none';
    }

    window.closeAddDimensionModal = closeAddModal;

    /* ====================================================================
     * 渲染方法特定参数区
     * ==================================================================== */
    function _renderMethodParams() {
        const method  = document.getElementById('add-dim-method').value;
        const container = document.getElementById('add-dim-method-params');
        if (!container) return;
        container.innerHTML = '';

        if (method === 'string_match') {
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
            container.innerHTML = `
                <div class="config-section">
                    <div class="config-label">文本截取长度（max_length）</div>
                    <input type="number" id="add-dim-bigram-len"
                           class="config-number-input"
                           value="300" min="50" max="2000" step="10">
                </div>`;
        } else if (method === 'vector_semantic') {
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
    }

    /* ====================================================================
     * 提交添加
     * ==================================================================== */
    async function submitAdd() {
        const label        = (document.getElementById('add-dim-label')?.value || '').trim();
        const method       = document.getElementById('add-dim-method')?.value || '';
        const abilityFields = _getSelectedFields('add-dim-ability-fields');
        const oppFields     = _getSelectedFields('add-dim-opp-fields');
        const icon         = (document.getElementById('add-dim-icon')?.value || '').trim();

        if (!label)         { alert('请填写维度名称'); return; }
        if (!method)        { alert('请选择匹配方法'); return; }
        if (!abilityFields.length) { alert('请至少选择一个能力侧字段'); return; }
        if (!oppFields.length)     { alert('请至少选择一个机会侧字段'); return; }

        const dimDef = {
            label:            label,
            method:           method,
            ability_fields:   abilityFields,
            opportunity_fields: oppFields,
        };
        if (icon) dimDef.icon = icon;

        if (method === 'string_match') {
            const mA = (document.getElementById('add-dim-ml-ability')?.value || '').trim();
            const mO = (document.getElementById('add-dim-ml-opp')?.value || '').trim();
            if (mA || mO) {
                dimDef.method_labels = {};
                if (mA) dimDef.method_labels.ability     = mA;
                if (mO) dimDef.method_labels.opportunity = mO;
            }
        }

        try {
            const res  = await fetch(`${BASE}/api/dimensions`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(dimDef),
            });
            const data = await res.json();
            if (!res.ok) { alert('添加失败：' + (data.error || res.status)); return; }

            alert('添加成功！');
            closeAddModal();
            // 刷新配置模态框
            if (window.closeConfigModal) window.closeConfigModal();
            setTimeout(() => { if (window.openConfigModal) window.openConfigModal(); }, 100);
        } catch (e) {
            alert('添加失败：' + e.message);
        }
    }

    window.submitAddDimension = submitAdd;

    /* ====================================================================
     * DOMContentLoaded —— 绑一次
     * ==================================================================== */
    document.addEventListener('DOMContentLoaded', () => {
        // 方法切换
        const ms = document.getElementById('add-dim-method');
        if (ms) ms.addEventListener('change', _renderMethodParams);

        // 多选面板 checkbox 变化 → 更新计数
        const abContainer = document.getElementById('add-dim-ability-fields');
        if (abContainer) abContainer.addEventListener('change', _onFieldCheckboxChange);
        const opContainer = document.getElementById('add-dim-opp-fields');
        if (opContainer) opContainer.addEventListener('change', _onFieldCheckboxChange);

        // 全选/取消全选按钮点击
        if (abContainer) abContainer.addEventListener('click', _onSelectAllClick);
        if (opContainer) opContainer.addEventListener('click', _onSelectAllClick);

        // 关闭 X
        const closeX = document.getElementById('add-dim-close-x');
        if (closeX) closeX.addEventListener('click', closeAddModal);

        // 取消
        const cancel = document.getElementById('add-dim-cancel');
        if (cancel) cancel.addEventListener('click', closeAddModal);

        // 保存
        const save = document.getElementById('add-dim-save');
        if (save) save.addEventListener('click', submitAdd);

        // 点击遮罩关闭
        const ov = document.getElementById('add-dim-overlay');
        if (ov) ov.addEventListener('click', e => { if (e.target === ov) closeAddModal(); });
    });
})();
