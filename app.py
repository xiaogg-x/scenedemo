# -*- coding: utf-8 -*-
"""
app.py —— Flask 路由层 (v3)

============================================
项目定位
============================================
本文件是"场景机会与能力匹配系统"的 Web 入口，基于 Flask 框架构建，
对外提供 RESTful API 供前端调用。

============================================
核心职责
============================================
  1. 应用启动时调用 `matcher` 包统一加载 Excel 数据到内存
  2. 提供 10+ 个 API 端点（列表、匹配、配置、维度管理、LLM 解释）
  3. 内置 CORS 支持，允许跨域访问（本地 Demo 必需）
  4. 通过 `/api/config` GET/POST 支持动态调整匹配参数
  5. 通过 `/api/dimensions` 支持维度的运行时增删
  6. 通过 `/api/match/explain` 提供 SSE 流式 LLM 解释

============================================
与 matcher 包的关系
============================================
app.py 是协调层（Controller），它：
  - 启动时调用 matcher.data_loader 加载 Excel 数据
  - 启动时调用 matcher.engine 加载配置文件
  - 启动时调用 matcher.vector_tool.pre_warm_cache 预热向量缓存
  - 请求时调用 matcher.engine 执行匹配计算
  - 请求时调用 matcher.llm_explainer 生成 LLM 解释
  - 通过 matcher.dimensions 感知和管理匹配维度

============================================
API 接口一览
============================================
  页面：
    GET  /                            → 返回前端 index.html

  列表：
    GET  /api/abilities               → 返回全部场景能力列表（摘要字段）
    GET  /api/opportunities           → 返回全部场景机会列表（摘要字段）

  匹配：
    GET  /api/match/ability/<id>      → 为指定能力返回 Top N 匹配机会（含详细得分明细）
    GET  /api/match/opportunity/<id>  → 为指定机会返回 Top N 匹配能力（含详细得分明细）
    POST /api/match/explain            → 为匹配对生成 SSE 流式 LLM 解释

  维度管理（v3 新增）：
    GET  /api/dimensions              → 返回维度注册表元信息 + 当前权重/参数配置
    GET  /api/dimensions/methods      → 返回可用匹配方法及其默认参数
    POST /api/dimensions              → 添加新维度
    DELETE /api/dimensions/<id>       → 删除指定维度

  配置：
    GET  /api/config                  → 返回当前匹配参数配置（所有权重、top_n、维度参数）
    POST /api/config                  → 更新匹配参数（含权重自动缩放）

  辅助：
    GET  /api/fields                  → 返回能力侧和机会侧的可匹配字段列表

============================================
启动方式
============================================
  python app.py
  或双击 start.bat
"""

import os
import sys
import json
from flask import Flask, jsonify, request, Response, stream_with_context

# 将项目根目录加入 sys.path，确保在任何工作目录下都能 import matcher 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- 从 matcher 包导入所有需要的公共接口 ----
# 这些函数覆盖了：数据加载、归一化、维度管理、匹配引擎、向量缓存
from matcher import (
    load_abilities,
    load_opportunities,
    match_ability_to_opportunities,
    match_opportunity_to_abilities,
    get_config,
    get_config_with_dimensions,
    update_config,
    load_config_from_file,
    get_weight_keys,
    add_dimension,
    delete_dimension,
    sync_config_with_dimensions,
    METHOD_REGISTRY,
    get_next_dim_id,
    pre_warm_cache,
    get_dimensions,
)


# ============================================================================
# Flask 应用初始化
# ============================================================================
# 创建 Flask 实例，同时指定 static_folder 和 static_url_path 将根路径绑定到
# static/ 目录，使得 /index.html 直接映射到 static/index.html
app = Flask(
    __name__,
    static_folder='static',
    static_url_path=''
)


# ============================================================================
# 内置 CORS 支持
# ============================================================================
# 由于前端通过 file:// 协议加载时可能无法直连后端，前端代码中使用 API_BASE 指向
# http://127.0.0.1:5000，因此需要 CORS 头允许跨域请求。
# 这里使用 after_request 钩子为每个响应统一添加 CORS 头，是最简单的实现方式。

@app.after_request
def add_cors_headers(response):
    """
    为每个 HTTP 响应统一添加 CORS（跨域资源共享）头。

    允许任意来源（*）、Content-Type 请求头、以及 GET/POST/DELETE/OPTIONS 方法。
    这是本地 Demo 必需的配置，生产环境应限制为具体域名。
    """
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    return response


