# -*- coding: utf-8 -*-
"""
engine.py —— 匹配引擎模块（v2：返回详细匹配明细）

职责：
  实现场景能力与场景机会之间的双向匹配评分与排序。
  每条匹配结果携带完整的评分明细，方便前端展示和参数调优。

核心算法：
  total_score = domain_score × DOMAIN_WEIGHT
              + text_score   × TEXT_WEIGHT
              + region_score × REGION_WEIGHT

  domain_score（领域得分）：在"欢迎合作方向"文本中检索能力领域关键词
    - 精确命中（子串匹配） → 1.0
    - 大类近似（归一化后相同） → 0.5
    - 无关 → 0.0

  text_score（文本重叠度）：中文 2-gram Jaccard 相似度
    - 提取两个文本的 bigram 字符集 → 计算交集/并集比值

  region_score（区域得分）：能力所属区 vs 机会所属区域
    - 精确匹配（完全相同） → 1.0
    - 不匹配 → 0.0

API：
  match_ability_to_opportunities(ability, opportunities) → list[dict] (Top N)
  match_opportunity_to_abilities(opp, abilities)             → list[dict] (Top N)
  get_config() → dict  (返回当前匹配参数)
  update_config(new_config) → dict  (更新匹配参数)
"""

import json
import os
import re
from .normalizer import normalize_domain


# ============================================================================
# 匹配参数配置（集中管理，供前端 /api/config 读写）
# ============================================================================
# 修改这些值会影响所有后续匹配计算
# 前端可通过 POST /api/config 动态更新
# ============================================================================
MATCH_CONFIG = {
    'domain_weight':   0.4,    # 领域匹配权重（0~1）
    'text_weight':     0.3,    # 文本相似度权重（0~1）
    'region_weight':   0.3,    # 区域匹配权重（0~1）
    'top_n':           3,      # 返回前 N 条最佳匹配
    'text_max_length': 300,    # 文本匹配时截取的最大汉字数（避免超长文本稀释相似度）
}

# 配置文件路径（与 Excel 数据文件同目录）
CONFIG_FILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '后台数据', 'config.json'
))


def save_config_to_file():
    """将当前 MATCH_CONFIG 持久化写入 config.json，下次启动时自动恢复。"""
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
    """
    返回当前匹配参数配置的副本（防止外部意外修改内部引用）。

    返回:
        dict: 包含 domain_weight, text_weight, top_n, text_max_length
    """
    return dict(MATCH_CONFIG)


def update_config(new_config):
    """
    更新匹配参数配置。只会更新传入的键，其他键保持不变。
    更新后自动持久化到 config.json。

    参数:
        new_config (dict): 需要更新的参数字典，如 {"domain_weight": 0.7}

    返回:
        dict: 更新后的完整配置
    """
    for key in ('domain_weight', 'text_weight', 'region_weight', 'top_n', 'text_max_length'):
        if key in new_config:
            MATCH_CONFIG[key] = new_config[key]
    save_config_to_file()
    return dict(MATCH_CONFIG)


# ============================================================================
# 文本预处理
# ============================================================================

def _clean_text(text):
    """
    清洗文本：去除所有非中文字符（标点、空格、数字、英文字母等），保留纯中文。

    参数:
        text (str): 原始文本

    返回:
        str: 只保留中文字符的干净文本
    """
    if not text:
        return ''
    # 用正则保留 Unicode 中文范围 \u4e00-\u9fff
    return re.sub(r'[^\u4e00-\u9fff]', '', text)


def _extract_bigrams(text):
    """
    从中文文本中提取 2-gram（bigram）字符集合。

    原理：
      将文本按每 2 个连续汉字切分。例如 "智慧交通" → {"智慧", "慧交", "交通"}
      每个 bigram 保留字符间的局部上下文关系。

    参数:
        text (str): 已清洗的中文文本（纯中文，无标点空白）

    返回:
        set[str]: bigram 集合，每个元素为 2 个汉字组成的字符串
    """
    bigrams = set()
    for i in range(len(text) - 1):
        bigrams.add(text[i:i+2])
    return bigrams


def _jaccard_similarity(set_a, set_b):
    """
    计算两个集合的 Jaccard 相似度。

    公式:
        Jaccard(A, B) = |A ∩ B| / |A ∪ B|

    参数:
        set_a (set): 文本 A 的 bigram 集合
        set_b (set): 文本 B 的 bigram 集合

    返回:
        float: 0.0 ~ 1.0 之间的相似度值。空集合交集返回 0.0。
    """
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b   # 交集
    union        = set_a | set_b   # 并集
    if len(union) == 0:
        return 0.0
    return len(intersection) / len(union)


