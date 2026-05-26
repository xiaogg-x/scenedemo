/**
 * state.js —— 全局状态管理模块 (v3)
 *
 * 职责：维护前端页面的全部运行时状态，对外暴露 getter/setter 接口。
 * v3 新增：维度元信息（dimensions）状态，替代硬编码的 DEFAULT_CONFIG。
 * 所有 DOM 渲染函数和事件处理函数都通过 state.js 读取/更新状态。
 */

const State = (function () {
    'use strict';

    // ====================================================================
    // 默认配置常量（当维度 API 未加载时使用）
    // ====================================================================
    const DEFAULT_CONFIG = {
        domain_weight:   0.4,
        text_weight:     0.3,
        region_weight:   0.3,
        top_n:           3,
        text_max_length: 300,
    };

    // ====================================================================
    // 内部状态变量
    // ====================================================================

    let _currentMode    = 'ability';
    let _selectedId     = null;
    let _abilities      = [];
    let _opportunities  = [];
    let _config         = null;
    let _configBackup   = null;
    let _dimensions     = null;  // v3: 维度元信息列表 [{id, label, weight, ...}, ...]

    // ====================================================================
    // 公开接口
    // ====================================================================

    return {
        getMode() { return _currentMode; },
        setMode(mode) { _currentMode = mode; },

        getSelectedId() { return _selectedId; },
        setSelectedId(id) { _selectedId = id; },

        getAbilities() { return _abilities; },
        setAbilities(list) { _abilities = list; },

        getOpportunities() { return _opportunities; },
        setOpportunities(list) { _opportunities = list; },

        getConfig() { return _config; },
        setConfig(config) { _config = config; },

        getCurrentList() {
            return _currentMode === 'ability' ? _abilities : _opportunities;
        },

        getCurrentItem() {
            if (_selectedId == null) return null;
            const list = this.getCurrentList();
            return list.find(item => item.id === _selectedId) || null;
        },

        getDefaultConfig() {
            return JSON.parse(JSON.stringify(DEFAULT_CONFIG));
        },

        getConfigBackup() { return _configBackup; },
        setConfigBackup(cfg) {
            _configBackup = cfg ? JSON.parse(JSON.stringify(cfg)) : null;
        },

        // ---- v3: 维度元信息 ----

        /** 获取维度元信息列表 */
        getDimensions() { return _dimensions; },

        /** 设置维度元信息列表 */
        setDimensions(dims) { _dimensions = dims; },

        /**
         * 获取有效权重 key 列表（从维度元信息推导）。
         * 如果维度未加载，回退到默认的固定列表。
         */
        getWeightKeys() {
            if (_dimensions && _dimensions.length > 0) {
                return _dimensions.map(d => d.weight_key);
            }
            return ['domain_weight', 'text_weight', 'region_weight'];
        },

        /**
         * 根据 weight_key 获取维度元信息。
         */
        getDimensionByWeightKey(weightKey) {
            if (!_dimensions) return null;
            return _dimensions.find(d => d.weight_key === weightKey) || null;
        },

        /**
         * 根据 dim_id 获取维度元信息。
         */
        getDimensionById(dimId) {
            if (!_dimensions) return null;
            return _dimensions.find(d => d.id === dimId) || null;
        },
    };
})();