# ============================================================================
# 数据加载（启动时一次性加载到全局变量）
# ============================================================================
# 所有场景能力和场景机会数据在 Flask 启动时从 Excel 文件中加载到内存，
# 之后所有 API 请求都直接操作这些内存数据，无需重复读取磁盘。
# 这保证了请求处理的低延迟（毫秒级）。

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '后台数据')

print('=' * 60)
print('  正在加载数据...')
print('=' * 60)

# 加载场景能力：每条包含产品名称、企业、领域、概述等 9 个字段
ALL_ABILITIES = load_abilities(os.path.join(DATA_DIR, '场景能力数据列表.xlsx'))

# 加载场景机会：每条包含项目名称、领域、细分领域、概述等 10 个字段
ALL_OPPORTUNITIES = load_opportunities(os.path.join(DATA_DIR, '场景机会数据列表.xlsx'))

print('=' * 60)
print(f'  数据加载完成：{len(ALL_ABILITIES)} 条能力，{len(ALL_OPPORTUNITIES)} 条机会')
print('=' * 60)

# 加载匹配参数配置文件（config.json），包括权重、top_n、维度参数等
load_config_from_file()

# 预热向量语义缓存——对 vector_semantic 维度引用的所有文本批量编码，
# 避免首次匹配请求因逐个编码 1000+ 条文本而超时（优化效果：54s → <1s）
# 原理：将所有能力/机会的文本字段一次性送入 sentence-transformers 模型，
#       生成向量后存入内存缓存，后续匹配直接查缓存而非重新编码。
print('=' * 60)
print('  正在预热向量语义缓存...')
print('=' * 60)
pre_warm_cache(ALL_ABILITIES, ALL_OPPORTUNITIES)
print('=' * 60)
print('  缓存预热完成，准备接受请求')
print('=' * 60)

