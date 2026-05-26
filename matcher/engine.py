# -*- coding: utf-8 -*-
"""
engine.py —— 匹配引擎模块 (v3：维度注册表驱动)

职责：
  实现场景能力与场景机会之间的双向匹配评分与排序。
  匹配维度由 matcher/dimensions.py 中的 DIMENSIONS 注册表集中定义，
  引擎只负责遍历注册表、拼字段、调评分、加权求和。

核心算法：
  total_score = Σ (dim_score × dim_weight)  对注册表中所有维度求和

API：
  match_ability_to_opportunities(ability, opportunities) → list[dict] (Top N)
  match_opportunity_to_abilities(opp, abilities)             → list[dict] (Top N)
  get_config() → dict  (返回当前匹配参数)
  update_config(new_config) → dict  (更新匹配参数)
"""

import json
import os
from .dimensions import DIMENSIONS, get_dimensions, get_weight_keys


# ============================================================================
# 匹配参数配置（集中管理，供前端 /api/config 读写）
# ============================================================================
# 权重 key 由维度注册表自动推导；top_n 是全局参数
# 维度私有参数以 "{dim_id}_{param_name}" 命名，如 "text_max_length"
# ============================================================================

def _build_default_config():
    """从维度注册表自动构建默认配置字典。"""
    config = {'top_n': 3}
    for dim in DIMENSIONS:
        config[dim['weight_key']] = dim['default_weight']
        for pk, pv in dim.get('params', {}).items():
            config[f"{dim['id']}_{pk}"] = pv['default']
    return config


MATCH_CONFIG = _build_default_config()


def sync_config_with_dimensions():
    """
    根据当前 DIMENSIONS 列表重新同步 MATCH_CONFIG。
    - 新增维度：添加默认权重（0.0）和默认参数
    - 删除维度：移除对应权重 key 和参数 key
    - 保留仍在 DIMENSIONS 中的维度的现有配置值
    调用后自动持久化。
    """
    global MATCH_CONFIG
    new_config = {'top_n': MATCH_CONFIG.get('top_n', 3)}

    for dim in DIMENSIONS:
        wk = dim['weight_key']
        # 保留现有值，或取默认值
        new_config[wk] = MATCH_CONFIG.get(wk, dim['default_weight'])
        # 维度私有参数
        for pk, pv in dim.get('params', {}).items():
            ck = f"{dim['id']}_{pk}"
            new_config[ck] = MATCH_CONFIG.get(ck, pv['default'])

    MATCH_CONFIG = new_config
    save_config_to_file()
    print(f'[config] 已与维度列表同步：{list(MATCH_CONFIG.keys())}')


# 配置文件路径（与 Excel 数据文件同目录）
CONFIG_FILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '后台数据', 'config.json'
))


def _valid_weight_keys():
    """返回当前支持的所有权重 key（含已注册维度的和已知历史 key）。"""
    known = set(get_weight_keys())
    # 兼容历史配置文件中可能存在的 key
    known.update(['domain_weight', 'text_weight', 'region_weight'])
    return known


def _is_weight_key(key):
    return key in _valid_weight_keys()


