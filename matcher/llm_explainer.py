# -*- coding: utf-8 -*-
"""
llm_explainer.py —— LLM 匹配结果解释生成模块

══════════════════════════════════════════════════════════════════════════════
模块概述
══════════════════════════════════════════════════════════════════════════════

本模块负责将匹配引擎输出的「结构化得分数据」转换为「人类可读的
中文解释文本」。它调用大语言模型（LLM），根据匹配双方的信息和各维度
的实际得分，生成通俗易懂的分析报告。

══════════════════════════════════════════════════════════════════════════════
核心能力
══════════════════════════════════════════════════════════════════════════════

  1. 提示词工程（_build_prompt）
     将匹配数据精心组织为结构化 prompt，引导 LLM 输出有观点、有依据的分析。
     Prompt 包含：能力信息块 + 机会信息块 + 各维度评分详情 + 综合得分。

  2. SSE 流式输出（generate_explanation_stream）
     通过 Server-Sent Events 协议逐 token 返回 LLM 的输出，
     前端可以实现「打字机效果」的实时展示体验。

  3. 内存缓存机制（_make_cache_key / _explain_cache）
     基于 (ability_id, opp_id, dims_fingerprint) 的三级缓存 key，
     避免相同匹配组合重复调用付费 API。

  4. OpenRouter API 集成
     兼容 OpenAI API 格式，通过 OpenRouter 平台访问多种开源/商业模型。
     支持代理配置，适应国内网络环境。

══════════════════════════════════════════════════════════════════════════════
推荐使用的免费模型（OpenRouter 平台）
══════════════════════════════════════════════════════════════════════════════

  - deepseek/deepseek-chat-v3-0324:free    — 中文表现优秀，响应速度快（推荐默认）
  - google/gemma-3-4b-it:free              — 轻量级模型，适合简单场景
  - mistralai/mistral-7b-instruct:free     — 通用能力强，多语言支持好

══════════════════════════════════════════════════════════════════════════════
API 接口格式
══════════════════════════════════════════════════════════════════════════════

  采用 OpenAI 兼容格式（Chat Completions API）：
    Base URL: https://openrouter.ai/api/v1/chat/completions
    认证方式: Bearer Token（API Key）

  请求头特殊字段：
    HTTP-Referer: OpenRouter 要求的来源标识（用于统计和计费）
    X-Title:      可选的应用名称

══════════════════════════════════════════════════════════════════════════════
已知问题与解决方案：中文编码修复
══════════════════════════════Router 的 SSE 响应 Content-Type 为
'text/event-stream'（不含 charset），requests 库默认按 ISO-8859-1 解码，
导致中文字符被错误解码为乱码。

  解决方案：在读取 SSE 流之前显式设置 response.encoding = 'utf-8'，
            强制使用 UTF-8 解码整个响应体。这是本模块的一个关键 bug fix。
"""

import hashlib
import json
import time
import requests

# ============================================================================
# 内存缓存系统（进程生命周期内有效，进程重启后自动清空）
# ============================================================================
#
# 缓存数据结构：
#   key   → tuple(ability_id, opp_id, dims_fingerprint)
#   value → tuple(full_text: str, timestamp: float)
#
# 设计要点：
#   - fingerprint 包含维度列表的结构信息（id + focus_description 的 MD5 摘要）
#     当用户增删维度或修改关注角度描述时，fingerprint 变化，旧缓存自动失效
#   - timestamp 用于未来可能的 TTL（生存时间）过期策略（当前版本未实现自动过期）
#   - 缓存存储在内存中，无 I/O 开销，但进程重启后全部丢失
#

_explain_cache = {}  # 全局缓存字典


