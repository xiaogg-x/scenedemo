/**
 * api.js —— API 请求层
 *
 * 职责：封装所有与后端 Flask 服务通信的 fetch 请求。
 * 每个函数对应一个后端接口，统一处理请求和错误。
 *
 * 设计模式：
 *  - 所有函数返回 Promise，由调用方使用 async/await 处理
 *  - 错误统一通过 throw new Error(message) 抛出
 *  - 基础 URL 为相对路径（前后端同域部署，无需 CORS 配置）
 *
 * 接口一览（共 11 个）：
 *  - fetchAbilities()            → GET  /api/abilities
 *  - fetchOpportunities()        → GET  /api/opportunities
 *  - fetchMatchForAbility(id)    → GET  /api/match/ability/<id>
 *  - fetchMatchForOpportunity(id)→ GET  /api/match/opportunity/<id>
 *  - fetchConfig()               → GET  /api/config
 *  - updateConfigAPI(config)     → POST /api/config
 *  - fetchDimensions()           → GET  /api/dimensions
 *  - fetchFields()               → GET  /api/fields
 *  - fetchDimensionMethods()     → GET  /api/dimensions/methods
 *  - addDimensionAPI(def)        → POST /api/dimensions
 *  - deleteDimensionAPI(id)      → DELETE /api/dimensions/<id>
 *  - fetchExplain(params, ...)   → POST /api/match/explain (SSE 流式)
 */

const BASE_URL = '';


/**
 * 获取全部场景能力列表（摘要字段）。
 *
 * 用途：页面初始化时加载左侧能力列表数据。
 * 返回格式：
 *   [{id, name, company, domain}, ...]
 *
 * @returns {Promise<Array<Object>>} 场景能力摘要数组
 * @throws {Error} 网络错误或非 2xx 响应
 */
async function fetchAbilities() {
    const res = await fetch(`${BASE_URL}/api/abilities`);
    if (!res.ok) throw new Error(`加载能力列表失败: ${res.status}`);
    return await res.json();
}


/**
 * 获取全部场景机会列表（摘要字段）。
 *
 * 用途：页面初始化时加载左侧机会列表数据。
 * 返回格式：
 *   [{id, name, domain, sub_domain, area}, ...]
 *
 * @returns {Promise<Array<Object>>} 场景机会摘要数组
 * @throws {Error} 网络错误或非 2xx 响应
 */
async function fetchOpportunities() {
    const res = await fetch(`${BASE_URL}/api/opportunities`);
    if (!res.ok) throw new Error(`加载机会列表失败: ${res.status}`);
    return await res.json();
}


/**
 * 为指定场景能力匹配 Top N 场景机会（默认 Top 3）。
 *
 * 流程：用户点击左侧能力 → 后端计算匹配 → 返回 Top N 机会。
 * 参数:
 *   abilityId (number): 场景能力的序号 ID（与数据库中 id 字段对应）
 *
 * 返回格式：
 *   {
 *     source: {id, name, company, domain, ...},   // 被匹配的能力
 *     matches: [                                    // 匹配结果列表
 *       {
 *         target: {id, name, domain, ...},          // 匹配到的机会
 *         domain_score: number,                     // 各维度得分
 *         text_score: number,
 *         total_score: number                       // 加权总分
 *       }, ...
 *     ],
 *     config: {domain_weight, text_weight, ...}    // 计算时所使用的配置
 *   }
 *
 * @param {number} abilityId - 场景能力的 ID
 * @returns {Promise<Object>} 匹配结果对象
 * @throws {Error} 匹配请求失败
 */
async function fetchMatchForAbility(abilityId) {
    const res = await fetch(`${BASE_URL}/api/match/ability/${abilityId}`);
    if (!res.ok) throw new Error(`匹配请求失败: ${res.status}`);
    return await res.json();
}


/**
 * 为指定场景机会匹配 Top N 场景能力（默认 Top 3）。
 *
 * 流程：用户切换到机会模式 → 点击左侧机会 → 后端计算匹配 → 返回 Top N 能力。
 * 与 fetchMatchForAbility 对称，方向相反。
 *
 * 参数:
 *   oppId (number): 场景机会的序号 ID
 *
 * 返回格式：
 *   {source: {...}, matches: [{target: {...}, domain_score, text_score, total_score}], config: {...}}
 *
 * @param {number} oppId - 场景机会的 ID
 * @returns {Promise<Object>} 匹配结果对象
 * @throws {Error} 匹配请求失败
 */
async function fetchMatchForOpportunity(oppId) {
    const res = await fetch(`${BASE_URL}/api/match/opportunity/${oppId}`);
    if (!res.ok) throw new Error(`匹配请求失败: ${res.status}`);
    return await res.json();
}


