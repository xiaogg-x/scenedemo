# -*- coding: utf-8 -*-
"""
engine.py —— 场景匹配引擎模块 (v3：维度注册表驱动架构)

══════════════════════════════════════════════════════════════════════════════
模块概述
══════════════════════════════════════════════════════════════════════════════

本模块是场景匹配系统的「评分计算核心」，负责将场景能力（Ability）与
场景机会（Opportunity）进行双向匹配，输出加权综合得分和排序结果。

══════════════════════════════════════════════════════════════════════════════
架构设计：维度注册表驱动（v3）
══════════════════════════════════════════════════════════════════════════════

v1/v2 版本的硬编码缺陷：
  旧版本中，匹配逻辑对 domain/text/region 三个维度做了硬编码——
  引擎内部直接调用 _score_string_match()、_score_text() 等具体函数，
  导致新增或删除维度时必须修改引擎源码。

v3 的可插拔改进：
  引擎不再知道任何具体的维度名称或匹配算法，它只做三件事：
    1. 遍历 DIMENSIONS 注册表（来自 dimensions.py）
    2. 按每个维度的字段配置提取数据、读取参数、调用 compute 闭包
    3. 对各维度得分做加权求和得到总分

  新增维度 → 只需在 dimensions.py 中注册 → 引擎自动适配，零代码修改。

══════════════════════════════════════════════════════════════════════════════
核心算法：多维度加权求和模型
══════════════════════════════════════════════════════════════════════════════

                    ┌─────────────────────────────┐
                    │     总分 Total Score        │
                    │                             │
                    │  Σ (dimension_score × weight)│
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │  领域匹配    │ │  文本匹配    │ │  区域匹配    │ ... (可扩展)
      │ score=0.8    │ │ score=0.5    │ │ score=1.0    │
      │ weight=0.4   │ │ weight=0.3   │ │ weight=0.3   │
      │ contrib=0.32 │ │ contrib=0.15 │ │ contrib=0.30 │
      └──────────────┘ └──────────────┘ └──────────────┘

  其中每个 dimension_score 由对应方法的 compute 闭包独立计算：
    - string_match:  0.0 | 0.5 | 1.0 （离散三级）
    - bigram:        [0.0, 1.0] 连续值（Jaccard 相似度）
    - vector_semantic: [0.0, 1.0] 连续值（余弦相似度）

  总分理论范围 [0.0, N]（N = 所有权重之和），通常归一化到 [0, 1] 来理解。

══════════════════════════════════════════════════════════════════════════════
API 接口总览
══════════════════════════════════════════════════════════════════════════════

  匹配入口：
    match_ability_to_opportunities(ability, opportunities)  → list[dict]  Top N 机会
    match_opportunity_to_abilities(opp, abilities)          → list[dict]  Top N 能力

  配置管理：
    get_config()                  → dict           获取当前参数
    update_config(new_config)     → dict           更新参数
    get_config_with_dimensions()  → dict           获取参数+维度元信息
    sync_config_with_dimensions() → None            维度变更后同步配置
"""

import json
import os
from .dimensions import DIMENSIONS, get_dimensions, get_weight_keys


# ============================================================================
# 匹配参数配置（集中管理，供前端 /api/config 读写）
# ============================================================================
#
# MATCH_CONFIG 是一个全局字典，存储所有影响匹配行为的运行参数：
#
#   结构示例：
#   {
#       "top_n": 3,                    // 返回前几条匹配结果（全局参数）
#       "domain_weight": 0.4,         // 领域维度权重
#       "text_weight": 0.3,           // 文本维度权重
#       "region_weight": 0.3,         // 区域维度权重
#       "text_max_length": 300,       // 文本维度的私有参数（bigram 截取长度）
#       "dim_1_model_name": "BAAI/...", // 自定义向量维度的私有参数
#       "dim_1_threshold": 0.3,
#   }
#
# 命名规则：
#   - 权重 key: "{dim_id}_weight"（由 dimensions.py 的 weight_key 字段决定）
#   - 私有参数 key: "{dim_id}_{param_name}"（由 dim_def.params 决定）

