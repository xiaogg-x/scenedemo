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
