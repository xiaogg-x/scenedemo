# -*- coding: utf-8 -*-
"""
engine.py —— 匹配引擎模块

职责：
  实现场景能力与场景机会之间的双向匹配评分与排序。

核心算法：
  total_score = domain_score × 0.6 + text_score × 0.4

  domain_score（领域得分）：在"欢迎合作方向"文本中检索能力领域关键词
    - 精确命中（子串匹配） → 1.0
    - 大类近似（归一化后相同） → 0.5
    - 无关 → 0.0

  text_score（文本重叠度）：中文 2-gram Jaccard 相似度
    - 提取两个文本的 bigram 字符集 → 计算交集/并集比值

API：
  match_ability_to_opportunities(ability, opportunities) → list[dict] (Top3)
  match_opportunity_to_abilities(opp, abilities)       → list[dict] (Top3)
"""

import re
from .normalizer import normalize_domain


# ============================================================================
# 权重配置
# ============================================================================
DOMAIN_WEIGHT = 0.6   # 领域匹配权重
TEXT_WEIGHT   = 0.4   # 文本相似度权重
TOP_N         = 3     # 返回前 N 条最佳匹配


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
    # 用正则保留 Unicode 中文范围 \\u4e00-\\u9fff
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
# 核心评分函数
# ============================================================================

def compute_domain_score(ability_domain, opp_welcome):
    """
    计算领域匹配得分（0.0 / 0.5 / 1.0）。

    策略:
      1. 先尝试精确子串匹配：能力的领域关键词是否直接出现在"欢迎合作方向"文本中
      2. 若未精确命中，尝试大类归一化比较

    参数:
        ability_domain (str): 场景能力的"所属产业领域"
        opp_welcome     (str): 场景机会的"欢迎合作方向"

    返回:
        float: 1.0（精确命中）、0.5（大类近似）、0.0（无关）
    """
    if not ability_domain or not opp_welcome:
        return 0.0

    # ---- 策略1：精确子串匹配 ----
    # 在"欢迎合作方向"中直接搜索能力的领域关键词（完整字符串）
    if ability_domain in opp_welcome:
        return 1.0

    # ---- 策略2：大类归一化匹配 ----
    # 将能力领域映射到大类（如"人工智能（软件）"→"人工智能"）
    big_cls_a = normalize_domain(ability_domain)

    # 在"欢迎合作方向"中提取所有可能的领域关键词组合（滑动窗口切词）
    # 取前 60 个字符作为检索范围（欢迎合作方向的领域标注通常在最前面）
    prefix = opp_welcome[:60] if len(opp_welcome) > 60 else opp_welcome

    # 检查前缀中是否有任何词归一化后与能力大类相同
    for i in range(len(prefix)):
        for j in range(i + 2, min(i + 30, len(prefix) + 1)):
            candidate = prefix[i:j]
            # 只有当 candidate 是独立的领域词时才比较（避免无意义的短片段）
            if normalize_domain(candidate) == big_cls_a:
                return 0.5
            if normalize_domain(candidate) != candidate:
                # 已经是归一化命中（candidate在映射表里）
                if normalize_domain(candidate) == big_cls_a:
                    return 0.5

    return 0.0


def compute_text_score(text_a, text_b):
    """
    计算两段文本的中文 2-gram Jaccard 相似度。

    过程:
      1. 清洗文本（去除非中文字符）
      2. 截取前 300 个有效汉字（控制计算量，避免超长文本稀释相似度）
      3. 分别提取 bigram 集合
      4. 计算 Jaccard 相似度

    参数:
        text_a (str): 能力侧文本（能力概述 + 意向对接客户）
        text_b (str): 机会侧文本（应用场景概述 + 欢迎合作方向）

    返回:
        float: 0.0 ~ 1.0 之间的相似度值
    """
    # Step 1: 清洗，只保留中文字符
    clean_a = _clean_text(text_a)
    clean_b = _clean_text(text_b)

    # Step 2: 截取前 300 个汉字，避免长文本稀释相似度
    clean_a = clean_a[:300]
    clean_b = clean_b[:300]

    # Step 3: 提取 bigram 集合
    bigrams_a = _extract_bigrams(clean_a)
    bigrams_b = _extract_bigrams(clean_b)

    # Step 4: 计算 Jaccard 相似度
    return _jaccard_similarity(bigrams_a, bigrams_b)