def _build_default_config():
    """
    从当前维度注册表自动构建默认配置字典。

    遍历 DIMENSIONS 列表，为每个维度生成：
      1. 权重键（key = weight_key, value = default_weight）
      2. 私有参数键（key = {dim_id}_{param_name}, value = param['default']）

    这个函数确保新增维度后，config 中自动出现对应的权重和参数项，
    不需要手动编辑 config.json。

    返回:
        dict: 默认配置字典，包含 top_n + 所有维度的权重和私有参数
    """
    config = {'top_n': 3}  # 全局参数：返回 Top N 条结果
    for dim in DIMENSIONS:
        # 每个维度的权重项
        config[dim['weight_key']] = dim['default_weight']
        # 每个维度的方法私有参数（如 bigram 的 max_length，vector_semantic 的 model_name 等）
        for pk, pv in dim.get('params', {}).items():
            config[f"{dim['id']}_{pk}"] = pv['default']
    return config


# 模块级初始化：根据当前 DIMENSIONS 构建初始配置
MATCH_CONFIG = _build_default_config()


def sync_config_with_dimensions():
    """
    根据当前 DIMENSIONS 列表重新同步 MATCH_CONFIG。

    ══════════════════════════════════════════════════════════════════════
    触发时机与用途
    ══════════════════════════════════════════════════════════════════════

    当用户通过 API 添加/删除维度后，DIMENSIONS 列表会变化，
    但 MATCH_CONFIG 可能仍保留旧维度的配置项或缺少新维度的配置项。
    本函数负责让两者保持一致。

    ══════════════════════════════════════════════════════════════════════
    同步策略（增量合并）
    ══════════════════════════════════════════════════════════════════════

      - 新增的维度：添加默认权重（0.0）和默认私有参数
        （新维度默认不影响现有总分分布）
      - 被删除的维度：其对应的权重 key 和参数 key 自动消失
        （因为新 config 只遍历当前的 DIMENSIONS）
      - 仍在的维度：保留用户已调整过的值（不覆盖！）
        （通过 MATCH_CONFIG.get(wk, dim['default_weight']) 实现"有则保留，无则默认"）
      - top_n 参数始终保留原值

    同步完成后自动持久化到 config.json。
    """
    global MATCH_CONFIG
    # 以现有 top_n 为基础构建新配置（top_n 不受维度增删影响）
    new_config = {'top_n': MATCH_CONFIG.get('top_n', 3)}

    for dim in DIMENSIONS:
        wk = dim['weight_key']
        # 优先使用已有值（用户可能已经调整过），没有则取维度的默认权重
        new_config[wk] = MATCH_CONFIG.get(wk, dim['default_weight'])
        # 同理处理该维度的所有私有参数
        for pk, pv in dim.get('params', {}).items():
            ck = f"{dim['id']}_{pk}"
            new_config[ck] = MATCH_CONFIG.get(ck, pv['default'])

    # 原子替换整个 config（保证一致性）
    MATCH_CONFIG = new_config
    save_config_to_file()
    print(f'[config] 已与维度列表同步：{list(MATCH_CONFIG.keys())}')


# 配置文件路径（与 Excel 数据文件同目录下的"后台数据"文件夹）
CONFIG_FILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '后台数据', 'config.json'
))


def _valid_weight_keys():
    """
    返回当前合法的所有权重 key 的集合。

    包含两部分来源：
      1. 当前 DIMENSIONS 注册表中所有维度的 weight_key（动态部分）
      2. 历史兼容 key（domain_weight, text_weight, region_weight）（静态兜底）

    历史兼容的意义：
      如果用户手动编辑 config.json 后又删掉了某个维度，
      config 文件中可能残留该维度的权重 key。
      兼容列表确保这些残留 key 不会被视为非法而被忽略。

    返回:
        set[str]: 合法权重 key 的集合
    """
    known = set(get_weight_keys())
    # 兼容历史配置文件中可能存在的 key（即使对应的维度已被删除）
    known.update(['domain_weight', 'text_weight', 'region_weight'])
    return known


def _is_weight_key(key):
    """判断一个 key 是否是合法的权重配置键。"""
    return key in _valid_weight_keys()


