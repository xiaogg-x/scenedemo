/**
 * main.js —— 主流程编排与事件绑定 (v2)
 *
 * 职责：
 *  1. 页面初始化（init）：加载数据、配置、维度元信息，渲染初始界面
 *  2. 列表点击处理：事件委托模式，根据 mode 调用对应匹配 API
 *  3. 模式切换：能力列表 ↔ 机会列表，切换按钮激活态、重置右侧面板
 *  4. 配置面板事件绑定：打开/关闭/保存/取消/恢复默认/策略切换
 *  5. 流程编排：协调 state.js ↔ api.js ↔ render.js 三个模块完成交互
 *
 * v2 新增：
 *  - 匹配完成后缓存 result.config 到全局状态
 *  - 维度删除/添加的事件委托处理
 *  - 策略切换（strategy-switch）事件绑定
 *
 * 依赖模块（通过 <script> 标签顺序加载）：
 *  - state.js     → State 全局对象
 *  - api.js       → fetchXxx / updateConfigAPI / addDimensionAPI 等函数
 *  - render.js    → renderList / showEmpty / showLoading / renderCards / renderConfigPanel 等函数
 *  - add_dimension.js → openAddDimensionModal / closeAddDimensionModal
 *
 * CSS 类名约定：
 *  - .list-item      → 左侧列表项，点击后通过 dataset.id/dataset.mode 获取上下文
 *  - .list-item.active → 当前选中的列表项高亮样式
 *  - .list-empty      → 列表为空或加载失败时的提示样式
 *  - .cards-empty     → 匹配结果为空时的提示样式
 *  - .strategy-btn    → 策略切换按钮，通过 dataset.strategy 区分策略值
 *  - .active          → 按钮/选项卡的激活态样式
 *  - .dim-delete-btn  → 维度删除按钮，通过 dataset.dimId 获取维度 ID
 */


// ============================================================================
// 页面初始化 —— 应用启动入口
// ============================================================================

/**
 * 应用初始化函数。
 *
 * 执行流程：
 *  1. 并行加载四个数据源：能力列表、机会列表、配置、维度元信息
 *  2. 将加载结果存入 State 全局状态
 *  3. 渲染左侧列表（默认能力模式）
 *  4. 右侧显示空状态占位
 *
 * 错误处理：
 *  - fetchConfig 和 fetchDimensions 使用 .catch(() => null) 降级
 *    确保即使后端部分服务不可用，页面仍能展示列表
 *  - 如果数据完全加载失败，列表区域显示错误提示
 *
 * @returns {Promise<void>}
 */
async function init() {
    try {
        // 并行加载数据、配置和维度元信息（减少总加载时间）
        // fetchConfig/fetchDimensions 失败时降级为 null，不阻塞整体流程
        const [abilities, opportunities, config, dimData] = await Promise.all([
            fetchAbilities(),
            fetchOpportunities(),
            fetchConfig().catch(() => null),
            fetchDimensions().catch(() => null),  // v3: 维度元信息，失败时回退到 DEFAULT_CONFIG
        ]);

        // 存入全局状态——所有后续操作都通过 State 对象读写
        State.setAbilities(abilities);
        State.setOpportunities(opportunities);
        if (config) State.setConfig(config);

        // 维度数据优先级：dimData.dimensions 优先，其次 dimData.config（合并值）
        if (dimData) {
            State.setDimensions(dimData.dimensions);
            // 如果 /api/config 获取失败但 /api/dimensions 携带了 config，则使用后者
            if (dimData.config && !config) State.setConfig(dimData.config);
        }

        // 渲染左侧列表（默认显示能力列表）
        renderList();

        // 右侧面板显示空状态——引导用户点击一项
        showEmpty();

        console.log(`[init] 加载完成：${abilities.length} 条能力，${opportunities.length} 条机会，`
            + `${(dimData && dimData.dimensions) ? dimData.dimensions.length : 0} 个匹配维度`);
    } catch (err) {
        console.error('[init] 数据加载失败:', err);
        // 致命错误：列表区域显示友好提示
        document.getElementById('item-list').innerHTML =
            '<div class="list-empty">数据加载失败，请检查后端服务是否启动</div>';
    }
}


// ============================================================================
// 列表点击事件（事件委托模式）
//
// 为什么用事件委托：
//  列表项由 renderList() 动态生成，如果给每个 .list-item 单独绑定事件，
//  每次重新渲染都需要重新绑定。事件委托只需在父容器 #item-list 上绑定一次，
//  通过 e.target.closest('.list-item') 找到被点击的项，性能更好且代码更简洁。
// ============================================================================

