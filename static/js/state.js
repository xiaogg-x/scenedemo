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
    // 内部状态变量
    // ====================================================================

    let _currentMode    = 'ability';      // 当前模式：'ability'（能力→机会） 或 'opportunity'（机会→能力）
    let _selectedId     = null;            // 当前选中项的 ID
    let _abilities      = [];              // 全部场景能力列表（缓存）
    let _opportunities  = [];              // 全部场景机会列表（缓存）
    let _config         = null;            // 当前匹配参数配置（从后端 /api/config 获取或匹配结果携带）

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
        }
    };
})();