def save_config_to_file():
    """
    将当前 MATCH_CONFIG 持久化写入 config.json。

    写入格式：UTF-8 编码、中文不转义（ensure_ascii=False）、2 空格缩进。
    异常保护：IO 失败时仅打印日志，不抛出异常。
    """
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(MATCH_CONFIG, f, ensure_ascii=False, indent=2)
        print(f'[config] 配置已保存至 {CONFIG_FILE}')
    except Exception as e:
        print(f'[config] 保存配置失败: {e}')


def load_config_from_file():
    """
    从 config.json 恢复配置（文件不存在时不做任何事）。

    采用「选择性合并」策略：只更新 MATCH_CONFIG 中已有的 key，
    不引入 config.json 中多余的未知 key。
    这保证了即使 config.json 被手动篡改加入了脏数据，也不会污染运行配置。
    """
    if not os.path.exists(CONFIG_FILE):
        print('[config] 未找到持久化配置文件，使用默认值')
        return
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 只更新已知的 key，忽略未知 key（防止脏数据污染）
            for key in MATCH_CONFIG:
                if key in data:
                    MATCH_CONFIG[key] = data[key]
        print(f'[config] 已从 {CONFIG_FILE} 加载配置: {MATCH_CONFIG}')
    except Exception as e:
        print(f'[config] 加载配置失败: {e}')


def get_config():
    """
    返回当前匹配参数配置的浅拷贝。

    返回副本而非原始引用，防止外部代码意外修改全局配置。
    API 层（/api/config GET）调用此函数获取前端展示用的配置数据。

    返回:
        dict: MATCH_CONFIG 的完整副本
    """
    return dict(MATCH_CONFIG)


def get_config_with_dimensions():
    """
    返回「当前配置 + 维度元信息」的组合结构。

    这是前端 /api/dimensions 接口的核心数据源。前端需要同时知道：
      1. 有哪些维度（id、label、icon、color 等 UI 信息）
      2. 每个维度当前的权重是多少（从 config 中读）
      3. 每个维度的私有参数当前值是什么
      4. 完整的原始 config 字典（用于保存回传）

    返回:
        dict: {
            'dimensions': [  // 维度元信息列表
                {
                    'id': 'domain',
                    'label': '领域匹配',
                    'weight_key': 'domain_weight',
                    'weight': 0.4,              ← 当前实际权重（来自 config）
                    'score_label': '领域',
                    'icon': '🔍',
                    'color': '#3B82F6',
                    'detail_type': 'text',
                    'focus_description': '...',
                    'params': {                     // 私有参数及其当前值
                        'max_length': {
                            ...param 定义...,
                            'config_key': 'text_max_length',  ← 对应 config 中的 key
                            'value': 300                   ← 当前值
                        }
                    }
                },
                ...
            ],
            'config': {...}  // 完整的原始配置字典
        }
    """
    dims_info = []
    for dim in DIMENSIONS:
        info = {
            'id': dim['id'],
            'label': dim['label'],
            'weight_key': dim['weight_key'],
            # 权重值：优先从 config 取（用户可能已调整），否则用维度默认值
            'weight': MATCH_CONFIG.get(dim['weight_key'], dim['default_weight']),
            'score_label': dim.get('score_label', dim['label']),
            'icon': dim.get('icon', ''),
            'color': dim.get('color', '#94A3B8'),  # 默认灰色（Tailwind slate-400）
            'detail_type': dim.get('detail_type', 'text'),
            'focus_description': dim.get('focus_description', ''),
        }
        # 如果该维度有私有参数，附加参数定义和当前值
        if 'params' in dim:
            info['params'] = {
                pk: {
                    **pv,  # 展开原始参数定义（default, label, hint, type, min, max...）
                    'config_key': f"{dim['id']}_{pk}",  # 告诉前端这个参数在 config 中的 key 名
                    'value': MATCH_CONFIG.get(f"{dim['id']}_{pk}", pv['default']),  # 当前实际值
                }
                for pk, pv in dim['params'].items()
            }
        dims_info.append(info)
    return {
        'dimensions': dims_info,
        'config': dict(MATCH_CONFIG),  # 完整配置快照
    }