/**
 * 列表项点击处理（事件委托）。
 *
 * 流程：
 *  1. 向上查找最近的 .list-item 元素
 *  2. 读取 dataset.id 和 dataset.mode 获取上下文
 *  3. 更新 State 中的选中项
 *  4. 重新渲染列表（切换高亮样式）
 *  5. 显示 loading → 调用匹配 API → 渲染匹配结果卡片
 *
 * CSS 说明：
 *  - .list-item 需要实现 cursor: pointer 的悬停效果
 *  - .list-item.active 用于高亮当前选中项，在 renderList() 中根据 State.getSelectedId() 设置
 */
document.getElementById('item-list').addEventListener('click', async (e) => {
    // 事件委托：向上查找最近的匹配元素（处理点击子元素的情况）
    const itemEl = e.target.closest('.list-item');
    if (!itemEl) return;  // 点击的不是列表项，忽略

    // 读取 dataset 属性（由 renderList() 渲染时写入）
    // dataset.id  → 场景能力/机会的 ID
    // dataset.mode → 'ability' 或 'opportunity'
    const id   = parseInt(itemEl.dataset.id);
    const mode = itemEl.dataset.mode;

    if (isNaN(id)) return;  // 无效 ID，安全跳过

    // 更新选中状态（会触发下一次 renderList 时改变高亮）
    State.setSelectedId(id);

    // 立即重新渲染列表，给用户即时视觉反馈（高亮切换）
    renderList();

    // 右侧面板显示加载动画，隐藏旧结果，提升用户等待体验
    showLoading();

    try {
        let result;

        // 根据当前模式调用对应的匹配 API
        // ability 模式：场景能力 → 匹配场景机会
        // opportunity 模式：场景机会 → 匹配场景能力
        if (mode === 'ability') {
            result = await fetchMatchForAbility(id);
        } else {
            result = await fetchMatchForOpportunity(id);
        }

        // v2: 匹配结果可能携带最新的 config（后端计算时使用的参数）
        // 缓存到全局状态，保证配置面板显示的是最新值
        if (result && result.config) {
            State.setConfig(result.config);
        }

        // 渲染匹配结果卡片（包含详细得分明细，由 render.js 实现）
        renderCards(result);
    } catch (err) {
        console.error('[onClick] 匹配请求失败:', err);
        // 匹配失败时保持右侧可见，显示错误信息
        document.getElementById('match-cards').innerHTML =
            '<div class="cards-empty">匹配请求失败，请重试</div>';
        renderConfigPanel(null);
    }
});


// ============================================================================
// 模式切换按钮
//
// 有两个按钮：#btn-ability-mode 和 #btn-opp-mode
// 激活态通过 .active CSS 类名控制视觉样式（高亮背景/字体颜色）
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
 * 执行步骤：
 *  1. 相同模式直接返回，避免无意义的重渲染
 *  2. 更新 State 模式标记
 *  3. 清除选中项（不同模式的 item ID 体系不同，不能共用）
 *  4. 切换按钮 .active 样式
 *  5. 重新渲染左侧列表
 *  6. 右侧面板重置为空状态
 *
 * @param {'ability'|'opportunity'} mode - 目标模式
 */
function switchMode(mode) {
    // 相同模式不重复切换（防止连续点击造成的浪费）
    if (State.getMode() === mode) return;

    // 更新全局状态——模式变更 + 清除选中项
    State.setMode(mode);
    State.setSelectedId(null);

    // 切换按钮的视觉效果：.active 类控制高亮状态
    const btnA = document.getElementById('btn-ability-mode');
    const btnO = document.getElementById('btn-opp-mode');
    if (mode === 'ability') {
        btnA.classList.add('active');
        btnO.classList.remove('active');
    } else {
        btnO.classList.add('active');
        btnA.classList.remove('active');
    }

    // 根据新模式重新渲染列表数据
    renderList();

    // 右侧面板清空——用户需要重新点击列表项来查看匹配结果
    showEmpty();
}


// ============================================================================
// 配置面板事件绑定
//
// 注意：配置面板的 DOM 由 render.js/render_config.js 动态生成，
// 但这些按钮的 ID 在模板中固定，所以事件绑定可以在这里进行。
// 策略切换按钮使用事件委托，因为 .strategy-btn 是动态渲染的。
// ============================================================================

/**
 * 绑定配置面板（Config Modal）的全部事件。
 *
 * 绑定的交互项：
 *  - #btn-config           → 打开配置面板
 *  - #config-close-x       → 关闭面板（× 按钮）
 *  - #config-overlay       → 点击遮罩层关闭
 *  - #btn-config-save      → 保存配置到后端
 *  - #btn-config-cancel    → 取消编辑，恢复备份
 *  - #btn-config-reset     → 恢复默认配置
 *  - #strategy-switch      → 策略切换（事件委托，子元素 .strategy-btn）
 *
 * 所有实际操作委托给 window 上的全局函数（由 render.js/render_config.js 挂载）：
 *  - window.openConfigModal
 *  - window.closeConfigModal
 *  - window.saveConfig
 *  - window.cancelConfig
 *  - window.resetConfig
 *  - window.setConfigStrategy
 *
 * 为什么通过 window 挂载：不同的 JS 文件（IIFE 模块）之间需要通过 window 对象
 * 共享函数引用，这是 vanilla JS 无模块打包器时的常见模式。
 */