# ============================================================================
# 匹配入口函数
# ============================================================================

def match_ability_to_opportunities(ability, opportunities):
    """
    为一条场景能力匹配 Top N 条场景机会。

    参数:
        ability       (dict): 单条场景能力数据
        opportunities (list[dict]): 全部场景机会列表

    返回:
        list[dict]: 按总分降序排列的前 N 条匹配结果，每条包含：
            - target       (dict): 匹配到的场景机会完整数据
            - domain_score (float): 领域得分
            - text_score   (float): 文本重叠度得分
            - total_score  (float): 综合得分
    """
    # 构造能力侧的合本文本（用于文本相似度计算）
    ability_text = ability.get('overview', '') + ' ' + ability.get('target_customer', '')
    ability_domain = ability.get('domain', '')

    results = []  # 存放所有候选机会的评分结果

    for opp in opportunities:
        # ---- 计算领域得分（权重60%） ----
        # 能力的"所属产业领域" vs 机会的"欢迎合作方向"
        domain_score = compute_domain_score(ability_domain, opp.get('welcome', ''))

        # ---- 计算文本得分（权重40%） ----
        # 能力侧：能力概述 + 意向对接客户
        # 机会侧：应用场景概述 + 欢迎合作方向
        opp_text = opp.get('overview', '') + ' ' + opp.get('welcome', '')
        text_score = compute_text_score(ability_text, opp_text)

        # ---- 综合评分 ----
        total_score = domain_score * DOMAIN_WEIGHT + text_score * TEXT_WEIGHT

        results.append({
            'target':       opp,
            'domain_score': round(domain_score, 4),
            'text_score':   round(text_score, 4),
            'total_score':  round(total_score, 4),
        })

    # ---- 按总分降序排列，取前 TOP_N ----
    results.sort(key=lambda x: x['total_score'], reverse=True)
    return results[:TOP_N]


def match_opportunity_to_abilities(opp, abilities):
    """
    为一条场景机会匹配 Top N 条场景能力。

    与 match_ability_to_opportunities 逻辑对称：
      - 领域得分：用机会的"应用场景所属领域"检索能力的"意向对接客户"
      - 文本得分：同样的 bigram Jaccard，交换锚点

    参数:
        opp       (dict): 单条场景机会数据
        abilities (list[dict]): 全部场景能力列表

    返回:
        list[dict]: 按总分降序排列的前 N 条匹配结果，结构同上
    """
    # 构造机会侧的合本文本
    opp_text = opp.get('overview', '') + ' ' + opp.get('welcome', '')

    # ---- 反向领域匹配策略 ----
    # 机会的 "欢迎合作方向" 字段通常以领域关键词开头（如"人工智能（软件）：..."）
    # 提取"欢迎合作方向"的前缀作为领域关键词，用于检索能力的"意向对接客户"
    # 同时保留原始 "应用场景所属领域" 作为兜底
    opp_welcome = opp.get('welcome', '')
    opp_domain_raw = opp.get('domain', '')

    results = []

    for ability in abilities:
        # 优先用"欢迎合作方向"开头的领域词去匹配能力的"意向对接客户"
        domain_score = compute_domain_score(
            ability.get('domain', ''),  # 能力的领域
            opp_welcome                  # 机会的"欢迎合作方向"
        )
        # 如果得分为0，再用机会的原始领域字段做兜底匹配
        if domain_score == 0 and opp_domain_raw:
            domain_score = compute_domain_score(
                opp_domain_raw,
                ability.get('target_customer', '')
            )

        # ---- 文本得分（同样的 bigram Jaccard） ----
        ability_text = ability.get('overview', '') + ' ' + ability.get('target_customer', '')
        text_score = compute_text_score(opp_text, ability_text)

        # ---- 综合评分 ----
        total_score = domain_score * DOMAIN_WEIGHT + text_score * TEXT_WEIGHT

        results.append({
            'target':       ability,
            'domain_score': round(domain_score, 4),
            'text_score':   round(text_score, 4),
            'total_score':  round(total_score, 4),
        })

    results.sort(key=lambda x: x['total_score'], reverse=True)
    return results[:TOP_N]