def update_config(new_config):
    """
    更新匹配参数配置（选择性更新模式）。

    只会更新传入字典中的键，未传入的键保持原有值不变。
    更新完成后自动调用 save_config_to_file() 持久化到 config.json。

    参数:
        new_config (dict): 需要更新的参数键值对
                           例如 {"domain_weight": 0.5, "top_n": 5, "text_max_length": 500}

    返回:
        dict: 更新后的完整配置副本

    安全机制：
      - 只接受已知 key（权重 key + 维度私有参数 key），未知 key 静默忽略
      - 通过 updatable_keys 集合白名单控制可更新的范围
    """
    # 构建白名单：当前 config 中已有的 key + 所有维度的权重 key + 所有维度的私有参数 key
    updatable_keys = set(MATCH_CONFIG.keys()) | set(get_weight_keys())
    # 动态添加各维度的私有参数 key 到白名单
    for dim in DIMENSIONS:
        for pk in dim.get('params', {}):
            updatable_keys.add(f"{dim['id']}_{pk}")

    # 选择性更新：只在白名单内的 key 才会被写入
    for key, value in new_config.items():
        if key in updatable_keys:
            MATCH_CONFIG[key] = value

    save_config_to_file()
    return dict(MATCH_CONFIG)


# ============================================================================
# 匹配入口函数 (v3：维度注册表驱动)
# ============================================================================

def _compute_dimension_scores(ability, opp):
    """
    **匹配引擎的核心计算循环** —— 遍历维度注册表，计算所有维度的得分并加权求和。

    ══════════════════════════════════════════════════════════════════════
    设计理念：完全数据驱动，零硬编码
    ══════════════════════════════════════════════════════════════════════

    本函数不知道也不关心有多少个维度、它们叫什么名字、用什么算法。
    它只是机械地执行一个 4 步循环，对 DIMENSIONS 中的每一个条目：

      Step 1 — 取字段值
        根据 dim['ability_fields'] 和 dim['opportunity_fields'] 从数据行中提取字段值。
        例如领域匹配维度配置了 ability_fields=['domain']，就从 ability 字典中取 ability['domain']。
        多字段时返回列表，如 ['概述文本', '客户描述文本']。

      Step 2 — 取私有参数
        从全局 MATCH_CONFIG 中读取该维度的方法参数。
        例如 bigram 方法需要 max_length 参数，就在 config 中找 '{dim_id}_max_length' 键。

      Step 3 — 调评分函数
        调用 dim['compute'] 闭包（由 dimensions.py 的 METHOD_REGISTRY 工厂创建），
        传入字段值和参数，得到 (score, detail) 元组。

      Step 4 — 取权重并累加
        从 MATCH_CONFIG 中读取该维度的当前权重，
        将 score × weight 累加到 total 总分上。

    ══════════════════════════════════════════════════════════════════════
    参数
    ══════════════════════════════════════════════════════════════════════

      ability (dict): 一条场景能力的数据行（来自 Excel 的能力表）
                      通常包含 name, domain, district, overview, target_customer 等字段
      opp     (dict): 一条场景机会的数据行（来自 Excel 的机会表）
                      通常包含 name, domain, area, overview, welcome 等字段

    ══════════════════════════════════════════════════════════════════════
    返回
    ══════════════════════════════════════════════════════════════════════

      tuple[dict, float]:
        - scores_by_dim (dict): 各维度的详细得分
            格式：{dim_id: {'score': float, 'detail': str|dict, 'weight': float}, ...}
            例：{
              'domain': {'score': 1.0, 'detail': '精确命中...', 'weight': 0.4},
              'text':   {'score': 0.35, 'detail': {...}, 'weight': 0.3},
              'region': {'score': 0.0, 'detail': '未命中...', 'weight': 0.3},
            }

        - total_score (float): 加权总分 = Σ(score × weight)，四舍五入到 4 位小数
    """
    scores_by_dim = {}
    total = 0.0

    # ─── 核心循环：遍历维度注册表中的每一个维度 ───
    for dim in DIMENSIONS:
        dim_id = dim['id']

        # ── 步骤 1：按维度注册表的字段列表，从数据行中提取字段值 ──
        # 能力侧：例如领域匹配取 ['domain'] → ['人工智能（软件）']
        #          文本匹配取 ['overview','target_customer'] → ['能力概述文本', '意向客户文本']
        a_vals = [ability.get(f, '') for f in dim['ability_fields']]
        o_vals = [opp.get(f, '') for f in dim['opportunity_fields']]

        # ── 步骤 2：从 MATCH_CONFIG 中读取维度私有参数 ──
        # 例如 bigram 方法的 max_length 参数 → 在 config 中查找 'text_max_length' 键
        # 若找不到或值为 None，则回退到维度定义中的默认值
        dim_params = {}
        for pk, pv in dim.get('params', {}).items():
            config_key = f"{dim_id}_{pk}"
            # 注意 Python 的 gotcha: dict.get(key, default) 在 key 存在但值为 None 时
            # 不会使用 default（因为 None 也是"存在"的值），
            # 所以这里需要显式判断 None 后再回退到默认值
            val = MATCH_CONFIG.get(config_key)
            dim_params[pk] = val if val is not None else pv['default']

        # ── 步骤 3：调用 compute 闭包 → (score, detail) ──
        # compute 闭包由 METHOD_REGISTRY[method]['build_compute'](dim_def) 构建
        # 闭包内部已记住字段名、method_labels 等上下文信息
        # 调用方只需提供原始值和参数即可，实现了完美的关注点分离
        score, detail = dim['compute'](a_vals, o_vals, dim_params)

        # ── 步骤 4：取权重并加权累加 ──
        # 权重表示该维度在综合评分中的重要程度（0~1）
        # 从 config 中取用户调整过的值，若没有则用维度的 default_weight
        weight = MATCH_CONFIG.get(dim['weight_key'], dim['default_weight'])

        # 记录该维度的完整得分信息（用于前端逐维度展示详情）
        scores_by_dim[dim_id] = {
            'score': round(score, 4),      # 得分四舍五入到 4 位小数
            'detail': detail,               # 详情信息（字符串或字典，取决于方法类型）
            'weight': weight,               # 当前使用的权重
        }
        total += score * weight  # 核心：加权累加到总分

    return scores_by_dim, round(total, 4)