/**
 * 获取当前匹配参数配置。
 *
 * 用途：页面初始化和打开配置面板时读取。
 * 返回格式：
 *   {domain_weight, text_weight, top_n, text_max_length}
 *
 * @returns {Promise<Object>} 当前配置对象
 * @throws {Error} 获取配置失败
 */
async function fetchConfig() {
    const res = await fetch(`${BASE_URL}/api/config`);
    if (!res.ok) throw new Error(`获取配置失败: ${res.status}`);
    return await res.json();
}


/**
 * 更新匹配参数配置（部分更新）。
 *
 * 参数:
 *   newConfig (object): 需要更新的配置字段，可以只传要修改的字段
 *                       例如：{domain_weight: 0.7} 或 {top_n: 5, text_max_length: 500}
 *
 * 返回格式：
 *   {domain_weight, text_weight, top_n, text_max_length}  // 更新后的完整配置
 *
 * @param {Object} newConfig - 部分或全部配置字段
 * @returns {Promise<Object>} 更新后的完整配置
 * @throws {Error} 更新失败，错误信息来自后端 error 字段
 */
async function updateConfigAPI(newConfig) {
    const res = await fetch(`${BASE_URL}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig),
    });
    if (!res.ok) {
        // POST 失败时尝试解析后端返回的 JSON 错误信息
        const err = await res.json();
        throw new Error(err.error || `更新配置失败: ${res.status}`);
    }
    return await res.json();
}


/**
 * 获取维度元信息 + 当前配置值 (v3 动态维度系统)。
 *
 * 用途：页面初始化时加载，替代旧的硬编码维度列表。
 * 后端合并了 /api/config 和 /api/dimensions，一次请求获取全部。
 *
 * 返回格式：
 *   {
 *     config: {domain_weight, text_weight, ...},
 *     dimensions: [{id, label, weight_key, weight, color, icon, detail_type, params: {...}}, ...]
 *   }
 *
 * @returns {Promise<Object>} {config, dimensions}
 * @throws {Error} 获取维度信息失败
 */
async function fetchDimensions() {
    const res = await fetch(`${BASE_URL}/api/dimensions`);
    if (!res.ok) throw new Error(`获取维度信息失败: ${res.status}`);
    return await res.json();
}


/**
 * 获取能力侧和机会侧可用于匹配的字段列表。
 *
 * 用途：在"添加匹配维度"模态框中填充字段多选面板。
 * 返回格式：
 *   {ability: ["name", "domain", "description", ...], opportunity: ["name", "area", ...]}
 *
 * @returns {Promise<Object>} {ability: string[], opportunity: string[]}
 * @throws {Error} 获取字段列表失败
 */
async function fetchFields() {
    const res = await fetch(`${BASE_URL}/api/fields`);
    if (!res.ok) throw new Error(`获取字段列表失败: ${res.status}`);
    return await res.json();
}


/**
 * 获取可用匹配方法及其默认参数。
 *
 * 用途：在"添加匹配维度"模态框中填充方法下拉选项，以及渲染对应参数表单。
 * 返回格式：
 *   {
 *     string_match: {default_detail_type, default_params, ...},
 *     bigram: {default_detail_type, default_params, ...},
 *     vector_semantic: {default_detail_type, default_params, ...}
 *   }
 *
 * @returns {Promise<Object>} 方法定义对象，key 为方法名
 * @throws {Error} 获取匹配方法失败
 */
async function fetchDimensionMethods() {
    const res = await fetch(`${BASE_URL}/api/dimensions/methods`);
    if (!res.ok) throw new Error(`获取匹配方法失败: ${res.status}`);
    return await res.json();
}


/**
 * 添加新匹配维度。
 *
 * 用途：用户在"添加维度"模态框中填写后提交。
 * body 格式：
 *   {
 *     label: "维度名称",
 *     method: "string_match",
 *     ability_fields: ["field1", "field2"],
 *     opportunity_fields: ["field3"],
 *     method_labels: {ability: "标签A", opportunity: "标签B"},  // 可选
 *     icon: "📊",           // 可选
 *     color: "#3B82F6",     // 可选
 *     score_label: "得分",  // 可选
 *     params: {...}         // 可选，方法特定参数
 *   }
 *
 * 返回格式：
 *   {success: true, message: "...", dimension: {...}}
 *
 * @param {Object} dimDef - 维度定义对象
 * @returns {Promise<Object>} {success, message, dimension}
 * @throws {Error} 添加失败，错误信息来自后端 error 字段
 */
async function addDimensionAPI(dimDef) {
    const res = await fetch(`${BASE_URL}/api/dimensions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dimDef),
    });
    if (!res.ok) {
        // POST 失败时解析后端返回的错误 JSON
        const err = await res.json();
        throw new Error(err.error || `添加维度失败: ${res.status}`);
    }
    return await res.json();
}