function bindConfigEvents() {
    // 打开配置面板按钮（页面右上角齿轮图标）
    const btnConfig = document.getElementById('btn-config');
    if (btnConfig) {
        btnConfig.addEventListener('click', () => {
            if (window.openConfigModal) window.openConfigModal();
        });
    }

    // 关闭按钮（模态框右上角的 ×）
    const btnCloseX = document.getElementById('config-close-x');
    if (btnCloseX) {
        btnCloseX.addEventListener('click', () => {
            if (window.closeConfigModal) window.closeConfigModal();
        });
    }

    // 点击遮罩层（半透明黑色背景）关闭模态框
    // 关键：只有在点击 overlay 本身（而非其子元素）时才关闭
    const overlay = document.getElementById('config-overlay');
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                if (window.closeConfigModal) window.closeConfigModal();
            }
        });
    }

    // 保存配置：读取滑块值 → POST 到 /api/config → 关闭面板
    const btnSave = document.getElementById('btn-config-save');
    if (btnSave) {
        btnSave.addEventListener('click', async () => {
            if (window.saveConfig) await window.saveConfig();
        });
    }

    // 取消编辑：丢弃修改 → 恢复配置备份 → 关闭面板
    const btnCancel = document.getElementById('btn-config-cancel');
    if (btnCancel) {
        btnCancel.addEventListener('click', () => {
            if (window.cancelConfig) window.cancelConfig();
        });
    }

    // 恢复默认：将所有配置项重置为 DEFAULT_CONFIG 值
    const btnReset = document.getElementById('btn-config-reset');
    if (btnReset) {
        btnReset.addEventListener('click', () => {
            if (window.resetConfig) window.resetConfig();
        });
    }

    // 策略切换按钮区域（事件委托）
    // .strategy-btn 是动态渲染的预设策略按钮（如"均衡""文本优先"等）
    const strategySwitch = document.getElementById('strategy-switch');
    if (strategySwitch) {
        strategySwitch.addEventListener('click', (e) => {
            const btn = e.target.closest('.strategy-btn');
            if (!btn) return;
            // 读取 strategy 值（如 "balanced"、"semantic_first" 等）
            const strategy = btn.dataset.strategy;
            if (window.setConfigStrategy) window.setConfigStrategy(strategy);
        });
    }
}


// ============================================================================
// 应用启动入口
// ============================================================================

/**
 * DOM 完全加载后自动执行初始化。
 *
 * 启动流程：
 *  1. init() —— 加载数据 → 渲染列表和空状态
 *  2. bindConfigEvents() —— 绑定配置面板所有交互事件
 *  3. 维度管理事件绑定（事件委托）：
 *     - 删除维度：点击 .dim-delete-btn → 确认 → DELETE API → 刷新面板
 *     - 添加维度：点击 #btn-add-dimension → 打开 add_dimension.js 的模态框
 */
document.addEventListener('DOMContentLoaded', () => {
    // 1. 初始化应用（加载数据、渲染界面）
    init();

    // 2. 绑定配置面板交互事件
    bindConfigEvents();

    // 3. 维度删除 / 添加（事件委托，适配配置面板动态 DOM）
    //    这些按钮在配置滑块容器内部，通过 render.js 动态渲染
    const sliderContainer = document.getElementById('config-weight-sliders');
    if (sliderContainer) {
        sliderContainer.addEventListener('click', async (e) => {
            // ---- 删除维度 ----
            const deleteBtn = e.target.closest('.dim-delete-btn');
            if (deleteBtn) {
                e.preventDefault();
                e.stopPropagation();  // 阻止事件冒泡到滑块交互
                const dimId = deleteBtn.dataset.dimId;  // 读取维度 ID

                // 二次确认，防止误删
                if (!confirm(`确定删除此维度吗？`)) return;

                try {
                    await deleteDimensionAPI(dimId);
                    alert('删除成功！');

                    // 刷新配置面板（关闭后延时重开，让后端更新生效）
                    if (window.closeConfigModal) window.closeConfigModal();
                    setTimeout(() => { if (window.openConfigModal) window.openConfigModal(); }, 100);
                } catch (err) {
                    alert('删除失败：' + err.message);
                }
                return;
            }

            // ---- 添加维度 ----
            const addBtn = e.target.closest('#btn-add-dimension');
            if (addBtn) {
                e.preventDefault();
                // 打开 add_dimension.js 提供的模态框
                if (window.openAddDimensionModal) window.openAddDimensionModal();
            }
        });
    }
});