# ============================================================================
# 核心评分函数（v2：返回 (score, detail)）
# ============================================================================

def compute_domain_score(ability_domain, opp_welcome):
    """
    计算领域匹配得分，同时返回匹配详情文本。

    策略:
      1. 先尝试精确子串匹配：能力的领域关键词是否直接出现在"欢迎合作方向"文本中
      2. 若未精确命中，尝试大类归一化比较

    参数:
        ability_domain (str): 场景能力的"所属产业领域"
        opp_welcome     (str): 场景机会的"欢迎合作方向"

    返回:
        tuple[float, str]:
            - score  (float): 1.0 / 0.5 / 0.0
            - detail (str):   人类可读的匹配过程描述
    """
    if not ability_domain or not opp_welcome:
        return 0.0, '无有效领域信息可供匹配（一侧字段为空）'

    # ---- 策略1：精确子串匹配 ----
    if ability_domain in opp_welcome:
        # 提取匹配位置周围的上下文（前后各取最多 20 个字符）
        idx = opp_welcome.find(ability_domain)
        start = max(0, idx - 20)
        end   = min(len(opp_welcome), idx + len(ability_domain) + 20)
        context = opp_welcome[start:end].replace('\n', ' ').replace('\r', '')
        return 1.0, (
            f'精确命中（得分：1.0）\n'
            f'能力领域：「{ability_domain}」\n'
            f'在机会「欢迎合作方向」字段中直接出现\n'
            f'匹配位置上下文：「…{context}…」'
        )

    # ---- 策略2：大类归一化匹配 ----
    big_cls_a = normalize_domain(ability_domain)

    # 取欢迎合作方向前 60 个字符作为检索范围（领域标注通常在最前面）
    prefix = opp_welcome[:60] if len(opp_welcome) > 60 else opp_welcome

    # 滑动窗口检查前缀中是否有词归一化后与能力大类相同
    for i in range(len(prefix)):
        for j in range(i + 2, min(i + 30, len(prefix) + 1)):
            candidate = prefix[i:j]
            cand_norm = normalize_domain(candidate)
            if cand_norm == big_cls_a and cand_norm != candidate:
                # candidate 在映射表里，且归一化后匹配
                return 0.5, (
                    f'大类近似匹配（得分：0.5）\n'
                    f'能力领域：「{ability_domain}」归一化为大类「{big_cls_a}」\n'
                    f'在机会「欢迎合作方向」前60字中找到同大类词「{candidate}」\n'
                    f'匹配依据：两者归一化后同属于「{big_cls_a}」大类'
                )

    return 0.0, (
        f'未命中（得分：0.0）\n'
        f'能力领域：「{ability_domain}」→ 大类「{big_cls_a}」\n'
        f'在机会「欢迎合作方向」前60字中未找到匹配的领域词'
    )


def compute_text_score(text_a, text_b):
    """
    计算两段文本的中文 2-gram Jaccard 相似度，同时返回重叠详情。

    过程:
      1. 清洗文本（去除非中文字符）
      2. 截取前 N 个有效汉字（N 由 MATCH_CONFIG['text_max_length'] 控制）
      3. 分别提取 bigram 集合
      4. 计算 Jaccard 相似度
      5. 收集重叠的 bigram 列表

    参数:
        text_a (str): 能力侧文本（能力概述 + 意向对接客户）
        text_b (str): 机会侧文本（应用场景概述 + 欢迎合作方向）

    返回:
        tuple[float, dict]:
            - score  (float): 0.0 ~ 1.0 Jaccard 相似度
            - detail (dict):  {
                'overlapping_bigrams': [str, ...],   # 重叠 bigram 列表（按字母序，最多15个）
                'overlap_count':       int,          # 重叠 bigram 数量
                'a_bigram_count':      int,          # 文本A的 bigram 总数
                'b_bigram_count':      int,          # 文本B的 bigram 总数
                'union_count':         int,          # 并集大小
                'text_a_snippet':      str,          # 文本A前50字摘要
                'text_b_snippet':      str,          # 文本B前50字摘要
              }
    """
    max_len = MATCH_CONFIG['text_max_length']

    # Step 1: 清洗，只保留中文字符
    clean_a = _clean_text(text_a)
    clean_b = _clean_text(text_b)

    # Step 2: 截取前 max_len 个汉字，避免长文本稀释相似度
    clean_a = clean_a[:max_len]
    clean_b = clean_b[:max_len]

    # Step 3: 提取 bigram 集合
    bigrams_a = _extract_bigrams(clean_a)
    bigrams_b = _extract_bigrams(clean_b)

    # Step 4: 计算 Jaccard 相似度
    score = _jaccard_similarity(bigrams_a, bigrams_b)

    # Step 5: 收集重叠 bigram（按字母序，最多15个用于前端展示）
    overlapping = bigrams_a & bigrams_b
    overlap_list = sorted(overlapping)[:15] if overlapping else []

    # 文本摘要（用于前端展示理解匹配文本内容）
    snippet_a = clean_a[:50] + ('...' if len(clean_a) > 50 else '')
    snippet_b = clean_b[:50] + ('...' if len(clean_b) > 50 else '')

    detail = {
        'overlapping_bigrams': overlap_list,
        'overlap_count':       len(overlapping),
        'a_bigram_count':      len(bigrams_a),
        'b_bigram_count':      len(bigrams_b),
        'union_count':         len(bigrams_a | bigrams_b),
        'text_a_snippet':      snippet_a,
        'text_b_snippet':      snippet_b,
    }
    return score, detail


