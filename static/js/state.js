/**
 * state.js —— 全局状态管理模块 (v3)
 *
 * 职责：维护前端页面的全部运行时状态，对外暴露 getter/setter 接口。
 * v3 新增：维度元信息（dimensions）状态，替代硬编码的 DEFAULT_CONFIG。
 *
 * 设计模式：IIFE（立即执行函数表达式）+ 闭包，确保状态私有化。
 * 所有状态变量 _ 前缀表示私有，只能通过 State.getXxx()/State.setXxx() 访问。
 *
 * 状态生命周期：
 *  1. init() 加载数据 → State.setAbilities/State.setOpportunities/State.setConfig
 *  2. 用户点击列表项 → State.setSelectedId + State.getMode 决定匹配方向
 *  3. 模式切换 → State.setMode 重置 selectedId 为 null
 *  4. 配置保存 → State.setConfig 更新匹配参数
 *  5. 维度管理 → State.setDimensions/getDimensions 动态获取匹配维度
 */

const State = (function () {
    'use strict';

    // ====================================================================
    // 默认配置常量（当维度 API 未加载或加载失败时回退使用）
    // 权重之和无需等于 1，后端自动归一化处理
    // ====================================================================
    const DEFAULT_CONFIG = {
        domain_weight:   0.4,   // 领域匹配权重
        text_weight:     0.3,   // 文本相似度权重
        region_weight:   0.3,   // 地区匹配权重
        top_n:           3,     // 返回 Top N 匹配结果
        text_max_length: 300,   // 文本匹配时截取最大长度
    };

    // ====================================================================
    // 内部状态变量（下划线前缀表示私有，由闭包保护）
    // ====================================================================

    /** 当前视图模式：'ability'（能力列表）或 'opportunity'（机会列表） */
    let _currentMode    = 'ability';

    /** 当前选中项的 ID（number 或 null） */
    let _selectedId     = null;

    /** 全部场景能力列表 [{id, name, company, domain}, ...] */
    let _abilities      = [];

    /** 全部场景机会列表 [{id, name, domain, sub_domain, area}, ...] */
    let _opportunities  = [];

    /** 当前匹配参数配置对象（来自 /api/config 或匹配结果返回） */
    let _config         = null;

    /** 配置备份：打开配置面板时拷贝，取消时恢复（深度拷贝） */
    let _configBackup   = null;

    /** v3: 维度元信息列表 [{id, label, weight, weight_key, color, icon, detail_type, params}, ...] */
    let _dimensions     = null;

    // ====================================================================
    // 公开接口 —— 分为五大类：模式 / 选中项 / 数据列表 / 配置 / 维度
    // 所有 getter 只读，setter 用于更新内部状态
    // ====================================================================

    return {
        // ================================================================
        // 1. 视图模式（ability ↔ opportunity 切换）
        // ================================================================

        /**
         * 获取当前视图模式。
         * @returns {'ability'|'opportunity'} 当前模式
         */
        getMode() { return _currentMode; },

        /**
         * 设置当前视图模式。
         * @param {'ability'|'opportunity'} mode - 新模式
         */
        setMode(mode) { _currentMode = mode; },

        // ================================================================
        // 2. 选中项（用户当前查看的 item）
        // ================================================================

        /**
         * 获取当前选中项 ID。
         * @returns {number|null} 选中的 item ID，未选中时为 null
         */
        getSelectedId() { return _selectedId; },

        /**
         * 设置当前选中项 ID。模式切换或点击列表项时调用。
         * @param {number|null} id - 选中的 item ID
         */
        setSelectedId(id) { _selectedId = id; },

        // ================================================================
        // 3. 数据列表（场景能力 / 场景机会）
        // ================================================================

        /**
         * 获取全部场景能力列表。
         * @returns {Array<Object>} [{id, name, company, domain}, ...]
         */
        getAbilities() { return _abilities; },

        /**
         * 设置场景能力列表（init 时调用一次）。
         * @param {Array<Object>} list - 能力数据数组
         */
        setAbilities(list) { _abilities = list; },

        /**
         * 获取全部场景机会列表。
         * @returns {Array<Object>} [{id, name, domain, sub_domain, area}, ...]
         */
        getOpportunities() { return _opportunities; },

        /**
         * 设置场景机会列表（init 时调用一次）。
         * @param {Array<Object>} list - 机会数据数组
         */
        setOpportunities(list) { _opportunities = list; },

        /**
         * 根据当前模式获取对应的数据列表。
         * 用于渲染左侧列表，避免手动判断 currentMode。
         * @returns {Array<Object>} 当前模式下的列表（abilities 或 opportunities）
         */
        getCurrentList() {
            return _currentMode === 'ability' ? _abilities : _opportunities;
        },

        /**
         * 根据当前选中的 ID 获取对应的完整数据对象。
         * 用于渲染右侧详情/匹配结果。
         * @returns {Object|null} 当前选中项的数据对象，未选中时返回 null
         */
        getCurrentItem() {
            if (_selectedId == null) return null;
            const list = this.getCurrentList();
            return list.find(item => item.id === _selectedId) || null;
        },

        // ================================================================
        // 4. 匹配参数配置
        // ================================================================

        /**
         * 获取默认配置的深拷贝。
         * 用于"恢复默认"操作，确保不会意外修改常量。
         * @returns {Object} 默认配置的副本
         */
        getDefaultConfig() {
            return JSON.parse(JSON.stringify(DEFAULT_CONFIG));
        },

        /**
         * 获取当前匹配配置。
         * @returns {Object|null} 配置对象
         */
        getConfig() { return _config; },

        /**
         * 设置当前匹配配置。
         * @param {Object} config - 配置对象
         */
        setConfig(config) { _config = config; },

        /**
         * 获取配置备份（打开配置面板时创建的副本）。
         * 取消编辑时用于恢复原始配置。
         * @returns {Object|null} 配置备份对象
         */
        getConfigBackup() { return _configBackup; },

        /**
         * 设置配置备份。传入的对象将被深拷贝存储。
         * @param {Object|null} cfg - 要备份的配置对象，null 表示清除备份
         */
        setConfigBackup(cfg) {
            _configBackup = cfg ? JSON.parse(JSON.stringify(cfg)) : null;
        },

        // ================================================================
        // 5. 维度元信息（v3 新增，动态维度系统核心）
        // ================================================================

        /**
         * 获取维度元信息列表。
         * 每个维度定义了一个匹配计算单元，包含权重、字段、方法等。
         * @returns {Array<Object>|null} [{id, label, weight_key, weight, color, icon, detail_type, params}, ...]
         */
        getDimensions() { return _dimensions; },

        /**
         * 设置维度元信息列表。init() 时从 /api/dimensions 加载。
         * @param {Array<Object>} dims - 维度数组
         */
        setDimensions(dims) { _dimensions = dims; },

        /**
         * 从维度元信息推导出所有有效的权重键名列表。
         * 用于动态渲染配置面板的权重滑块。
         *
         * 优先级：
         *  1. 如果维度数据已加载 → 返回维度定义的 weight_key 数组
         *  2. 如果维度未加载 → 回退到默认的固定列表（domain/text/region）
         *
         * @returns {string[]} 权重键名数组，如 ['domain_weight', 'text_weight', 'region_weight']
         */
        getWeightKeys() {
            if (_dimensions && _dimensions.length > 0) {
                return _dimensions.map(d => d.weight_key);
            }
            // 维度未加载时的回退值
            return ['domain_weight', 'text_weight', 'region_weight'];
        },

        /**
         * 根据 weight_key 查找对应的维度元信息。
         * 用于在配置面板中渲染滑块时获取维度的显示名称、颜色等。
         *
         * @param {string} weightKey - 权重键名，如 'domain_weight'
         * @returns {Object|null} 维度对象，未找到时返回 null
         */
        getDimensionByWeightKey(weightKey) {
            if (!_dimensions) return null;
            return _dimensions.find(d => d.weight_key === weightKey) || null;
        },

        /**
         * 根据 dim_id 查找对应的维度元信息。
         * 用于删除维度、查看维度详情等场景。
         *
         * @param {number|string} dimId - 维度的唯一 ID
         * @returns {Object|null} 维度对象，未找到时返回 null
         */
        getDimensionById(dimId) {
            if (!_dimensions) return null;
            return _dimensions.find(d => d.id === dimId) || null;
        },
    };
})();