def _build_match_result(opp, ability, scores_by_dim, total_score, source_is_ability=True):
    """
    构建单条匹配结果的完整字典（v3 标准格式）。

    ══════════════════════════════════════════════════════════════════════
    输出格式设计（双版本兼容）
    ══════════════════════════════════════════════════════════════════════

    结果字典同时包含两种格式的得分数据：

      v3 结构化格式（推荐新前端使用）：
        'dimension_scores' → {dim_id: {score, detail, weight}, ...}
        层次清晰，适合动态渲染任意数量的维度。

      v2 扁平化格式（兼容老前端）：
        '{dim_id}_score'         → float    (如 domain_score = 0.8)
        '{dim_id}_match_detail'  → str/dict (如 domain_match_detail = "精确命中...")
        老前端无需改动就能继续读取各维度得分。

    ══════════════════════════════════════════════════════════════════════
    source_is_ability 参数的含义
    ══════════════════════════════════════════════════════════════════════

    匹配有两种方向：
      - True  (= 默认): 「能力 → 机会」匹配
             source（主动方）是能力，target（被动方）是机会
             source_fields 显示能力的字段，target_fields 显示机会的字段
      - False:         「机会 → 能力」匹配（反向匹配）
             source 是机会，target 是能力
             字段标签互换，方便前端统一模板渲染

    参数:
        opp              (dict): 被匹配的目标对象（机会或能力，取决于方向）
        ability          (dict): 发起匹配的源对象
        scores_by_dim    (dict): _compute_dimension_scores 的第一返回值
        total_score      (float): 加权总分
        source_is_ability (bool): 匹配方向标识

    返回:
        dict: 完整的匹配结果字典，包含 target、total_score、dimension_scores、
              v2 兼容字段、source_fields、target_fields
    """
    result = {
        'target': opp if source_is_ability else ability,  # 匹配到的目标对象
        'total_score': total_score,                       # 综合得分
        'dimension_scores': scores_by_dim,                 # 结构化维度得分
    }

    # ---- v2 兼容层：把 dimension_scores 拍平为独立的顶级字段 ----
    # 这样基于 v2 接口的老前端代码可以继续工作而无需修改
    # 例如生成：result['domain_score'] = 0.8, result['domain_match_detail'] = "精确命中…"
    for dim_id, ds in scores_by_dim.items():
        result[f'{dim_id}_score'] = ds['score']
        result[f'{dim_id}_match_detail'] = ds['detail']

    # ---- 字段对照表（中文标签 → 实际值） ----
    # 前端用此数据渲染左右对比视图（左列 = 源对象字段，右列 = 目标对象字段）
    if source_is_ability:
        # 能力→机会匹配：左侧展示能力信息，右侧展示机会信息
        result['source_fields'] = {
            '产品名称': ability.get('name', ''),
            '所属产业领域': ability.get('domain', ''),
            '所属区': ability.get('district', ''),
            '能力概述': ability.get('overview', ''),
            '意向对接客户': ability.get('target_customer', ''),
        }
        result['target_fields'] = {
            '应用场景项目名称': opp.get('name', ''),
            '应用场景所属领域': opp.get('domain', ''),
            '应用场景所属区域': opp.get('area', ''),
            '应用场景概述': opp.get('overview', ''),
            '欢迎合作方向': opp.get('welcome', ''),
        }
    else:
        # 机会→能力反向匹配：左侧展示机会信息，右侧展示能力信息
        result['source_fields'] = {
            '应用场景项目名称': opp.get('name', ''),
            '应用场景所属领域': opp.get('domain', ''),
            '应用场景所属区域': opp.get('area', ''),
            '应用场景概述': opp.get('overview', ''),
            '欢迎合作方向': opp.get('welcome', ''),
        }
        result['target_fields'] = {
            '产品名称': ability.get('name', ''),
            '所属产业领域': ability.get('domain', ''),
            '所属区': ability.get('district', ''),
            '能力概述': ability.get('overview', ''),
            '意向对接客户': ability.get('target_customer', ''),
        }

    return result