def save_config_to_file():
    """将当前 MATCH_CONFIG 持久化写入 config.json。"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(MATCH_CONFIG, f, ensure_ascii=False, indent=2)
        print(f'[config] 配置已保存至 {CONFIG_FILE}')
    except Exception as e:
        print(f'[config] 保存配置失败: {e}')


def load_config_from_file():
    """从 config.json 恢复配置（文件不存在时不做任何事）。"""
    if not os.path.exists(CONFIG_FILE):
        print('[config] 未找到持久化配置文件，使用默认值')
        return
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for key in MATCH_CONFIG:
                if key in data:
                    MATCH_CONFIG[key] = data[key]
        print(f'[config] 已从 {CONFIG_FILE} 加载配置: {MATCH_CONFIG}')
    except Exception as e:
        print(f'[config] 加载配置失败: {e}')


def get_config():
    """返回当前匹配参数配置的副本。"""
    return dict(MATCH_CONFIG)


def get_config_with_dimensions():
    """
    返回当前配置 + 维度元信息，供前端 /api/dimensions 使用。
    """
    dims_info = []
    for dim in DIMENSIONS:
        info = {
            'id': dim['id'],
            'label': dim['label'],
            'weight_key': dim['weight_key'],
            'weight': MATCH_CONFIG.get(dim['weight_key'], dim['default_weight']),
            'score_label': dim.get('score_label', dim['label']),
            'icon': dim.get('icon', ''),
            'color': dim.get('color', '#94A3B8'),
            'detail_type': dim.get('detail_type', 'text'),
        }
        if 'params' in dim:
            info['params'] = {
                pk: {
                    **pv,
                    'config_key': f"{dim['id']}_{pk}",
                    'value': MATCH_CONFIG.get(f"{dim['id']}_{pk}", pv['default']),
                }
                for pk, pv in dim['params'].items()
            }
        dims_info.append(info)
    return {
        'dimensions': dims_info,
        'config': dict(MATCH_CONFIG),
    }


def update_config(new_config):
    """
    更新匹配参数配置。只会更新传入的键，其他键保持不变。
    更新后自动持久化到 config.json。

    参数:
        new_config (dict): 需要更新的参数字典

    返回:
        dict: 更新后的完整配置
    """
    updatable_keys = set(MATCH_CONFIG.keys()) | set(get_weight_keys())
    # 维度私有参数也允许更新
    for dim in DIMENSIONS:
        for pk in dim.get('params', {}):
            updatable_keys.add(f"{dim['id']}_{pk}")

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
    遍历维度注册表，计算所有维度的得分。

    这是匹配引擎的核心循环——完全由 DIMENSIONS 注册表驱动，
    不对任何具体维度（领域/文本/区域）做硬编码。

    对每个维度的处理步骤（4 步）：
      1. 取字段值   —— 从 ability 和 opp 中按 ability_fields/opportunity_fields 提取值
      2. 取私有参数  —— 从 MATCH_CONFIG 中读取该维度的 params（如 text_max_length）
      3. 调评分函数  —— 调用 dim['compute'] 闭包（由 METHOD_REGISTRY 构建）
      4. 取权重      —— 从 MATCH_CONFIG 取当前权重，缺省用 default_weight

    参数:
        ability (dict): 场景能力数据行
        opp     (dict): 场景机会数据行

    返回:
        tuple[dict, float]:
            - scores_by_dim  {dim_id: {'score': float, 'detail': str|dict, 'weight': float}}
            - total_score    float  (Σ score × weight)
    """
    scores_by_dim = {}
    total = 0.0

    for dim in DIMENSIONS:
        dim_id = dim['id']

        # 步骤 1：按维度注册表的字段列表，从数据行中提取字段值
        # 例如领域匹配取 ['domain'] → ['人工智能（软件）']
        #     文本匹配取 ['overview','target_customer'] → [概述文本, 意向客户文本]
        a_vals = [ability.get(f, '') for f in dim['ability_fields']]
        o_vals = [opp.get(f, '') for f in dim['opportunity_fields']]

        # 步骤 2：从 MATCH_CONFIG 中读取维度私有参数
        # 例如 bigram 方法的 max_length 参数 → MATCH_CONFIG['text_max_length'] 或默认 300
        dim_params = {}
        for pk, pv in dim.get('params', {}).items():
            config_key = f"{dim_id}_{pk}"
            dim_params[pk] = MATCH_CONFIG.get(config_key, pv['default'])

        # 步骤 3：调用 compute 闭包 → (score, detail)
        # compute 闭包由 METHOD_REGISTRY[method]['build_compute'](dim_def) 构建
        # 内部已记住字段名、标签等上下文，调用方只需要传值和参数
        score, detail = dim['compute'](a_vals, o_vals, dim_params)

        # 步骤 4：取权重（当前配置中该维度的重要程度 0~1）
        weight = MATCH_CONFIG.get(dim['weight_key'], dim['default_weight'])

        scores_by_dim[dim_id] = {
            'score': round(score, 4),
            'detail': detail,
            'weight': weight,
        }
        total += score * weight  # 加权累加

    return scores_by_dim, round(total, 4)