def _make_cache_key(ability_id, opp_id, dims):
    """
    生成用于查询/存储缓存的复合 key。

    ══════════════════════════════════════════════════════════════════════
    Key 设计：三级指纹
    ══════════════════════════════════════════════════════════════════════

      第一层 — ability_id: 能力的唯一标识符
        确保不同能力的匹配结果不会互相混淆

      第二层 — opp_id: 机会的唯一标识符
        确保同一能力对不同机会的解释各自独立

      第三层 — dims_fingerprint: 维度配置的结构指纹
        将所有维度的 (id, focus_description) 序列化后取 MD5 前 8 位。
        这样当以下情况发生时，缓存自动失效：
          * 新增或删除了维度 → 列表长度变化 → fingerprint 不同
          * 修改了某维度的 focus_description → 内容变化 → fingerprint 不同
          * 调整了维度顺序 → sort_keys 保证排序不影响 fingerprint

    为什么用 MD5 而不用完整字符串？
      - 完整的 JSON 字符串作为 dict key 太长（可能几百字节）
      - MD5 前 8 位（16 个 hex 字符）在当前场景下碰撞概率极低
      - 同时具备可读性（调试时可以快速对比）

    参数:
        ability_id (str|int): 场景能力的唯一 ID
        opp_id     (str|int): 场景机会的唯一 ID
        dims       (list[dict]): 当前维度注册表列表

    返回:
        tuple: (ability_id, opp_id, fingerprint_str) 可哈希的元组，适合做 dict key
    """
    # 将维度列表序列化为排序后的 JSON 字符串
    # sort_keys=True 保证维度顺序变化不影响指纹
    # ensure_ascii=False 保留中文字符（确保编码一致性）
    dims_info = json.dumps(
        [(d['id'], d.get('focus_description', '')) for d in dims],
        sort_keys=True, ensure_ascii=False
    )
    # 取 MD5 哈希的前 8 个字符作为指纹（足够区分大多数配置变更场景）
    fingerprint = hashlib.md5(dims_info.encode('utf-8')).hexdigest()[:8]
    return (ability_id, opp_id, fingerprint)


def get_cached_explanation(ability_id, opp_id, dims):
    """
    查询缓存中是否已有该匹配组合的解释文本。

    参数:
        ability_id (str|int): 能力 ID
        opp_id     (str|int): 机会 ID
        dims       (list[dict]): 当前维度列表（用于计算 fingerprint）

    返回:
        str|None: 命中返回完整解释文本，未命中返回 None
    """
    key = _make_cache_key(ability_id, opp_id, dims)
    entry = _explain_cache.get(key)
    if entry:
        return entry[0]  # 返回 (full_text, timestamp) 中的 full_text
    return None


def clear_cache(ability_id=None, opp_id=None):
    """
    清除解释缓存。

    支持两种清除模式：

      模式A — 全量清除（不传参数或传 None）
        清空 _explain_cache 中所有条目。
        适用场景：修改了全局提示词模板后需要刷新所有缓存。

      模式B — 定向清除（同时传入 ability_id 和 opp_id）
        只清除指定 (能力, 机会) 组合的所有缓存条目。
        注意：会清除该组合下所有 dims_fingerprint 的缓存，
        因为用户可能刚刚修改了维度配置需要重新生成。

    参数:
        ability_id (str|int|None): 能力 ID（模式B 必填）
        opp_id     (str|int|None): 机会 ID（模式B 必填）
    """
    global _explain_cache
    if ability_id is not None and opp_id is not None:
        # 定向删除：先收集待删 key（避免遍历时修改字典）
        to_delete = []
        for key in _explain_cache:
            # key 是三元组 (ability_id, opp_id, fingerprint)，比较前两个元素
            if key[0] == ability_id and key[1] == opp_id:
                to_delete.append(key)
        for k in to_delete:
            del _explain_cache[k]
    else:
        # 全量清空
        _explain_cache.clear()


# ============================================================================
# 提示词工程模块
# ============================================================================