def match_ability_to_opportunities(ability, opportunities):
    """
    为一条场景能力匹配 Top N 条场景机会（正向匹配）。

    ══════════════════════════════════════════════════════════════════════
    执行流程
    ══════════════════════════════════════════════════════════════════════

      1. 遍历每一条机会
      2. 对 (ability, opportunity) 调用 _compute_dimension_scores() 计算多维得分
      3. 用 _build_match_result() 组装标准格式结果
      4. 按 total_score 降序排序
      5. 截取前 top_n 条（由 MATCH_CONFIG['top_n'] 决定）

    ══════════════════════════════════════════════════════════════════════
    结果格式
    ══════════════════════════════════════════════════════════════════════

    每条结果包含：
      - target (dict):            匹配到的场景机会完整数据
      - dimension_scores (dict):   结构化维度得分（v3 格式）
      - {dim}_score (float):      v2 兼容扁平得分字段
      - {dim}_match_detail:       v2 兼容详情字段
      - total_score (float):      综合加权得分
      - source_fields (dict):     能力侧字段对照
      - target_fields (dict):     机会侧字段对照

    参数:
        ability      (dict):  一条场景能力数据
        opportunities (list[dict]): 场景机会列表

    返回:
        list[dict]: 按 total_score 降序排列的前 top_n 条匹配结果
    """
    results = []

    for opp in opportunities:
        # 计算这对 (ability, opportunity) 在所有维度上的得分
        scores_by_dim, total_score = _compute_dimension_scores(ability, opp)
        # 组装成标准结果格式
        result = _build_match_result(opp, ability, scores_by_dim, total_score,
                                     source_is_ability=True)
        results.append(result)

    # 降序排列：得分最高的排最前面
    results.sort(key=lambda x: x['total_score'], reverse=True)
    # 截取 Top N
    return results[:MATCH_CONFIG['top_n']]


