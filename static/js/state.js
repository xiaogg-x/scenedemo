/**
 * state.js —— 全局状态管理模块 (v2)
 *
 * 职责：维护前端页面的全部运行时状态，对外暴露 getter/setter 接口。
 * v2 新增：当前匹配参数配置（config）状态。
 * 所有 DOM 渲染函数和事件处理函数都通过 state.js 读取/更新状态。
 */

const State = (function () {
    'use strict';

    // ====================================================================
    // 默认配置常量（与后端 engine.py 中的 MATCH_CONFIG 保持一致）
    // ====================================================================
    const DEFAULT_CONFIG = {
        domain_weight:   0.6,
        text_weight:     0.4,
        top_n:           3,
        text_max_length: 300,
    };

    // ====================================================================
    // 内部状态变量
    // ====================================================================

    let _currentMode    = 'ability';      // 当前模式：'ability'（能力→机会） 或 'opportunity'（机会→能力）
    let _selectedId     = null;            // 当前选中项的 ID
    let _abilities      = [];              // 全部场景能力列表（缓存）
    let _opportunities  = [];              // 全部场景机会列表（缓存）
    let _config         = null;            // 当前匹配参数配置（从后端 /api/config 获取或匹配结果携带）
    let _configBackup   = null;            // 配置备份（用于「取消」时恢复）

    // ====================================================================
    // 公开接口
    // ====================================================================

    return {
        /** 获取当前模式 */
        getMode() {
            return _currentMode;
        },

        /** 设置当前模式 */
        setMode(mode) {
            _currentMode = mode;
        },

        /** 获取当前选中 ID */
        getSelectedId() {
            return _selectedId;
        },

        /** 设置当前选中 ID */
        setSelectedId(id) {
            _selectedId = id;
        },

        /** 获取场景能力列表 */
        getAbilities() {
            return _abilities;
        },

        /** 设置场景能力列表 */
        setAbilities(list) {
            _abilities = list;
        },

        /** 获取场景机会列表 */
        getOpportunities() {
            return _opportunities;
        },

        /** 设置场景机会列表 */
        setOpportunities(list) {
            _opportunities = list;
        },

        /** 获取当前匹配参数配置 */
        getConfig() {
            return _config;
        },

        /** 设置当前匹配参数配置 */
        setConfig(config) {
            _config = config;
        },

        /**
         * 根据当前模式获取对应的列表数据。
         * 能力模式 → 返回能力列表；机会模式 → 返回机会列表
         */
        getCurrentList() {
            return _currentMode === 'ability' ? _abilities : _opportunities;
        },

        /**
         * 根据当前模式获取对应的 item。
         * 能力模式 → 从 _abilities 中按 ID 查找
         * 机会模式 → 从 _opportunities 中按 ID 查找
         */
        getCurrentItem() {
            if (_selectedId == null) return null;
            const list = this.getCurrentList();
            return list.find(item => item.id === _selectedId) || null;
        },

        /**
         * 获取默认配置副本（调用方放心修改，不影响常量）。
         */
        getDefaultConfig() {
            return JSON.parse(JSON.stringify(DEFAULT_CONFIG));
        },

        /**
         * 获取配置备份（用于「取消」时恢复）。
         */
        getConfigBackup() {
            return _configBackup;
        },

        /**
         * 设置配置备份（打开配置面板时调用，保存当前快照）。
         */
        setConfigBackup(cfg) {
            _configBackup = cfg ? JSON.parse(JSON.stringify(cfg)) : null;
        }
    };
})();