def _build_prompt(ability_data, opp_data, dims, scores_by_dim):
    """
    构建发送给 LLM 的分析提示词（Prompt Engineering）。

    ══════════════════════════════════════════════════════════════════════
    Prompt 结构设计
    ══════════════════════════════════════════════════════════════════════

    本函数采用「结构化信息注入」策略构建 prompt：

      ┌─────────────────────────────────────────────┐
      │  System Role: 你是场景匹配分析专家           │
      │                                             │
      │  ┌─ 能力信息块 ─┐                          │
      │  │ 名称/领域/区域/概述/亮点/成效/客户      │  ← 上下文信息
      │  ├──────────────┤                          │
      │  │ 机会信息块    │                          │
      │  │ 领域/子领域/区域/概述/合作方向/类别/单位│  ← 上下文信息
      │  ├──────────────┤                          │
      │  │ 维度评分详情  │                          │  ← 核心推理依据
      │  │ 每个维度的：关注角度/原始分/权重/贡献/详情│
      │  ├──────────────┤                          │
      │  │ 综合得分      │                          │  ← 总体参考
      │  └──────────────┘                          │
      │                                             │
      │  输出要求：                                  │  ← 任务指令
      │  匹配优势 / 存在差距 / 综合评价             │
      └─────────────────────────────────────────────┘

    ══════════════════════════════════════════════════════════════════════
    关键设计决策
    ══════════════════════════════════════════════════════════════════════

    1. 注入原始得分而非只给总分：
       LLM 可以看到每个维度的具体表现，从而给出更有针对性的分析。
       例如：「文本匹配得分低是因为能力概述偏重技术细节，
       而机会更关注应用场景描述。」

    2. 注入 focus_description（关注角度描述）：
       每个 dimension 定义中的 focus_description 字段告诉 LLM
       这个维度"应该关注什么"，帮助它从正确的角度解读得分。

    3. detail 截断到 500 字符：
       防止 bigram/vector 方法的详细数据（可能包含大量 bigram 列表）
       过长而挤占 LLM 的上下文窗口。

    4. 输出字数控制（200-400 字）：
       在 prompt 中明确限制输出长度，避免 LLM 生成冗长的套话。
       配合 max_tokens=800 的硬上限双重保险。

    参数:
        ability_data   (dict): 场景能力的完整数据行（含 name, company, domain 等）
        opp_data       (dict): 场景机会的完整数据行（含 name, domain, area 等）
        dims           (list[dict]): 维度注册表（需要 focus_description 字段）
        scores_by_dim  (dict): {dim_id: {score, detail, weight}, ...} 匹配得分

    返回:
        tuple[str, float]: (构造好的 prompt 文本, 计算出的综合总分)
                           总分用于在 prompt 中告知 LLM 匹配的整体水平
    """
    # ---- 构建场景能力信息块 ----
    # 使用 f-string 格式化为结构化文本，每行一个字段
    # .get() 方法提供 '未知' 作为默认值，防止 KeyError 且让 LLM 知道数据缺失
    ability_info = f"""【场景能力 —— {ability_data.get('name', '未知')}】
- 企业名称：{ability_data.get('company', '未知')}
- 所属产业领域：{ability_data.get('domain', '未知')}
- 所属区域：{ability_data.get('district', '未知')}
- 能力概述：{ability_data.get('overview', '未知')}
- 核心亮点：{ability_data.get('highlight', '未知')}
- 应用成效：{ability_data.get('effect', '未知')}
- 意向对接客户：{ability_data.get('target_customer', '未知')}"""

    # ---- 构建场景机会信息块 ----
    opp_info = f"""【场景机会 —— {opp_data.get('name', '未知')}】
- 应用场景所属领域：{opp_data.get('domain', '未知')}
- 子领域：{opp_data.get('sub_domain', '未知')}
- 所属区域：{opp_data.get('area', '未知')}
- 应用场景概述：{opp_data.get('overview', '未知')}
- 欢迎合作方向：{opp_data.get('welcome', '未知')}
- 机会类别：{opp_data.get('category', '未知')}
- 实施单位：{opp_data.get('unit', '未知')}"""

    # ---- 构建各维度评分详情块 ----
    dim_lines = []
    for dim in dims:
        dim_id = dim['id']
        label = dim.get('label', dim_id)
        focus = dim.get('focus_description', '（未定义关注角度）')
        ds = scores_by_dim.get(dim_id, {})
        score = ds.get('score', 0)
        weight = ds.get('weight', 0)
        detail = ds.get('detail', '')

        # detail 的类型处理：string_match 返回 str，bigram/vector 返回 dict
        # 统一转为可读字符串以便嵌入 prompt
        if isinstance(detail, dict):
            # bigram/vector 的 detail 是结构化字典，用 JSON 格式化后截断
            detail_str = json.dumps(detail, ensure_ascii=False, indent=2)
        else:
            detail_str = str(detail)

        dim_lines.append(f"""### {dim['icon']} {label}
- 关注角度：{focus}
- 原始得分：{score:.2f}（满分 1.0）
- 权重：{weight:.2f}
- 加权贡献：{score * weight:.2f}
- 匹配详情：{detail_str[:500]}""")  # 截断 500 字符防止 prompt 过长

    dims_text = '\n'.join(dim_lines)

    # ---- 计算综合加权总分 ----
    # 这里独立计算一次（而非直接用传入的 total_score），保证 prompt 中的分数是准确的
    total = sum(
        scores_by_dim.get(d['id'], {}).get('score', 0) *
        scores_by_dim.get(d['id'], {}).get('weight', 0)
        for d in dims
    )

    # ---- 组装最终 prompt ----
    # 角色设定 + 任务描述 + 上下文数据 + 输出格式要求
    prompt = f"""你是一个场景匹配分析专家。请根据以下匹配结果，用通俗易懂的中文解释：

**为什么这个「场景能力」和「场景机会」能够匹配上？匹配的优势在哪里？可能存在哪些差距？**

请从以下角度逐一分析，最后给出综合评价（控制在 200-400 字）：

{ability_info}

{opp_info}

【匹配维度得分详情】
{dims_text}

【综合得分】{total:.2f}（满分 1.0）

请按以下结构输出：
1. **匹配优势**：哪些维度匹配得最好，分别说明原因
2. **存在差距**：哪些维度匹配较弱或未匹配上，原因是什么
3. **综合评价**：整体匹配程度如何，是否值得重点关注，是否存在互补空间"""

    return prompt, total


