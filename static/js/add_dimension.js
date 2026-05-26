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

            // 能力侧字段
            const ab = document.getElementById('add-dim-ability-field');
            ab.innerHTML = '<option value="">-- 请选择 --</option>';
            (fields.ability || []).forEach(f => {
                const opt = document.createElement('option');
                opt.value = f; opt.textContent = f;
                ab.appendChild(opt);
            });

            // 机会侧字段
            const op = document.getElementById('add-dim-opp-field');
            op.innerHTML = '<option value="">-- 请选择 --</option>';
            (fields.opportunity || []).forEach(f => {
                const opt = document.createElement('option');
                opt.value = f; opt.textContent = f;
                op.appendChild(opt);
            });

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
        }
    }

    /* ====================================================================
     * 提交添加
     * ==================================================================== */
    async function submitAdd() {
        const label        = (document.getElementById('add-dim-label')?.value || '').trim();
        const method       = document.getElementById('add-dim-method')?.value || '';
        const abilityField = document.getElementById('add-dim-ability-field')?.value || '';
        const oppField     = document.getElementById('add-dim-opp-field')?.value || '';
        const icon         = (document.getElementById('add-dim-icon')?.value || '').trim();

        if (!label)        { alert('请填写维度名称'); return; }
        if (!method)       { alert('请选择匹配方法'); return; }
        if (!abilityField) { alert('请选择能力侧字段'); return; }
        if (!oppField)     { alert('请选择机会侧字段'); return; }

        const dimDef = {
            label:            label,
            method:           method,
            ability_fields:   [abilityField],
            opportunity_fields: [oppField],
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
