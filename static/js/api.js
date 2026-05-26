/**
 * api.js —— API 请求层
 *
 * 职责：封装所有与后端 Flask 服务通信的 fetch 请求。
 * 每个函数对应一个后端接口，统一处理请求和错误。
 *
 * 所有请求的基础 URL 为相对路径（前后端同域部署）。
 */

const BASE_URL = '';


/**
 * 获取全部场景能力列表（摘要字段）。
 *
 * 返回格式：
 *   [{id, name, company, domain}, ...]
 */
async function fetchAbilities() {
    const res = await fetch(`${BASE_URL}/api/abilities`);
    if (!res.ok) throw new Error(`加载能力列表失败: ${res.status}`);
    return await res.json();
}


/**
 * 获取全部场景机会列表（摘要字段）。
 *
 * 返回格式：
 *   [{id, name, domain, sub_domain, area}, ...]
 */
async function fetchOpportunities() {
    const res = await fetch(`${BASE_URL}/api/opportunities`);
    if (!res.ok) throw new Error(`加载机会列表失败: ${res.status}`);
    return await res.json();
}


/**
 * 为指定场景能力匹配 Top3 场景机会。
 *
 * 参数:
 *   abilityId (number): 场景能力的序号 ID
 *
 * 返回格式：
 *   {source: {...}, matches: [{target: {...}, domain_score, text_score, total_score}]}
 */
async function fetchMatchForAbility(abilityId) {
    const res = await fetch(`${BASE_URL}/api/match/ability/${abilityId}`);
    if (!res.ok) throw new Error(`匹配请求失败: ${res.status}`);
    return await res.json();
}


/**
 * 为指定场景机会匹配 Top3 场景能力。
 *
 * 参数:
 *   oppId (number): 场景机会的序号 ID
 *
 * 返回格式：
 *   {source: {...}, matches: [{target: {...}, domain_score, text_score, total_score}]}
 */
async function fetchMatchForOpportunity(oppId) {
    const res = await fetch(`${BASE_URL}/api/match/opportunity/${oppId}`);
    if (!res.ok) throw new Error(`匹配请求失败: ${res.status}`);
    return await res.json();
}


/**
 * 获取当前匹配参数配置。
 *
 * 返回格式：
 *   {domain_weight, text_weight, top_n, text_max_length}
 */
async function fetchConfig() {
    const res = await fetch(`${BASE_URL}/api/config`);
    if (!res.ok) throw new Error(`获取配置失败: ${res.status}`);
    return await res.json();
}


/**
 * 更新匹配参数配置。
 *
 * 参数:
 *   newConfig (object): 要更新的配置字段，如 {domain_weight: 0.7}
 *
 * 返回格式：
 *   {domain_weight, text_weight, top_n, text_max_length}  // 更新后的完整配置
 */
async function updateConfigAPI(newConfig) {
    const res = await fetch(`${BASE_URL}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || `更新配置失败: ${res.status}`);
    }
    return await res.json();
}


/**
 * 获取维度元信息 + 当前配置值 (v3)。
 *
 * 返回格式：
 *   {
 *     config: {domain_weight, text_weight, ...},
 *     dimensions: [{id, label, weight_key, weight, color, icon, detail_type, params: {...}}, ...]
 *   }
 */
async function fetchDimensions() {
    const res = await fetch(`${BASE_URL}/api/dimensions`);
    if (!res.ok) throw new Error(`获取维度信息失败: ${res.status}`);
    return await res.json();
}


/**
 * 获取能力侧和机会侧可用于匹配的字段列表。
 *
 * 返回格式：
 *   {ability: [...], opportunity: [...]}
 */
async function fetchFields() {
    const res = await fetch(`${BASE_URL}/api/fields`);
    if (!res.ok) throw new Error(`获取字段列表失败: ${res.status}`);
    return await res.json();
}


/**
 * 获取可用匹配方法及其默认参数。
 *
 * 返回格式：
 *   {string_match: {default_detail_type, default_params, ...}, bigram: {...}}
 */
async function fetchDimensionMethods() {
    const res = await fetch(`${BASE_URL}/api/dimensions/methods`);
    if (!res.ok) throw new Error(`获取匹配方法失败: ${res.status}`);
    return await res.json();
}


/**
 * 添加新匹配维度。
 *
 * body 格式：
 *   {label, method, ability_fields, opportunity_fields,
 *    method_labels, icon, color, score_label, params}
 *
 * 返回格式：
 *   {success, message, dimension: {...}}
 */
async function addDimensionAPI(dimDef) {
    const res = await fetch(`${BASE_URL}/api/dimensions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dimDef),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || `添加维度失败: ${res.status}`);
    }
    return await res.json();
}


/**
 * 删除指定匹配维度。
 *
 * 返回格式：
 *   {success, message}
 */
async function deleteDimensionAPI(dimId) {
    const res = await fetch(`${BASE_URL}/api/dimensions/${dimId}`, {
        method: 'DELETE',
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || `删除维度失败: ${res.status}`);
    }
    return await res.json();
}