# ============================================================================
# LLM 调用模块（流式输出 + 代理支持 + 错误处理）
# ============================================================================

def generate_explanation_stream(ability_data, opp_data, dims, scores_by_dim, config):
    """
    **流式生成匹配解释**—— Python Generator 函数，逐 token yield 文本。

    ══════════════════════════════════════════════════════════════════════
    SSE 流式协议说明
    ══════════════════════════════════════════════════════════════════════

    本函数是一个 Python generator（生成器），通过 `yield` 逐个返回 LLM 输出的
    文本片段（token）。Flask 路由可以将此 generator 包装为 SSE 响应流：

      @app.route('/api/explain/<ability_id>/<opp_id>')
      def explain(ability_id, opp_id):
          def sse_stream():
              for chunk in generate_explanation_stream(...):
                  yield f'data: {json.dumps({"content": chunk})}\n\n'
          return Response(sse_stream(), mimetype='text/event-stream')

    前端通过 EventSource API 或 fetch + ReadableStream 实时接收每个 chunk，
    实现「打字机效果」的用户体验。

    ══════════════════════════════════════════════════════════════════════
    请求参数构建
    ══════════════════════════════════════════════════════════════════════

      payload 结构（OpenAI Chat Completions 格式）：
      {
        model: "deepseek/deepseek-chat-v3-0324:free",  // 模型选择
        messages: [
          {role: "system", content: "角色设定..."},    // 系统提示词
          {role: "user",   content: "完整的分析prompt"}  // 用户消息（由 _build_prompt 构建）
        ],
        stream: true,              // 启用流式输出
        max_tokens: 800,           // 最大生成长度（硬上限）
        temperature: 0.7,          // 创造性温度（0=确定性，1=创造性；0.7 为平衡值）
      }

    ══════════════════════════════════════════════════════════════════════
    中文编码修复（重要！）
    ══════════════════════════════════════════════════════════════════════

    OpenRouter 的 SSE 响应头的 Content-Type 为 'text/event-stream'（无 charset 声明）。
    Python requests 库对这种 Content-Type 默认使用 ISO-8859-1 编码解码，
    这会导致中文字节被误解码为乱码字符（如 "ä½ åºç¨" 之类的 mojibake）。

    修复方法：在开始读取响应流之前显式设置 response.encoding = 'utf-8'，
    这强制后续的所有 iter_lines() 操作都使用 UTF-8 解码。

    这是本模块最关键的 bug fix 之一——没有这行代码，
    所有包含中文的 LLM 输出都会显示为乱码。

    ══════════════════════════════════════════════════════════════════════
    异常处理策略
    ══════════════════════════════════════════════════════════════════════

      - HTTP 非 200：yield 错误消息并终止
      - 超时（60s）：yield 超时提示（可能是模型过大或网络慢）
      - 连接错误：yield 连接失败提示（检查代理/网络）
      - 其他异常：yield 通用异常提示（截断至 300 字符避免过长）
      - JSON 解析失败（损坏的 SSE 数据）：静默跳过该行继续处理

    所有错误都以 [错误] 前缀标记，前端可以据此判断是否为异常内容。

    参数:
        ability_data  (dict): 场景能力的完整字段数据
        opp_data      (dict): 场景机会的完整字段数据
        dims          (list[dict]): 维度注册表（含 focus_description）
        scores_by_dim (dict): {dim_id: {score, detail, weight}} 各维度得分
        config        (dict): LLM 配置字典，包含：
                            - endpoint (str): API 端点 URL
                            - api_key   (str): API 密钥
                            - model     (str): 模型名
                            - proxy     (str): 可选的 HTTP 代理地址

    Yields:
        str: LLM 输出的文本片段（每次一个或多个 token）
             正常内容为纯文本，错误以 '[错误]' 前缀标识
    """
    # 从 config 中提取连接参数
    proxy_url = config.get('proxy', '')
    endpoint = config.get('endpoint', 'https://openrouter.ai/api/v1/chat/completions')
    api_key = config.get('api_key', '')
    model = config.get('model', 'deepseek/deepseek-chat-v3-0324:free')  # 默认使用 DeepSeek 免费版

    # 调用提示词工程模块构建完整的分析 prompt
    prompt, total = _build_prompt(ability_data, opp_data, dims, scores_by_dim)

    # ---- 构建 HTTP 请求头 ----
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',         # Bearer Token 认证
        'HTTP-Referer': 'http://localhost:5000',       # OpenRouter 要求的来源字段
        'X-Title': 'Scene Matching Demo',               # 可选的应用标识
    }

    # ---- 构建请求体（OpenAI Chat Completions 格式）----
    payload = {
        'model': model,
        'messages': [
            # System 消息：设定 AI 的角色和行为规范
            {
                'role': 'system',
                'content': (
                    '你是一个专业的场景匹配分析专家。'
                    '你的任务是根据匹配算法给出的各维度得分，'
                    '用通俗易懂的中文解释为什么两个场景要素能够匹配。'
                    '回答要求：有观点、有依据、不套话、控制在300字左右。'
                )
            },
            # User 消息：包含所有匹配数据的分析请求
            {
                'role': 'user',
                'content': prompt
            }
        ],
        'stream': True,           # 关键：启用 SSE 流式输出
        'max_tokens': 800,        # 硬性上限：最多生成 800 个 token
        'temperature': 0.7,       # 温度参数：0.7 在"准确性"和"创造性"之间取平衡
    }

    # 代理设置（可选）：适用于需要翻墙访问 OpenRouter 的国内环境
    proxies = None
    if proxy_url:
        proxies = {
            'http': proxy_url,
            'https': proxy_url,
        }

    try:
        # 发起 POST 请求（stream=True 启用流式接收）
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            proxies=proxies,
            stream=True,           # 不一次性下载全部内容，而是按需读取
            timeout=60,            # 60 秒总超时（含连接和读取）
        )

        # HTTP 状态码检查
        if response.status_code != 200:
            # yield 错误消息后 return 终止生成器
            yield f'[错误] LLM 请求失败 (HTTP {response.status_code})：{response.text[:200]}'
            return

        # ═════════════════════════════════════════════════════
        # 关键修复：强制 UTF-8 编码
        # ═════════════════════════════════════════════════════
        #
        # OpenRouter 的 SSE 响应 Content-Type 为 text/event-stream（无 charset），
        # requests 库默认按 ISO-8859-1（Latin-1）解码，
        # 这会导致中文字节被错误解释为单字节西欧字符 → 乱码（mojibake）。
        #
        # 例如 UTF-8 编码的 "匹配" (E5 匹配 8D 8C A5 88) 在 ISO-8859-1 下会被解读为
        # 五个乱码字符 "åŒ¹é…"。
        #
        # 显式设置 encoding='utf-8' 后，iter_lines(decode_unicode=True) 会正确地
        # 用 UTF-8 解码每一行，中文字符正常显示。
        # ═════════════════════════════════════════════════════
        response.encoding = 'utf-8'

        # 逐行读取 SSE 流（Server-Sent Events 格式）
        for line in response.iter_lines(decode_unicode=True):
            # 跳过空行和注释行（SPE 规范中以 ':' 开头的行为注释）
            if not line or not line.startswith('data: '):
                continue

            data_str = line[6:]  # 去掉 "data: " 前缀，得到 JSON 字符串

            # SSE 流结束标记
            if data_str == '[DONE]':
                break

            try:
                # 解析 SSE 数据负载（OpenAI 格式的 delta 对象）
                data = json.loads(data_str)
                choices = data.get('choices', [])
                if choices:
                    # 提取增量文本（delta.content 是本次新增的文本片段）
                    delta = choices[0].get('delta', {})
                    content = delta.get('content', '')
                    if content:
                        yield content  # 将文本片段推送给调用方（前端 SSE 响应）
            except json.JSONDecodeError:
                # 某些行可能不是合法 JSON（如心跳包等），静默跳过
                continue

    except requests.exceptions.Timeout:
        # 60 秒内未完成响应（可能是模型排队、网络拥塞等）
        yield '[错误] LLM 请求超时（60s），请检查网络或代理配置。'
    except requests.exceptions.ConnectionError as e:
        # 无法建立 TCP 连接（DNS 失败、代理不可达、服务器拒绝等）
        yield f'[错误] 无法连接 LLM 服务：{str(e)[:200]}'
    except Exception as e:
        # 兜底异常处理（捕获上述分类之外的所有异常）
        yield f'[错误] LLM 调用异常：{str(e)[:300]}'