/**
 * 删除指定匹配维度。
 *
 * 用途：在配置面板中点击维度旁的删除按钮（×）。
 * 返回格式：
 *   {success: true, message: "..."}
 *
 * @param {number|string} dimId - 要删除的维度 ID
 * @returns {Promise<Object>} {success, message}
 * @throws {Error} 删除失败，错误信息来自后端 error 字段
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


/**
 * 请求 LLM 对匹配结果生成解释（SSE 流式传输）。
 *
 * 与其他函数不同，本函数不使用 async/await，而是通过三个回调
 * 处理流式数据：onChunk、onDone、onError。
 *
 * SSE (Server-Sent Events) 协议：
 *  每个消息以 "data: " 开头，后跟 JSON 字符串。
 *  三种消息类型：
 *   - {"chunk": "文本片段"}        → 调用 onChunk
 *   - {"done": true, "cached": bool} → 调用 onDone
 *   - {"error": "错误信息"}         → 调用 onError
 *
 * 参数:
 *   params    (object): {ability_id, opp_id, match_index, mode, force_refresh}
 *   onChunk   (function): 每收到一段解释文本时回调 onChunk(chunkText)
 *   onDone    (function): 流结束时回调 onDone({cached: bool})
 *                         cached=true 表示命中后端缓存，非首次生成
 *   onError   (function): 出错时回调 onError(errorMessage)
 *
 * 返回: AbortController（调用方可通过 .abort() 取消请求，如用户关闭详情面板时）
 *
 * 工作流程：
 *  1. 创建 AbortController 用于取消请求
 *  2. 发送 POST 请求到 /api/match/explain
 *  3. 获取 response.body 的 ReadableStream reader
 *  4. 循环读取数据块，使用 TextDecoder 解码
 *  5. 按 \n 分割为 SSE 事件行，逐行解析 JSON
 *  6. 根据 JSON 内容调用对应回调
 *
 * @param {Object} params - 请求参数 {ability_id, opp_id, match_index, mode, force_refresh}
 * @param {function(string):void} onChunk - 文本块回调
 * @param {function({cached: boolean}):void} onDone - 流结束回调
 * @param {function(string):void} onError - 错误回调
 * @returns {AbortController} 用于取消请求的控制器
 */
function fetchExplain(params, onChunk, onDone, onError) {
    // 创建 AbortController，用于取消正在进行的 SSE 请求
    // 典型场景：用户切换匹配卡片时，取消前一个卡片的解释加载
    const controller = new AbortController();

    fetch(`${BASE_URL}/api/match/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: controller.signal,  // 绑定取消信号
    }).then(async (response) => {
        // 检查 HTTP 状态码（非 200 时尝试解析错误 JSON）
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            onError(err.error || `请求失败: ${response.status}`);
            return;
        }

        // 获取 ReadableStream 读取器，逐块读取 SSE 数据
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        // buffer 用于处理跨数据块的行分割
        // 例如：一个 SSE 消息 "data: {"chunk":"hello"}\n" 可能被拆在两个 chunk 中
        let buffer = '';

        // 循环读取直到流结束（done === true）
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;  // 流结束，退出循环

            // 增量解码（stream: true 确保多字节字符不会因边界截断而乱码）
            buffer += decoder.decode(value, { stream: true });

            // 按 \n 分割为完整的 SSE 事件行
            const lines = buffer.split('\n');

            // 最后一行可能不完整（下一个 chunk 的后续部分），保留在 buffer 中
            buffer = lines.pop() || '';

            for (const line of lines) {
                // SSE 协议：每条消息以 "data: " 开头
                if (!line.startsWith('data: ')) continue;

                // 提取 "data: " 之后的 JSON 字符串
                const dataStr = line.substring(6);
                try {
                    const data = JSON.parse(dataStr);

                    if (data.error) {
                        // 错误消息 → 通知调用方
                        onError(data.error);
                        return;
                    }

                    if (data.done) {
                        // 流结束消息 → 通知调用方（含是否命中缓存）
                        onDone({ cached: data.cached });
                        return;
                    }

                    if (data.chunk) {
                        // 文本块 → 逐段推送给调用方渲染
                        onChunk(data.chunk);
                    }

                    // 注意：如果 JSON 解析成功但不符合以上任一种格式，静默跳过
                } catch (e) {
                    // JSON 解析失败，跳过该行（可能是噪声数据或调试信息）
                }
            }
        }
    }).catch((err) => {
        // AbortError 是预期的取消行为（用户主动取消），不视为错误
        if (err.name === 'AbortError') return;
        // 其他错误（网络断开、超时等）→ 通知调用方
        onError(err.message || '网络错误');
    });

    // 返回 controller 供调用方 .abort()
    return controller;
}