# ============================================================================
# LLM 配置加载（从独立 llm_config.json 读取）
# ============================================================================
# LLM 配置存储在 后台数据/llm_config.json 中，启动时读取并缓存到
# LLM_CONFIG 全局字典。后续 /api/match/explain 使用这些配置调用 LLM API。
# 这样 /api/config 保存匹配参数时不会覆盖 LLM 密钥、模型和代理设置。
# 支持通过 proxy 字段配置 HTTP 代理（用于本地开发环境）。
DEFAULT_LLM_CONFIG = {
    'endpoint': 'https://openrouter.ai/api/v1/chat/completions',
    'api_key': '',
    'model': 'deepseek/deepseek-chat-v3-0324:free',
    'proxy': '',
}
LLM_CONFIG = dict(DEFAULT_LLM_CONFIG)
try:
    llm_config_path = os.path.join(DATA_DIR, 'llm_config.json')
    legacy_config_path = os.path.join(DATA_DIR, 'config.json')

    if os.path.exists(llm_config_path):
        with open(llm_config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            LLM_CONFIG.update({
                'endpoint': cfg.get('endpoint', DEFAULT_LLM_CONFIG['endpoint']),
                'api_key': cfg.get('api_key', DEFAULT_LLM_CONFIG['api_key']),
                'model': cfg.get('model', DEFAULT_LLM_CONFIG['model']),
                'proxy': cfg.get('proxy', DEFAULT_LLM_CONFIG['proxy']),
            })
    elif os.path.exists(legacy_config_path):
        # 兼容旧版本：如果用户还没有拆分配置，仍尝试读取 config.json.llm。
        with open(legacy_config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            llm_cfg = cfg.get('llm', {})
            if llm_cfg:
                LLM_CONFIG.update({
                    'endpoint': llm_cfg.get('endpoint', DEFAULT_LLM_CONFIG['endpoint']),
                    'api_key': llm_cfg.get('api_key', DEFAULT_LLM_CONFIG['api_key']),
                    'model': llm_cfg.get('model', DEFAULT_LLM_CONFIG['model']),
                    'proxy': llm_cfg.get('proxy', DEFAULT_LLM_CONFIG['proxy']),
                })
                print('[llm] 已从旧版 config.json.llm 加载配置，建议迁移到 后台数据/llm_config.json')

    has_key = 'yes' if LLM_CONFIG.get('api_key') else 'no'
    print(f'[llm] 配置已加载: endpoint={LLM_CONFIG["endpoint"]}, model={LLM_CONFIG["model"]}, proxy={LLM_CONFIG["proxy"]}, api_key={has_key}')
except Exception as e:
    print(f'[llm] 加载配置失败: {e}，使用默认值')


# ============================================================================
# API 路由定义
# ============================================================================
# 所有路由以 /api/ 为前缀，遵循 RESTful 风格。
# GET 请求用于查询，POST 用于创建/更新，DELETE 用于删除。

# ---------------------------------------------------------------------------
# 首页路由
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """返回前端单页应用入口 HTML。"""
    return app.send_static_file('index.html')


# ---------------------------------------------------------------------------
# 列表 API
# ---------------------------------------------------------------------------
# 提供能力和机会的摘要列表接口，前端用此数据渲染选择下拉菜单和搜索框。
# 返回字段经过裁剪，只包含展示必需的摘要字段，避免传输冗余数据。

@app.route('/api/abilities')
def api_abilities():
    """
    返回全部场景能力列表（摘要字段）。

    返回格式:
        JSON 数组，每项包含 id, name, company, domain, district。
        注意不返回 overview 等详细字段，前端列表页不需要这些。

    性能:
        直接遍历内存中的 ALL_ABILITIES 列表，无数据库查询开销。
    """
    summary = []
    for a in ALL_ABILITIES:
        summary.append({
            'id': a['id'],
            'name': a['name'],
            'company': a['company'],
            'domain': a['domain'],
            'district': a['district'],
        })
    return jsonify(summary)


@app.route('/api/opportunities')
def api_opportunities():
    """
    返回全部场景机会列表（摘要字段）。

    返回格式:
        JSON 数组，每项包含 id, name, domain, sub_domain, area。
        机会侧的字段和能力侧不完全相同，这是由两个数据源的差异决定的。
    """
    summary = []
    for o in ALL_OPPORTUNITIES:
        summary.append({
            'id': o['id'],
            'name': o['name'],
            'domain': o['domain'],
            'sub_domain': o['sub_domain'],
            'area': o['area'],
        })
    return jsonify(summary)


# ---------------------------------------------------------------------------
# 匹配 API (v3：含 dimension_scores)
# ---------------------------------------------------------------------------

def _build_match_response(matches, config, source):
    """
    构建统一的匹配结果响应体（v3 格式）。

    这是匹配 API 共用的响应构建函数，被 api_match_ability 和
    api_match_opportunity 两个路由共同调用。

    响应体设计遵循"v3 结构化 + v2 扁平兼容"双轨制：
      - v3：dimension_scores 字段，结构化存储每个维度的得分信息
        {dim_id: {score: 0.8, detail: "精确命中...", weight: 0.5}}
      - v2 兼容：将 dimension_scores 拍平为独立 key
        例如 domain_score=0.8, domain_match_detail="精确命中..."

    这样前端新代码可以用 dimension_scores 做精细化的维度展示，
    而旧代码（没有及时升级的）仍能通过扁平字段正常工作。

    参数:
        matches (list): 匹配结果列表，每项由 matcher.engine 生成，
                        包含 target、total_score、dimension_scores 等字段
        config  (dict):  当前匹配配置（权重、top_n 等），供前端展示
        source  (dict):  发起匹配的源实体（能力或机会）的摘要信息

    返回:
        dict: 包含 config, source, matches 三个字段的响应体
    """
    match_list = []
    for m in matches:
        target = m['target']
        # ---- 构建每个匹配条目的基础信息 ----
        entry = {
            'target': {
                'id': target['id'],
                'name': target['name'],
                'domain': target.get('domain', ''),
                # area 字段：机会侧用 'area'，能力侧用 'district'
                # 通过 get 链兼容两种数据源的不同字段名
                'area': target.get('area', target.get('district', '')),
                'overview': target.get('overview', ''),
            },
            'total_score': m['total_score'],
            'dimension_scores': m.get('dimension_scores', {}),
            'source_fields': m.get('source_fields', {}),
            'target_fields': m.get('target_fields', {}),
        }

        # ---- v2 兼容层：把 dimension_scores 拍平为独立 key ----
        # 例如 domain_score=0.8, domain_match_detail="精确命中..."
        # 前端 render.js 中既有 v3 的 dimension_scores 渲染，也有 v2 兼容读取
        if 'dimension_scores' in m:
            for dim_id, ds in m['dimension_scores'].items():
                entry[f'{dim_id}_score'] = ds['score']
                entry[f'{dim_id}_match_detail'] = ds['detail']
        else:
            # 兜底：如果引擎没返回 dimension_scores（旧版本），从扁平字段还原
            for key in m:
                if key.endswith('_score') and key != 'total_score':
                    entry[key] = m[key]
                if key.endswith('_match_detail'):
                    entry[key] = m[key]

        # ---- 透传 target 中的可选字段（机会和能力侧字段不同） ----
        # 不做硬编码，字段存在才透传，这样新增字段只需数据源增加即可
        # 无需修改此处代码
        for extra_field in [
            'sub_domain', 'welcome', 'category', 'unit',
            'company', 'highlight', 'effect', 'target_customer'
        ]:
            if extra_field in target:
                entry['target'][extra_field] = target[extra_field]

        match_list.append(entry)

    return {
        'config': config,
        'source': source,
        'matches': match_list,
    }


@app.route('/api/match/ability/<int:ability_id>')
def api_match_ability(ability_id):
    """
    为指定场景能力匹配 Top N 场景机会。

    请求:
        GET /api/match/ability/1

    流程:
        1. 在 ALL_ABILITIES 中按 ID 查找能力
        2. 调用 match_ability_to_opportunities 执行匹配计算
        3. 通过 _build_match_response 构建统一响应

    参数:
        ability_id (int): URL 路径参数，能力 ID

    返回:
        404: 能力不存在
        200: {"config": {...}, "source": {...}, "matches": [...]}
    """
    # 线性查找目标能力（数据量不大，性能足够）
    ability = None
    for a in ALL_ABILITIES:
        if a['id'] == ability_id:
            ability = a
            break

    if ability is None:
        return jsonify({'error': f'能力 ID={ability_id} 不存在'}), 404

    # 执行匹配：将当前能力与全部机会进行多维度打分排序
    matches = match_ability_to_opportunities(ability, ALL_OPPORTUNITIES)

    # 构建源实体摘要（前端在结果头部展示此信息的卡片）
    source = {
        'id': ability['id'],
        'name': ability['name'],
        'company': ability['company'],
        'domain': ability['domain'],
        'district': ability['district'],
        'overview': ability['overview'],
        'target_customer': ability['target_customer'],
    }

    return jsonify(_build_match_response(matches, get_config(), source))


@app.route('/api/match/opportunity/<int:opp_id>')
def api_match_opportunity(opp_id):
    """
    为指定场景机会匹配 Top N 场景能力。

    与 api_match_ability 对称，区别在于：
      - 数据源：在 ALL_OPPORTUNITIES 中查找机会
      - 匹配方向：将机会与全部能力进行匹配
      - source 字段不同（机会侧有自己的字段名）

    参数:
        opp_id (int): URL 路径参数，机会 ID

    返回:
        404: 机会不存在
        200: {"config": {...}, "source": {...}, "matches": [...]}
    """
    # 线性查找目标机会
    opp = None
    for o in ALL_OPPORTUNITIES:
        if o['id'] == opp_id:
            opp = o
            break

    if opp is None:
        return jsonify({'error': f'机会 ID={opp_id} 不存在'}), 404

    # 执行匹配：将当前机会与全部能力进行多维度打分排序
    matches = match_opportunity_to_abilities(opp, ALL_ABILITIES)

    # 构建源实体摘要（机会侧字段名和能力侧不同）
    source = {
        'id': opp['id'],
        'name': opp['name'],
        'domain': opp['domain'],
        'area': opp['area'],
        'overview': opp['overview'],
        'welcome': opp['welcome'],
    }

    return jsonify(_build_match_response(matches, get_config(), source))


# ---------------------------------------------------------------------------
# 维度 API (v3 新增)
# ---------------------------------------------------------------------------
# 维度 API 提供运行时的维度元信息查询和增删功能。
# 前端通过 /api/dimensions 获取维度列表和参数，通过 POST/DELETE 管理维度。

@app.route('/api/dimensions')
def api_dimensions():
    """
    返回维度注册表元信息 + 当前配置值。

    返回格式:
        {
          "dimensions": [...],    // 所有已注册维度的定义（id, label, method, params 等）
          "config": {...},        // 当前配置（权重、top_n 等）
          "method_registry": {...} // 可用匹配方法注册表
        }

    由 get_config_with_dimensions() 统一组装，该函数从 DIMENSIONS 列表和
    当前 config 中提取数据，保证两边的信息一致。
    """
    return jsonify(get_config_with_dimensions())


# ---------------------------------------------------------------------------
# 字段列表 API（前端添加维度时使用）
# ---------------------------------------------------------------------------

@app.route('/api/fields')
def api_fields():
    """
    返回能力侧和机会侧可用于匹配的字段列表。

    前端在创建新维度时，需要选择"在哪个字段上进行匹配"。
    这个接口告诉前端两方各自有哪些字段可用。

    返回:
        {
          "ability": ["domain", "district", "overview", "highlight", "effect", "target_customer"],
          "opportunity": ["domain", "sub_domain", "area", "overview", "welcome", "category", "unit", "investment"]
        }

    注意:
        此列表为硬编码，和 data_loader.py 中定义的字段一一对应。
        如果数据源新增了字段，需要同步更新这里的配置。
    """
    return jsonify({
        'ability': ['domain', 'district', 'overview', 'highlight', 'effect', 'target_customer'],
        'opportunity': ['domain', 'sub_domain', 'area', 'overview', 'welcome', 'category', 'unit', 'investment'],
    })


# ---------------------------------------------------------------------------
# 匹配方法 API（前端添加维度时使用）
# ---------------------------------------------------------------------------

@app.route('/api/dimensions/methods')
def api_dimension_methods():
    """
    返回可用匹配方法及其默认参数。

    每种匹配方法（如 domain_match, text_semantic, vector_semantic 等）
    都有默认的 detail_type、参数、图标和颜色配置。

    前端在添加维度时需要选择匹配方法，此接口提供所有可选方法和默认值，
    以便前端渲染方法选择器并预填默认参数。

    返回格式:
        {
          "domain_match": {
            "default_detail_type": "match",
            "default_params": {},
            "default_icon": "building",
            "default_color": "#4A90D9"
          },
          ...
        }
    """
    result = {}
    # METHOD_REGISTRY 是 matcher.dimensions 中定义的方法注册表
    # 记录了每种匹配方法的名称、默认参数模板、图标和颜色
    for name, reg in METHOD_REGISTRY.items():
        result[name] = {
            'default_detail_type': reg['default_detail_type'],
            'default_params': reg['default_params'],
            'default_icon': reg['default_icon'],
            'default_color': reg['default_color'],
        }
    return jsonify(result)


# ---------------------------------------------------------------------------
# 维度增删 API
# ---------------------------------------------------------------------------

@app.route('/api/dimensions', methods=['POST', 'OPTIONS'])
def api_add_dimension():
    """
    添加新匹配维度（默认权重 0）。

    新维度创建后权重为 0，不会影响已有匹配结果，
    用户需要在配置面板中手动调整权重才能生效。

    流程:
        1. 校验请求体（必须有 label 和 method）
        2. 调用 add_dimension(body) 创建维度定义
        3. 调用 sync_config_with_dimensions() 将新维度的权重 key 同步到 config
        4. 返回新维度的完整信息

    请求体示例:
        {
          "label": "语义相似度",
          "method": "text_semantic",
          "source_field": "overview",
          "target_field": "overview",
          "params": {"threshold": 0.5}
        }

    返回:
        400: 缺少必需字段或添加失败
        200: {"success": true, "message": "...", "dimension": {...}}
    """
    if request.method == 'OPTIONS':
        return '', 204
    try:
        body = request.get_json(force=True)
        if body is None or not isinstance(body, dict):
            return jsonify({'error': '请求体必须是 JSON 对象'}), 400

        # label 和 method 是创建维度的两个必需字段
        if 'label' not in body:
            return jsonify({'error': '缺少必需字段：label'}), 400
        if 'method' not in body:
            return jsonify({'error': '缺少必需字段：method'}), 400

        # add_dimension 负责：校验方法名、自动分配 dim_id、写入 dimensions.json
        success, msg, dim = add_dimension(body)
        if not success:
            return jsonify({'error': msg}), 400

        # 同步：确保新维度的权重 key 出现在 config 中
        # 例如新增域名为 "my_custom_dim" 的维度后，config 中自动出现 my_custom_dim_weight: 0
        sync_config_with_dimensions()
        return jsonify({'success': True, 'message': msg, 'dimension': dim})

    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/dimensions/<dim_id>', methods=['DELETE', 'OPTIONS'])
def api_delete_dimension(dim_id):
    """
    删除指定匹配维度。

    删除限制：
      - 至少保留 1 个维度，保证匹配系统正常工作
      - 删除后自动同步 config，移除该维度的权重 key

    参数:
        dim_id (str): URL 路径参数，要删除的维度 ID

    返回:
        400: 删除失败（如只剩 1 个维度）
        200: {"success": true, "message": "..."}
    """
    if request.method == 'OPTIONS':
        return '', 204
    try:
        # delete_dimension 负责：校验数量限制、从 DIMENSIONS 列表移除、写入文件
        success, msg = delete_dimension(dim_id)
        if not success:
            return jsonify({'error': msg}), 400

        # 同步 config：移除已删除维度的权重 key
        sync_config_with_dimensions()
        return jsonify({'success': True, 'message': msg})

    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ---------------------------------------------------------------------------
# 参数配置 API (v3：维度感知)
# ---------------------------------------------------------------------------

@app.route('/api/config', methods=['GET', 'POST', 'OPTIONS'])
def api_config():
    """
    匹配参数配置的查询和更新接口。

    GET:
      返回当前完整配置，包括：
        - 每个维度的权重（如 domain_weight: 0.5）
        - top_n（返回匹配结果数量）
        - 各维度的私有参数（如 text_max_length: 500）

    POST:
      更新匹配参数。经过 4 步校验流程：
        1) 类型和范围校验：权重必须是 0~1 的 float，top_n 必须是 >=1 的 int
        2) 权重 key 校验：只允许更新 DIMENSIONS 中已注册的维度权重
        3) 维度私有参数校验：从 DIMENSIONS 注册表读取每个 param 的 type/min/max
        4) 权重自动缩放：如果更新的权重和 ≠ 1.0，则等比例缩放到和为 1

      POST body 示例：
        {"domain_weight": 0.7, "text_weight": 0.3, "top_n": 5}

      权重缩放示例：
        设当前有权重 domain_weight, text_weight, region_weight
        用户传 domain_weight=0.8, text_weight=0.8 (sum=1.6)
        → 等比例缩放：domain_weight=0.5, text_weight=0.5, region_weight=0
    """
    if request.method == 'OPTIONS':
        return '', 204

    if request.method == 'POST':
        try:
            body = request.get_json(force=True)
            if body is None:
                return jsonify({'error': '请求体为空，请提供 JSON'}), 400

            # 从维度注册表获取当前有效的所有权重 key
            # 例如：['domain_weight', 'text_weight', 'region_weight']
            # 这些 key 由 DIMENSIONS 列表自动生成，格式为 {dim_id}_weight
            valid_weight_keys = set(get_weight_keys())

            # ---- 第 1 步：权重 key 类型 & 范围校验 ----
            # 每个权重值必须是 0~1 之间的数值
            for key in valid_weight_keys:
                if key in body and not isinstance(body[key], (int, float)):
                    return jsonify({'error': f'{key} 必须是数值'}), 400
                if key in body and not (0 <= body[key] <= 1):
                    return jsonify({'error': f'{key} 必须在 0~1 之间'}), 400

            # ---- 第 2 步：top_n 校验 ----
            # top_n 决定返回的匹配结果数量，最小为 1
            if 'top_n' in body:
                if not isinstance(body['top_n'], int):
                    return jsonify({'error': 'top_n 必须是整数'}), 400
                if body['top_n'] < 1:
                    return jsonify({'error': 'top_n 必须 >= 1'}), 400

            # ---- 第 3 步：维度私有参数校验（遍历 DIMENSIONS 注册表） ----
            # 每个维度可以自定义参数（如 text_max_length, semantic_threshold 等），
            # 这些参数出现在 config 中时会加上 dim_id 前缀
            # 例如维度 text 的 max_length 参数 → config key 为 text_max_length
            from matcher.dimensions import DIMENSIONS
            for dim in DIMENSIONS:
                for pk, pv in dim.get('params', {}).items():
                    config_key = f"{dim['id']}_{pk}"  # 如 "text_max_length"
                    if config_key in body:
                        # 类型检查
                        if pv['type'] == 'int' and not isinstance(body[config_key], int):
                            return jsonify({'error': f'{config_key} 必须是整数'}), 400
                        # 范围检查（如果定义了 min/max）
                        if 'min' in pv and body[config_key] < pv['min']:
                            return jsonify({'error': f'{config_key} 必须 >= {pv["min"]}'}), 400
                        if 'max' in pv and body[config_key] > pv['max']:
                            return jsonify({'error': f'{config_key} 必须 <= {pv["max"]}'}), 400

            # ---- 第 4 步：权重自动缩放（如果用户修改了任意权重） ----
            # 所有权重之和应等于 1.0，如果不是则等比例缩放。
            # 这样可以保证用户随意拖滑块后，系统自动归一化。
            weight_updated = any(k in body for k in valid_weight_keys)

            if weight_updated:
                # 收集所有权重值：body 中有的用 body 中的，没有的用当前配置中的
                current_cfg = get_config()
                weights = []
                for k in valid_weight_keys:
                    val = float(body[k]) if k in body else current_cfg.get(k, 0.0)
                    weights.append(val)
                s = sum(weights)
                # 如果和不是 1.0 且不是全零，等比例缩放
                # 容差 0.001 避免浮点精度导致的误缩放
                if s > 0.001 and abs(s - 1.0) > 0.001:
                    factor = 1.0 / s
                    for k in valid_weight_keys:
                        if k in body or k in current_cfg:
                            body[k] = round((float(body.get(k, current_cfg.get(k, 0.0)))) * factor, 4)
                    print(f'[config] 权重已自动缩放至和为1：{ {k: body[k] for k in valid_weight_keys if k in body} }')

            # 持久化更新并返回新配置
            new_config = update_config(body)
            print(f'[config] 参数已更新: {new_config}')
            return jsonify(new_config)

        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # GET 请求：直接返回当前完整配置
    return jsonify(get_config())


# ============================================================================
# LLM 匹配解释 API (SSE 流式 + 缓存)
# ============================================================================
# 当用户点击某个匹配对时，前端调用此接口获取 LLM 生成的解释文本。
# 使用 SSE (Server-Sent Events) 实现流式返回，让用户看到逐字生成的体验。
# 同时支持缓存：相同的能力-机会组合只会调用一次 LLM，后续返回缓存。

@app.route('/api/match/explain', methods=['POST', 'OPTIONS'])
def api_match_explain():
    """
    为指定的能力-机会匹配对调用 LLM 生成解释（SSE 流式输出）。

    使用 Server-Sent Events (SSE) 协议逐块返回 LLM 生成的文本，
    前端通过 EventSource 或 fetch + ReadableStream 接收流式数据。

    缓存机制:
      - 首次请求 → 真实 LLM 调用，结果写入内存缓存
      - 后续相同请求 → 直接返回缓存文本（同样以流式模拟输出，保持体验一致）
      - force_refresh=true → 清除缓存后重新生成

    请求体:
      {
        "ability_id":   int,       // 能力 ID（必填）
        "opp_id":       int,       // 机会 ID（必填）
        "match_index":  int,       // 匹配结果在列表中的位置（0-based）
        "mode":         string,    // "ability" 或 "opportunity"（决定匹配方向）
        "force_refresh": bool      // 是否强制重新生成（清除缓存）
      }

    SSE 事件流格式:
      data: {"chunk": "部分文本..."}     // 流式文本块
      data: {"done": true, "cached": false} // 完成标记和缓存状态

    异常处理:
      - 能力或机会不存在 → 404
      - LLM 调用失败 → SSE 流中返回 {"error": "..."}
      - 未找到匹配得分 → 404
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        body = request.get_json(force=True)
        if not body or not isinstance(body, dict):
            return jsonify({'error': '请求体必须是 JSON 对象'}), 400

        # ---- 提取请求参数 ----
        ability_id = body.get('ability_id')
        opp_id = body.get('opp_id')
        match_index = body.get('match_index', 0)
        mode = body.get('mode', 'ability')
        force_refresh = body.get('force_refresh', False)

        if ability_id is None or opp_id is None:
            return jsonify({'error': '缺少必需字段：ability_id 和 opp_id'}), 400

        # ---- 1) 查找能力数据 ----
        ability_data = None
        for a in ALL_ABILITIES:
            if a['id'] == ability_id:
                ability_data = a
                break
        if ability_data is None:
            return jsonify({'error': f'能力 ID={ability_id} 不存在'}), 404

        # ---- 2) 查找机会数据 ----
        opp_data = None
        for o in ALL_OPPORTUNITIES:
            if o['id'] == opp_id:
                opp_data = o
                break
        if opp_data is None:
            return jsonify({'error': f'机会 ID={opp_id} 不存在'}), 404

        # ---- 3) 获取维度信息和匹配得分 ----
        # 需要先执行匹配以获取每个维度的得分，LLM 需要这些得分作为上下文
        dims = get_dimensions()

        # 根据 mode 决定匹配方向
        if mode == 'ability':
            matches = match_ability_to_opportunities(ability_data, ALL_OPPORTUNITIES)
        else:
            matches = match_opportunity_to_abilities(opp_data, ALL_ABILITIES)

        # 从匹配结果中找到目标条目的维度得分
        target_id = opp_id if mode == 'ability' else ability_id
        scores_by_dim = {}
        for m in matches:
            if m['target']['id'] == target_id:
                scores_by_dim = m.get('dimension_scores', {})
                break

        if not scores_by_dim:
            return jsonify({'error': '未找到匹配得分数据'}), 404

        # ---- 4) 处理强制刷新 ----
        # 用户在 UI 中点击"重新生成"时传入 force_refresh=true，
        # 此时清除该匹配对的缓存，强制 LLM 重新生成
        from matcher.llm_explainer import clear_cache, get_cached_explanation, generate_explanation_stream

        if force_refresh:
            clear_cache(ability_id=ability_id, opp_id=opp_id)

        # ---- 5) 生成 SSE 流 ----
        # 使用内嵌生成器函数 yield 返回值，Flask 的 Response + stream_with_context
        # 会自动将其序列化为 SSE 格式发送。
        def generate():
            import time as time_module
            import traceback

            # 强制先发一个心跳注释行，确保 SSE 连接建立
            # SSE 协议中以冒号开头的行为注释，客户端会忽略但能刷新缓冲区
            yield ':\n\n'

            try:
                # ---- 缓存检查 ----
                # 缓存 key 由 (ability_id, opp_id, dims) 三要素组成，
                # 当维度配置变化时缓存自动失效（因为 key 不同了）
                cached_text = get_cached_explanation(ability_id, opp_id, dims)
                if cached_text:
                    print(f'[llm] 命中缓存 (ability={ability_id}, opp={opp_id})')
                    # 命中缓存 → 模拟流式逐字返回，保持和真实 LLM 一致的视觉体验
                    # 每次发送 5 个字符，间隔 15ms
                    for i in range(0, len(cached_text), 5):
                        chunk = cached_text[i:i+5]
                        yield f'data: {json.dumps({"chunk": chunk}, ensure_ascii=False)}\n\n'
                        time_module.sleep(0.015)
                    yield f'data: {json.dumps({"done": True, "cached": True}, ensure_ascii=False)}\n\n'
                    return

                # ---- 真实 LLM 调用 ----
                # 未命中缓存 → 调用 LLM API，边接收边推送 SSE
                print(f'[llm] 开始调用 LLM (ability={ability_id}, opp={opp_id}, model={LLM_CONFIG.get("model")}, proxy={LLM_CONFIG.get("proxy")})')
                full_text = ''
                for chunk in generate_explanation_stream(
                    ability_data, opp_data, dims, scores_by_dim, LLM_CONFIG
                ):
                    full_text += chunk
                    yield f'data: {json.dumps({"chunk": chunk}, ensure_ascii=False)}\n\n'

                print(f'[llm] LLM 返回完成, 共 {len(full_text)} 字符')

                # ---- 存入缓存 ----
                # 将完整的 LLM 回复文本存入内存缓存，下次相同请求直接命中
                from matcher.llm_explainer import _explain_cache, _make_cache_key
                key = _make_cache_key(ability_id, opp_id, dims)
                _explain_cache[key] = (full_text, time_module.time())

                yield f'data: {json.dumps({"done": True, "cached": False}, ensure_ascii=False)}\n\n'

            except Exception as e:
                # LLM 调用异常不影响 SSE 连接——通过 error 事件通知前端
                print(f'[llm] generate() 异常: {e}')
                traceback.print_exc()
                yield f'data: {json.dumps({"error": str(e)[:300]}, ensure_ascii=False)}\n\n'

        # ---- 构造 SSE Response ----
        # text/event-stream 是 SSE 标准 MIME 类型
        resp = Response(generate(), content_type='text/event-stream')
        resp.charset = 'utf-8'
        # Werkzeug 的 charset 属性不会自动更新 Content-Type header，
        # 必须手动写入完整 header 才能让浏览器用 UTF-8 解码中文。
        resp.headers['Content-Type'] = 'text/event-stream; charset=utf-8'
        resp.headers['Cache-Control'] = 'no-cache'            # 禁止浏览器缓存 SSE
        resp.headers['Connection'] = 'keep-alive'              # 保持长连接
        resp.headers['X-Accel-Buffering'] = 'no'              # 禁止 nginx 缓冲
        return resp

    except Exception as e:
        # 外层异常（解析请求、查找数据等阶段）
        # 同样通过 SSE 流返回错误，保持响应格式一致
        print(f'[llm] 解释生成异常: {e}')
        # 将异常消息捕获到局部变量，避免闭包中 e 被 Python 垃圾回收
        err_msg = str(e)[:300]
        def error_stream():
            yield f'data: {json.dumps({"error": err_msg}, ensure_ascii=False)}\n\n'
        resp = Response(error_stream(), content_type='text/event-stream')
        resp.charset = 'utf-8'
        resp.headers['Content-Type'] = 'text/event-stream; charset=utf-8'
        resp.headers['Cache-Control'] = 'no-cache'
        resp.headers['Connection'] = 'keep-alive'
        resp.headers['X-Accel-Buffering'] = 'no'
        return resp


# ============================================================================
# 程序入口
# ============================================================================
if __name__ == '__main__':
    # 当 python app.py 直接运行时，启动 Flask 开发服务器
    # 生产环境应使用 gunicorn 或 waitress 等 WSGI 服务器
    print()
    print('=' * 60)
    print('  场景机会与能力匹配 Demo — 后端服务 v3')
    print(f'  访问地址: http://127.0.0.1:5000')
    print('  API 文档: http://127.0.0.1:5000/api/config')
    print('=' * 60)
    # debug=True 开启热重载和详细错误页面
    # use_reloader=False 避免重复加载数据和预热缓存（Flask 重载器会启动两次进程）
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)