def match_opportunity_to_abilities(opp, abilities):
    """
    为一条场景机会匹配 Top N 条场景能力（反向匹配）。

    ══════════════════════════════════════════════════════════════════════
    与正向匹配的关系
    ══════════════════════════════════════════════════════════════════════

    基本逻辑与 match_ability_to_opportunities() 完全对称：
      - 同样遍历 DIMENSIONS 注册表计算多维得分
      - 同样按 total_score 降序排列截取 Top N
      - 区别仅在 source_is_ability=False（字段标签互换）

    ══════════════════════════════════════════════════════════════════════
    领域兜底匹配策略（Domain Fallback）
    ══════════════════════════════════════════════════════════════════════

    反向匹配独有的增强逻辑：当常规的 domain（领域）维度得分为 0 时，
    尝试用**另一个字段组合**进行二次匹配。

    为什么需要这个兜底？

    问题根源：「双向字段命名不对称」

    正向匹配（能力→机会）：
      能力 domain="人工智能"  →  在机会 welcome 中搜索 "人工智能"

    反向匹配（机会→能力）：
      机会 domain="人工智能"  →  在能力 domain 中搜索 "人工智能"
      但如果能力的 domain 叫"AI技术"，而"人工智能"写在了能力的 target_customer 字段里，
      常规匹配就会漏掉这组本应匹配的记录。

    兜底方案：

      当 domain 维度得分 == 0（精确子串和大类归一化都没命中）时：
      用机会的 domain 作为搜索词，去搜索能力的 target_customer（意向对接客户）字段。

      这相当于给反向匹配多了一次「交叉字段」尝试的机会。

    示例：
      能力: domain="AI平台", target_customer="寻找人工智能领域的制造企业"
      机会: domain="人工智能", welcome="寻找AI解决方案提供商"

      常规反向匹配：机会 domain("人工智能") vs 能力 domain("AI平台") → 归一化可能不一致 → 0分
      兜底匹配：      机会 domain("人工智能") vs 能力 target_customer("...人工智能...") → 命中! → 补救成功

    参数:
        opp      (dict):        一条场景机会数据
        abilities (list[dict]): 场景能力列表

    返回:
        list[dict]: 按 total_score 降序排列的前 top_n 条匹配结果（source_is_ability=False）
    """
    results = []

    for ability in abilities:
        # 先走标准的维度注册表匹配流程（与正向匹配完全一致）
        scores_by_dim, total_score = _compute_dimension_scores(ability, opp)

        # ---- 领域兜底匹配（Domain Fallback） ----
        # 触发条件：domain 维度得分恰好为 0（说明精确匹配和大类归一化都没命中）
        if 'domain' in scores_by_dim and scores_by_dim['domain']['score'] == 0:
            opp_domain = opp.get('domain', '')
            if opp_domain:
                # 导入底层评分函数（直接调用而非走 compute 闭包，以便自定义字段映射）
                from .dimensions import _score_string_match
                # 兜底匹配：反过来搜
                #   搜索词 = 机会的 domain（如"人工智能"）
                #   被搜文本 = 能力的 target_customer（如"面向人工智能制造业..."）
                fallback_score, fallback_detail = _score_string_match(
                    opp_domain,                            # 搜索词：机会的领域
                    ability.get('target_customer', ''),    # 被搜索文本：能力的意向对接客户
                    ability_label='机会所属领域',          # 自定义标签（区别于常规匹配）
                    opp_label='能力意向对接客户',
                )
                if fallback_score > 0:
                    # 兜底成功：用兜底得分替换原有 domain 得分
                    # 注意：保留原有的 weight（不改变权重分配）
                    old_weight = scores_by_dim['domain']['weight']
                    scores_by_dim['domain'] = {
                        'score': fallback_score,
                        'detail': fallback_detail,
                        'weight': old_weight,
                    }
                    # 因为 domain 分数变了，需要重新计算总分
                    total_score = sum(
                        ds['score'] * ds['weight']
                        for ds in scores_by_dim.values()
                    )
                    total_score = round(total_score, 4)

        # 组装结果（注意 source_is_ability=False 表示这是反向匹配）
        result = _build_match_result(opp, ability, scores_by_dim, total_score,
                                     source_is_ability=False)
        results.append(result)

    # 排序 + 截取 Top N
    results.sort(key=lambda x: x['total_score'], reverse=True)
    return results[:MATCH_CONFIG['top_n']]