def compute_region_score(ability_district, opp_area):
    """
    计算区域匹配得分，同时返回匹配详情文本。

    策略:
      两端区域值完全相同 → 1.0（精确匹配）
      否则 → 0.0（不同区，或一侧为非区级值如"南京市""江苏省"）

    参数:
        ability_district (str): 场景能力的"所属区（开发区）"
        opp_area         (str): 场景机会的"应用场景所属区域"

    返回:
        tuple[float, str]:
            - score  (float): 1.0 / 0.0
            - detail (str):   人类可读的匹配过程描述
    """
    a = (ability_district or '').strip()
    b = (opp_area or '').strip()

    if not a or not b:
        return 0.0, '无有效区域信息可供匹配（一侧区域字段为空）'

    if a == b:
        return 1.0, (
            f'区域匹配（得分：1.0）\n'
            f'能力所属区：「{a}」\n'
            f'机会所属区域：「{b}」\n'
            f'判定：完全一致，同区匹配'
        )

    return 0.0, (
        f'区域不匹配（得分：0.0）\n'
        f'能力所属区：「{a}」\n'
        f'机会所属区域：「{b}」\n'
        f'判定：非同区'
    )


# ============================================================================
# 匹配入口函数（v2：返回详细匹配明细）
# ============================================================================

def match_ability_to_opportunities(ability, opportunities):
    """
    为一条场景能力匹配 Top N 条场景机会。

    每条匹配结果携带：
      - target:              匹配到的场景机会数据
      - domain_score:        领域得分 (0.0/0.5/1.0)
      - text_score:          文本重叠度得分 (0~1)
      - total_score:         综合得分
      - domain_match_detail: 领域匹配过程描述（字符串）
      - text_match_detail:   文本匹配详情（dict，含重叠 bigram）
      - match_fields:        参与匹配的字段名及取值对照

    参数:
        ability       (dict): 单条场景能力数据
        opportunities (list[dict]): 全部场景机会列表

    返回:
        list[dict]: 按总分降序排列的前 N 条匹配结果
    """
    ability_text   = ability.get('overview', '') + ' ' + ability.get('target_customer', '')
    ability_domain = ability.get('domain', '')
    ability_district = ability.get('district', '')

    # 要参与 match_fields 展示的能力侧字段
    ability_fields = {
        '产品名称':   ability.get('name', ''),
        '所属产业领域': ability.get('domain', ''),
        '所属区':     ability_district,
        '能力概述':   ability.get('overview', ''),
        '意向对接客户': ability.get('target_customer', ''),
    }

    results = []

    for opp in opportunities:
        opp_welcome = opp.get('welcome', '')
        opp_area    = opp.get('area', '')

        # ---- 计算领域得分 + 详情 ----
        domain_score, domain_detail = compute_domain_score(ability_domain, opp_welcome)

        # ---- 计算文本得分 + 详情 ----
        opp_text = opp.get('overview', '') + ' ' + opp_welcome
        text_score, text_detail = compute_text_score(ability_text, opp_text)

        # ---- 计算区域得分 + 详情 ----
        region_score, region_detail = compute_region_score(ability_district, opp_area)

        # ---- 综合评分 ----
        total_score = (
            domain_score * MATCH_CONFIG['domain_weight']
            + text_score   * MATCH_CONFIG['text_weight']
            + region_score * MATCH_CONFIG['region_weight']
        )

        # ---- 要展示的机会侧字段对照 ----
        opp_fields = {
            '应用场景项目名称': opp.get('name', ''),
            '应用场景所属领域': opp.get('domain', ''),
            '应用场景所属区域': opp_area,
            '应用场景概述':   opp.get('overview', ''),
            '欢迎合作方向':   opp_welcome,
        }

        results.append({
            'target':              opp,
            'domain_score':         round(domain_score, 4),
            'text_score':           round(text_score, 4),
            'region_score':         round(region_score, 4),
            'total_score':          round(total_score, 4),
            'domain_match_detail':  domain_detail,
            'text_match_detail':    text_detail,
            'region_match_detail':  region_detail,
            'source_fields':        ability_fields,
            'target_fields':        opp_fields,
        })

    # 按总分降序排列，取前 TOP_N
    results.sort(key=lambda x: x['total_score'], reverse=True)
    return results[:MATCH_CONFIG['top_n']]