def _build_match_result(opp, ability, scores_by_dim, total_score, source_is_ability=True):
    """
    构建单条匹配结果字典（v3 格式）。

    同时输出两种格式的得分数据：
      - v3 结构化：dimension_scores → {dim_id: {score, detail, weight}, ...}
      - v2 兼容扁平化：{dim_id}_score / {dim_id}_match_detail
        这样老前端代码无需改动也能读取各维度得分

    source_is_ability 参数决定「谁匹配谁」：
      - True  → 能力→机会匹配（source=能力, target=机会）
      - False → 机会→能力匹配（source=机会, target=能力）
      source_fields / target_fields 根据此参数选择不同的中文标签
    """
    result = {
        'target': opp if source_is_ability else ability,
        'total_score': total_score,
        'dimension_scores': scores_by_dim,
    }

    # ---- v2 兼容：把 dimension_scores 拍平为独立字段 ----
    # 例如 domain_score=0.8, domain_match_detail="精确命中…"
    for dim_id, ds in scores_by_dim.items():
        result[f'{dim_id}_score'] = ds['score']
        result[f'{dim_id}_match_detail'] = ds['detail']

    # ---- 字段对照表（中文标签 → 值） ----
    # 能力→机会匹配时，左侧展示能力字段，右侧展示机会字段
    # 机会→能力匹配时则反过来
    if source_is_ability:
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
    为一条场景能力匹配 Top N 条场景机会。

    每条匹配结果携带：
      - target:              匹配到的场景机会数据
      - dimension_scores:    {dim_id: {score, detail, weight}, ...}  结构化维度得分
      - domain_score / text_score / region_score:  v2 兼容扁平字段
      - total_score:         综合得分
      - source_fields / target_fields: 字段对照
    """
    results = []

    for opp in opportunities:
        scores_by_dim, total_score = _compute_dimension_scores(ability, opp)
        result = _build_match_result(opp, ability, scores_by_dim, total_score,
                                     source_is_ability=True)
        results.append(result)

    results.sort(key=lambda x: x['total_score'], reverse=True)
    return results[:MATCH_CONFIG['top_n']]


def match_opportunity_to_abilities(opp, abilities):
    """
    为一条场景机会匹配 Top N 条场景能力（反向匹配）。

    与 match_ability_to_opportunities 逻辑对称，评分维度完全由 DIMENSIONS 注册表驱动。

    额外兜底逻辑：当领域（domain）维度得分为 0 时，尝试用机会的 domain 字段
    去匹配能力的 target_customer（意向对接客户）字段。
    这解决了「双向匹配不对称」的问题——能力和机会的领域字段命名不同，
    常规匹配可能因字段不同而漏掉，兜底匹配从另一个字段补回来。

    例如：
      能力 domain="人工智能" → 机会 welcome 中查"人工智能"  ← 常规领域匹配
      机会 domain="人工智能" → 能力 target_customer 中查"人工智能" ← 兜底匹配
    """
    results = []

    for ability in abilities:
        scores_by_dim, total_score = _compute_dimension_scores(ability, opp)

        # ---- 领域兜底匹配 ----
        # 触发条件：domain 维度得分正好为 0（精确子串和大类归一化都没命中）
        # 兜底策略：反过来用机会的 domain 去匹配能力的 target_customer 字段
        if 'domain' in scores_by_dim and scores_by_dim['domain']['score'] == 0:
            opp_domain = opp.get('domain', '')
            if opp_domain:
                from .dimensions import _score_string_match
                fallback_score, fallback_detail = _score_string_match(
                    opp_domain,                            # 搜索词：机会的领域
                    ability.get('target_customer', ''),    # 被搜索文本：能力的意向对接客户
                    ability_label='机会所属领域',
                    opp_label='能力意向对接客户',
                )
                if fallback_score > 0:
                    # 保留原有权重，只替换得分和详情
                    old_weight = scores_by_dim['domain']['weight']
                    scores_by_dim['domain'] = {
                        'score': fallback_score,
                        'detail': fallback_detail,
                        'weight': old_weight,
                    }
                    # 重新计算总分（因为领域得分可能变了）
                    total_score = sum(
                        ds['score'] * ds['weight']
                        for ds in scores_by_dim.values()
                    )
                    total_score = round(total_score, 4)

        result = _build_match_result(opp, ability, scores_by_dim, total_score,
                                     source_is_ability=False)
        results.append(result)

    results.sort(key=lambda x: x['total_score'], reverse=True)
    return results[:MATCH_CONFIG['top_n']]