def generate_and_cache(ability_id, opp_id, ability_data, opp_data, dims,
                       scores_by_dim, config):
    """
    非流式版本的解释生成器：完整生成解释文本并存入内存缓存。

    ══════════════════════════════════════════════════════════════════════
    与 generate_explanation_stream() 的关系
    ══════════════════════════════════════════════════════════════════════

    本函数是对流式生成器的封装：
      1. 先查缓存 → 命中则直接返回（节省 API 调用费用和时间）
      2. 未命中 → 调用 generate_explanation_stream() 收集所有 token
      3. 收集完毕后将完整文本存入 _explain_cache
      4. 返回完整文本

    适用场景：
      - 需要「一次性获取全文」而非逐步推送的场景（如后台批量生成）
      - 需要将结果持久化到缓存的场景

    参数:
        ability_id  (str|int): 能力唯一 ID（用于缓存 key）
        opp_id      (str|int): 机会唯一 ID（用于缓存 key）
        ability_data (dict):   能力数据
        opp_data    (dict):    机会数据
        dims        (list[dict]): 维度注册表
        scores_by_dim (dict):  维度得分
        config      (dict):    LLM 配置

    返回:
        tuple[bool, str]:
            - cached (bool): True 表示命中缓存（直接返回缓存文本，无需 API 调用）
                             False 表示新生成（已存入缓存）
            - full_text (str): 完整的解释文本
    """
    key = _make_cache_key(ability_id, opp_id, dims)

    # 第一步：查缓存
    existing = _explain_cache.get(key)
    if existing:
        return True, existing[0]  # (cached=True, cached_text)

    # 第二步：缓存未命中 → 调用流式生成器收集完整文本
    full_text = ''
    for chunk in generate_explanation_stream(
        ability_data, opp_data, dims, scores_by_dim, config
    ):
        full_text += chunk  # 逐个拼接 token 直到生成器结束

    # 第三步：存入缓存（附带时间戳供未来 TTL 过期策略使用）
    _explain_cache[key] = (full_text, time.time())
    return False, full_text  # (cached=False, newly_generated_text)