def match_opportunity_to_abilities(opp, abilities):
    """
    为一条场景机会匹配 Top N 条场景能力（反向匹配）。

    与 match_ability_to_opportunities 逻辑对称：
      - 领域得分：优先用机会的"欢迎合作方向"前缀匹配能力的领域
      - 文本得分：同样的 bigram Jaccard，交换锚点

    参数:
        opp       (dict): 单条场景机会数据
        abilities (list[dict]): 全部场景能力列表

    返回:
        list[dict]: 按总分降序排列的前 N 条匹配结果（结构同上）
    """
    opp_text    = opp.get('overview', '') + ' ' + opp.get('welcome', '')
    opp_welcome = opp.get('welcome', '')
    opp_domain_raw = opp.get('domain', '')
    opp_area    = opp.get('area', '')

    # 机会侧要展示的字段
    opp_fields = {
        '应用场景项目名称': opp.get('name', ''),
        '应用场景所属领域': opp.get('domain', ''),
        '应用场景所属区域': opp_area,
        '应用场景概述':   opp.get('overview', ''),
        '欢迎合作方向':   opp_welcome,
    }

    results = []

    for ability in abilities:
        ability_district = ability.get('district', '')

        # ---- 领域得分 ----
        # 优先用"欢迎合作方向"匹配能力的领域（机会侧欢迎合作方向前缀 = 能力领域）
        domain_score, domain_detail = compute_domain_score(
            ability.get('domain', ''),
            opp_welcome
        )
        # 如果得分为0，再用机会的原始领域字段做兜底匹配
        if domain_score == 0 and opp_domain_raw:
            domain_score2, domain_detail2 = compute_domain_score(
                opp_domain_raw,
                ability.get('target_customer', '')
            )
            if domain_score2 > 0:
                domain_score = domain_score2
                domain_detail = domain_detail2

        # ---- 文本得分 ----
        ability_text = ability.get('overview', '') + ' ' + ability.get('target_customer', '')
        text_score, text_detail = compute_text_score(opp_text, ability_text)

        # ---- 区域得分 ----
        region_score, region_detail = compute_region_score(ability_district, opp_area)

        # ---- 综合评分 ----
        total_score = (
            domain_score * MATCH_CONFIG['domain_weight']
            + text_score   * MATCH_CONFIG['text_weight']
            + region_score * MATCH_CONFIG['region_weight']
        )

        # 能力侧字段对照
        ability_fields = {
            '产品名称':   ability.get('name', ''),
            '所属产业领域': ability.get('domain', ''),
            '所属区':     ability_district,
            '能力概述':   ability.get('overview', ''),
            '意向对接客户': ability.get('target_customer', ''),
        }

        results.append({
            'target':              ability,
            'domain_score':         round(domain_score, 4),
            'text_score':           round(text_score, 4),
            'region_score':         round(region_score, 4),
            'total_score':          round(total_score, 4),
            'domain_match_detail':  domain_detail,
            'text_match_detail':    text_detail,
            'region_match_detail':  region_detail,
            'source_fields':        opp_fields,
            'target_fields':        ability_fields,
        })

    results.sort(key=lambda x: x['total_score'], reverse=True)
    return results[:MATCH_CONFIG['top_n']]
