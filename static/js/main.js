/**
 * main.js —— 主流程编排与事件绑定 (v2)
 *
 * 职责：
 *  1. 页面初始化：加载数据、加载配置、渲染初始界面
 *  2. 事件监听：列表点击、模式切换按钮
 *  3. 流程编排：协调 state / api / render 三个模块完成交互
 *  v2 新增：匹配完成后缓存 config 到全局状态
 */


// ============================================================================
// 页面初始化
// ============================================================================

async function init() {
    try {
        // 并行加载数据、配置和维度元信息
        const [abilities, opportunities, config, dimData] = await Promise.all([
            fetchAbilities(),
            fetchOpportunities(),
            fetchConfig().catch(() => null),
            fetchDimensions().catch(() => null),  // v3: 维度元信息
        ]);

        // 存入全局状态
        State.setAbilities(abilities);
        State.setOpportunities(opportunities);
        if (config) State.setConfig(config);
        if (dimData) {
            State.setDimensions(dimData.dimensions);
            // 合并维度携带的配置值
            if (dimData.config && !config) State.setConfig(dimData.config);
        }

        // 渲染初始列表（默认能力模式）
        renderList();

        // 右侧显示空状态
        showEmpty();

        console.log(`[init] 加载完成：${abilities.length} 条能力，${opportunities.length} 条机会，`
            + `${(dimData && dimData.dimensions) ? dimData.dimensions.length : 0} 个匹配维度`);
    } catch (err) {
        console.error('[init] 数据加载失败:', err);
        document.getElementById('item-list').innerHTML =
            '<div class="list-empty">数据加载失败，请检查后端服务是否启动</div>';
    }
}


// ============================================================================
// 列表点击事件（事件委托）
// ============================================================================

document.getElementById('item-list').addEventListener('click', async (e) => {
    // 向上查找最近的 .list-item 元素（事件委托模式）
    const itemEl = e.target.closest('.list-item');
    if (!itemEl) return;

    // 读取被点击项的 ID
    const id   = parseInt(itemEl.dataset.id);
    const mode = itemEl.dataset.mode;

    if (isNaN(id)) return;

    // 更新状态：选中项
    State.setSelectedId(id);

    // 重新渲染列表（切换高亮）
    renderList();

    // 显示 loading
    showLoading();

    try {
        let result;
        if (mode === 'ability') {
            result = await fetchMatchForAbility(id);
        } else {
            result = await fetchMatchForOpportunity(id);
        }

        // v2: 缓存匹配结果中携带的 config 到全局状态
        if (result && result.config) {
            State.setConfig(result.config);
        }

        // 渲染匹配结果卡片（v2：含详细明细）
        renderCards(result);
    } catch (err) {
        console.error('[onClick] 匹配请求失败:', err);
        document.getElementById('match-cards').innerHTML =
            '<div class="cards-empty">匹配请求失败，请重试</div>';
        renderConfigPanel(null);
    }
});


// ============================================================================
// 模式切换按钮
// ============================================================================

document.getElementById('btn-ability-mode').addEventListener('click', () => {
    switchMode('ability');
});

document.getElementById('btn-opp-mode').addEventListener('click', () => {
    switchMode('opportunity');
});

/**
 * 切换视图模式（能力列表 ↔ 机会列表）。
 *
 * 参数:
 *   mode (str): 'ability' 或 'opportunity'
 */
function switchMode(mode) {
    if (State.getMode() === mode) return;  // 相同模式不重复切换

    // 更新状态
    State.setMode(mode);
    State.setSelectedId(null);

    // 更新按钮激活态样式
    const btnA = document.getElementById('btn-ability-mode');
    const btnO = document.getElementById('btn-opp-mode');
    if (mode === 'ability') {
        btnA.classList.add('active');
        btnO.classList.remove('active');
    } else {
        btnO.classList.add('active');
        btnA.classList.remove('active');
    }

    // 重新渲染列表
    renderList();

    // 右侧重置为空状态
    showEmpty();
}


// ============================================================================
// 配置面板事件绑定
// ============================================================================

/**
 * 绑定配置按钮、模态框、保存/取消/恢复默认 的全部事件。
 * 在页面初始化时调用一次。
 */
function bindConfigEvents() {
    // 打开配置面板
    const btnConfig = document.getElementById('btn-config');
    if (btnConfig) {
        btnConfig.addEventListener('click', () => {
            if (window.openConfigModal) window.openConfigModal();
        });
    }

    // 关闭按钮（右上角 ×）
    const btnCloseX = document.getElementById('config-close-x');
    if (btnCloseX) {
        btnCloseX.addEventListener('click', () => {
            if (window.closeConfigModal) window.closeConfigModal();
        });
    }

    // 点击遮罩层关闭（仅点击 overlay 本身时触发）
    const overlay = document.getElementById('config-overlay');
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                if (window.closeConfigModal) window.closeConfigModal();
            }
        });
    }

    // 保存
    const btnSave = document.getElementById('btn-config-save');
    if (btnSave) {
        btnSave.addEventListener('click', async () => {
            if (window.saveConfig) await window.saveConfig();
        });
    }

    // 取消
    const btnCancel = document.getElementById('btn-config-cancel');
    if (btnCancel) {
        btnCancel.addEventListener('click', () => {
            if (window.cancelConfig) window.cancelConfig();
        });
    }

    // 恢复默认
    const btnReset = document.getElementById('btn-config-reset');
    if (btnReset) {
        btnReset.addEventListener('click', () => {
            if (window.resetConfig) window.resetConfig();
        });
    }

    // 策略切换按钮（事件委托）
    const strategySwitch = document.getElementById('strategy-switch');
    if (strategySwitch) {
        strategySwitch.addEventListener('click', (e) => {
            const btn = e.target.closest('.strategy-btn');
            if (!btn) return;
            const strategy = btn.dataset.strategy;
            if (window.setConfigStrategy) window.setConfigStrategy(strategy);
        });
    }
}


// ============================================================================
// 启动
// ============================================================================

// 页面加载完成后自动初始化
document.addEventListener('DOMContentLoaded', () => {
    init();
    bindConfigEvents();

    // ---- 维度删除 / 添加（事件委托，适配动态 DOM） ----
    const sliderContainer = document.getElementById('config-weight-sliders');
    if (sliderContainer) {
        sliderContainer.addEventListener('click', async (e) => {
            // 删除按钮
            const deleteBtn = e.target.closest('.dim-delete-btn');
            if (deleteBtn) {
                e.preventDefault();
                e.stopPropagation();
                const dimId = deleteBtn.dataset.dimId;
                if (!confirm(`确定删除此维度吗？`)) return;
                try {
                    await deleteDimensionAPI(dimId);
                    alert('删除成功！');
                    if (window.closeConfigModal) window.closeConfigModal();
                    setTimeout(() => { if (window.openConfigModal) window.openConfigModal(); }, 100);
                } catch (err) {
                    alert('删除失败：' + err.message);
                }
                return;
            }

            // 添加维度按钮
            const addBtn = e.target.closest('#btn-add-dimension');
            if (addBtn) {
                e.preventDefault();
                if (window.openAddDimensionModal) window.openAddDimensionModal();
            }
        });
    }
});
