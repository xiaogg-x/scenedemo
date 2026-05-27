# -*- coding: utf-8 -*-
"""
dimensions.py —— 匹配维度注册表（文件持久化版）

══════════════════════════════════════════════════════════════════════════════
模块概述
══════════════════════════════════════════════════════════════════════════════

本模块是场景匹配系统的**核心维度管理中枢**，实现了「可插拔维度」架构。
整个匹配引擎（engine.py）不硬编码任何具体匹配逻辑，而是完全依赖本模块提供的
DIMENSIONS 注册表来驱动评分计算。

══════════════════════════════════════════════════════════════════════════════
核心职责
══════════════════════════════════════════════════════════════════════════════

  1. 定义可用的匹配方法（字符串匹配 / bigram 文本匹配 / 向量语义匹配）
     → 通过 METHOD_REGISTRY 字典实现方法注册，新增匹配算法只需：
        a) 实现 _make_xxx_adapter() 工厂函数
        b) 在 METHOD_REGISTRY 中添加条目

  2. 管理维度列表的加载、保存、增删
     → 维度定义持久化到 后台数据/dimensions.json
     → 文件不存在时，用 DEFAULT_DIMENSIONS 种子数据初始化

  3. 提供适配器工厂：根据 method 名称 + 字段定义生成 compute 闭包
     → 每个维度的 compute 函数是一个 closure（闭包），
       内部已记住字段名、标签等上下文，调用方只需传值即可

  4. 维度定义与运行时对象的分离设计
     → JSON 文件中只存纯数据字典（不含函数）
     → 运行时通过 _dim_def_to_runtime() 附加上 compute 闭包
     → 持久化前通过 _runtime_to_dim_def() 剥离不可序列化的 compute

══════════════════════════════════════════════════════════════════════════════
可插拔架构说明
══════════════════════════════════════════════════════════════════════════════

本系统采用「策略模式 + 工厂模式 + 注册表」的组合架构：

  METHOD_REGISTRY（策略注册表）
    │
    ├── string_match    → _make_string_match_adapter()  → compute(a_vals, o_vals, params)
    │                      精确子串命中(1.0) / 大类归一化近似(0.5) / 未命中(0.0)
    │
    ├── bigram          → _make_bigram_adapter()         → compute(a_vals, o_vals, params)
    │                      中文 2-gram Jaccard 相似度
    │
    └── vector_semantic → _make_vector_adapter()          → compute(a_vals, o_vals, params)
                           SentenceTransformer 嵌入 + 余弦相似度

新增匹配方法的步骤：
  Step 1: 在此 MODULE 中实现 _make_xxx_adapter(dim_def) 工厂函数
  Step 2: 在 METHOD_REGISTRY 字典中添加对应条目
  Step 3: 前端 add_dimension.js 的 _renderMethodParams() 中添加对应的 UI 控件

══════════════════════════════════════════════════════════════════════════════
维度 JSON 格式（存文件用，不含 compute 函数）
══════════════════════════════════════════════════════════════════════════════

  {
    "id":               "domain",                    // 维度唯一标识符
    "label":            "领域匹配",                   // 前端展示名称
    "weight_key":       "domain_weight",             // 配置文件中的权重键名
    "ability_fields":   ["domain"],                  // 能力侧参与匹配的字段列表
    "opportunity_fields": ["welcome"],               // 机会侧参与匹配的字段列表
    "method":           "string_match",              // 匹配方法名（对应 METHOD_REGISTRY key）
    "method_labels":   {"ability": "能力领域", "opportunity": "欢迎合作方向"},
                                                    // 评分详情中的中文标签
    "default_weight":   0.4,                         // 默认权重（0~1）
    "detail_type":      "text",                       // 前端渲染方式：'text'|'bigram'|'vector'
    "icon":             "🔍",                        // 前端图标
    "score_label":      "领域",                       // 得分列标题
    "color":            "#3B82F6",                   // 前端主题色
    "params":           {},                          // 方法私有参数（如 max_length, threshold 等）
    "focus_description":"关注场景能力所属产业领域..." // 维度关注角度描述（给 LLM 用）
  }
"""

import re
import json
import os

import numpy as np

from .normalizer import normalize_domain


# ============================================================================
# 通用文本处理工具函数
# ============================================================================

def _clean_text(text):
    """
    清洗文本：去除所有非中文字符，保留纯中文内容。

    这是 bigram 文本匹配的前置步骤。中文 NLP 处理中，
    标点符号、数字、英文字母通常对语义相似度的贡献较小，
    过滤后可以减少噪声，提高 Jaccard 相似度的准确性。

    参数:
        text (str): 原始文本，可能包含中文、英文、数字、标点等混合内容

    返回:
        str: 纯中文字符串，如果输入为空或 None 则返回空字符串

    示例:
        >>> _clean_text("智慧城市AI解决方案 v2.0")
        "智慧城市解决方案"
    """
    if not text:
        return ''
    # 使用 Unicode 范围 \\u4e00-\\u9fff 匹配所有 CJK 统一表意文字（中文汉字）
    return re.sub(r'[^\u4e00-\u9fff]', '', text)


def _extract_bigrams(text):
    """
    从中文文本中提取 2-gram（二元语法/相邻字符对）集合。

    Bigram 是自然语言处理中最基础的特征之一，它将文本拆分为
    所有连续的两个字符组成的片段。例如"智慧交通"会被拆分为：
    "智慧"、"慧交"、"交通" 三组 bigram。

    为什么用集合而不是列表？
      - 集合天然去重，同一 bigram 无论出现多少次只算一次
      - 这使得后续的 Jaccard 相似度计算更关注「有哪些字符组合」而非「出现了多少次」
      - 对于短文本匹配场景，这种简化是合理的

    参数:
        text (str): 已清洗过的纯中文文本（建议先用 _clean_text 处理）

    返回:
        set[str]: 文本中所有不重复的 bigram 字符对集合

    示例:
        >>> _extract_bigrams("智慧交通")
        {"智慧", "慧交", "交通"}
        >>> _extract_bigrams("智")   # 长度不足 2 时返回空集
        set()
    """
    bigrams = set()
    # range(len(text) - 1): 确保有至少 2 个字符才能形成 bigram
    for i in range(len(text) - 1):
        # 切片取 i 和 i+1 两个位置的字符组成一个 bigram
        bigrams.add(text[i:i+2])
    return bigrams


def _jaccard_similarity(set_a, set_b):
    """
    计算两个集合之间的 Jaccard 相似系数。

    Jaccard 系数 = |A ∩ B| / |A ∪ B|
    取值范围 [0, 1]，1 表示两个集合完全相同，0 表示无交集。

    本系统中用于衡量两段中文文本在字符组合层面的重叠程度。
    例如：
      A = {"智慧", "慧交", "交通"}  （"智慧交通"的bigram）
      B = {"智能", "能交", "交通"}  （"智能交通"的bigram）
      A ∩ B = {"交通"}, A ∪ B 有 5 个元素
      Jaccard = 1/5 = 0.2

    参数:
        set_a (set): 第一个 bigram 集合
        set_b (set): 第二个 bigram 集合

    返回:
        float: Jaccard 相似度，范围 [0.0, 1.0]；任一集合为空时返回 0.0
    """
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b   # 交集：两边都有的 bigram
    union = set_a | set_b          # 并集：所有出现过的 bigram
    if len(union) == 0:
        return 0.0
    return len(intersection) / len(union)


# ============================================================================
# 核心评分函数 —— 每个函数对应一种具体的匹配算法实现
# ============================================================================

def _score_string_match(ability_val, opp_val,
                       ability_label='能力值', opp_label='机会值'):
    """
    通用字符串匹配得分计算器——采用「精确子串 + 大类归一化」双层策略。

    ══════════════════════════════════════════════════════════════════════
    匹配策略（三层判定，优先级从高到低）
    ══════════════════════════════════════════════════════════════════════

      策略1 — 精确子串匹配（得分 1.0）
        判断 ability_val 是否作为子串完整出现在 opp_val 中。
        例：ability="人工智能"，opp="我们正在寻找人工智能大模型应用合作伙伴"
            → "人工智能" 完整出现在 opp 中 → 1.0 分

      策略2 — 大类归一化近似匹配（得分 0.5）
        当精确匹配失败时，将双方文本通过 normalizer 归一化为标准大类名，
        再检查归一化后是否一致。
        例：ability="AI大模型" → normalize → "人工智能"
              opp 前60字中出现"人工智能技术方案" → normalize → "人工智能"
            → 两者归一化后同属"人工智能"大类 → 0.5 分
        大类归一化的意义：解决同义词、简称、不同写法导致的漏匹配问题。

      策略3 — 完全未匹配（得分 0.0）
        以上两种策略均未命中 → 0.0 分

    ══════════════════════════════════════════════════════════════════════
    参数
    ══════════════════════════════════════════════════════════════════════

      ability_val  (str): 能力侧字段的原始值（被搜索的关键词）
      opp_val      (str): 机会侧字段的原始值（被搜索的目标文本）
      ability_label (str): 能力侧字段的中文显示标签，用于构造详情消息
      opp_label   (str): 机会侧字段的中文显示标签，用于构造详情消息

    ══════════════════════════════════════════════════════════════════════
    返回
    ══════════════════════════════════════════════════════════════════════

      tuple[float, str]: (得分, 详情文本)
        - score: 0.0 或 0.5 或 1.0
        - detail: 人类可读的匹配详情，包含命中的具体位置上下文或未命中的原因
    """
    if not ability_val or not opp_val:
        return 0.0, (
            f'无有效信息可供匹配'
            f'（一侧{ability_label}或{opp_label}字段为空）'
        )

    # ─── 策略1：精确子串匹配 ───
    # Python 的 in 操作符执行的是子串查找（非正则，非单词边界）
    if ability_val in opp_val:
        # 找到精确命中位置，截取前后各20字符作为上下文展示
        idx = opp_val.find(ability_val)
        start = max(0, idx - 20)                                    # 左边界不越界
        end = min(len(opp_val), idx + len(ability_val) + 20)       # 右边界不越界
        context = opp_val[start:end].replace('\n', ' ').replace('\r', '')  # 清理换行符便于展示
        return 1.0, (
            f'精确命中（得分：1.0）\n'
            f'{ability_label}：「{ability_val}」\n'
            f'在机会「{opp_label}」字段中直接出现\n'
            f'匹配位置上下文：「…{context}…」'
        )

    # ─── 策略2：大类归一化近似匹配 ───
    # 先把能力值归一化为标准大类名
    big_cls_a = normalize_domain(ability_val)
    # 只扫描机会文本前60个字符（性能优化：避免全文遍历）
    prefix = opp_val[:60] if len(opp_val) > 60 else opp_val

    # 暴力枚举所有长度为 2~29 的子串，逐一归一化后比对
    # 时间复杂度 O(n^2)，但 n=60 很小，实际可忽略不计
    for i in range(len(prefix)):
        for j in range(i + 2, min(i + 30, len(prefix) + 1)):
            candidate = prefix[i:j]
            cand_norm = normalize_domain(candidate)
            # cand_norm != candidate 排除「原文就相同」的情况（那应该在策略1就被命中了）
            if cand_norm == big_cls_a and cand_norm != candidate:
                return 0.5, (
                    f'大类近似匹配（得分：0.5）\n'
                    f'{ability_label}：「{ability_val}」'
                    f'归一化为大类「{big_cls_a}」\n'
                    f'在机会「{opp_label}」前60字中找到同大类词'
                    f'「{candidate}」\n'
                    f'匹配依据：两者归一化后同属于'
                    f'「{big_cls_a}」大类'
                )

    # ─── 策略3：完全未命中 ───
    return 0.0, (
        f'未命中（得分：0.0）\n'
        f'{ability_label}：「{ability_val}」→ 大类「{big_cls_a}」\n'
        f'在机会「{opp_label}」前60字中未找到匹配项'
    )


def _score_text(text_a, text_b, max_len=300):
    """
    文本重叠度得分计算器——基于中文 2-gram Jaccard 相似度。

    与 _score_string_match 不同，本函数不做精确/模糊匹配判定，
    而是将两段文本视为「字符组合的袋子」，用集合论方法量化其重叠程度。

    适用场景：长文本之间的粗粒度相似度比较，如能力概述 vs 机会概述。

    ══════════════════════════════════════════════════════════════════════
    处理流程
    ══════════════════════════════════════════════════════════════════════

      1. _clean_text(): 去除非中文字符
      2. 截取前 max_len 字符（防止超长文本导致 bigram 集合过大，稀释相似度）
      3. _extract_bigrams(): 提取 2-gram 集合
      4. _jaccard_similarity(): 计算 Jaccard 系数
      5. 构造 detail 字典（含重叠的 bigram 列表、数量统计等）

    ══════════════════════════════════════════════════════════════════════
    参数
    ══════════════════════════════════════════════════════════════════════

      text_a  (str): 第一段文本（通常是能力侧文本）
      text_b  (str): 第二段文本（通常是机会侧文本）
      max_len (int): 单侧文本最大截取长度（默认300字符），超出部分将被丢弃

    ══════════════════════════════════════════════════════════════════════
    返回
    ══════════════════════════════════════════════════════════════════════

      tuple[float, dict]:
        - score  (float): Jaccard 相似度 [0.0, 1.0]
        - detail (dict): 详细信息字典，包含：
            * overlapping_bigrams (list): 重叠的 bigram 列表（最多15个，用于前端高亮展示）
            * overlap_count      (int):   重叠 bigram 总数
            * a_bigram_count     (int):   文本A的bigram总数
            * b_bigram_count     (int):   文本B的bigram总数
            * union_count        (int):   并集大小
            * text_a_snippet     (str):   文本A前50字符摘要
            * text_b_snippet     (str):   文本B前50字符摘要
    """
    clean_a = _clean_text(text_a)[:max_len]
    clean_b = _clean_text(text_b)[:max_len]

    # 分别提取双方的 bigram 集合
    bigrams_a = _extract_bigrams(clean_a)
    bigrams_b = _extract_bigrams(clean_b)

    # 核心：Jaccard 相似度 = 交集大小 / 并集大小
    score = _jaccard_similarity(bigrams_a, bigrams_b)

    # 收集重叠的 bigram 用于前端可视化（排序保证确定性，最多15个避免过长）
    overlapping = bigrams_a & bigrams_b
    overlap_list = sorted(overlapping)[:15] if overlapping else []

    # 截取文本摘要用于详情展示
    snippet_a = clean_a[:50] + ('...' if len(clean_a) > 50 else '')
    snippet_b = clean_b[:50] + ('...' if len(clean_b) > 50 else '')

    detail = {
        'overlapping_bigrams': overlap_list,
        'overlap_count': len(overlapping),
        'a_bigram_count': len(bigrams_a),
        'b_bigram_count': len(bigrams_b),
        'union_count': len(bigrams_a | bigrams_b),
        'text_a_snippet': snippet_a,
        'text_b_snippet': snippet_b,
    }
    return score, detail


# ============================================================================
# 匹配方法注册表 —— 新增方法在此注册
# ============================================================================
#
# 设计模式：策略模式（Strategy Pattern）+ 工厂模式（Factory Pattern）
#
# 每种方法的条目结构：
#   build_compute(dim_def)     → 工厂函数，接收 dim_def（维度定义），返回 compute 闭包
#                                闭包签名：compute(a_vals, o_vals, params) → (score, detail)
#   default_detail_type        → 前端渲染方式：'text'=纯文本 | 'bigram'=高亮重叠词 | 'vector'=向量详情
#   default_params             → 默认私有参数定义（无则为 {}），供前端动态生成 UI 控件
#   default_icon / default_color → 前端显示用的图标 emoji 和主题色
#
# 新增方法步骤：
#   1) 在此 METHOD_REGISTRY 中添加条目（指定 factory 函数和默认参数）
#   2) 实现对应的 _make_xxx_adapter(dim_def) 工厂函数（见下方）
#   3) 前端 add_dimension.js 的 _renderMethodParams() 中加对应的 UI 控件
# ============================================================================

def _make_string_match_adapter(dim_def):
    """
    为 string_match（字符串匹配）方法构建 compute 闭包。

    ══════════════════════════════════════════════════════════════════════
    闭包机制详解
    ══════════════════════════════════════════════════════════════════════

    本函数是一个工厂函数，它返回的 compute 是一个闭包（closure）。
    闭包会「捕获」外部的 ability_label 和 opp_label 变量，
    使得每次调用 compute 时无需再传入这些标签信息。

    闭包签名：
      compute(a_vals, o_vals, params) → tuple[score, detail]

    其中：
      - a_vals (list[str]): 从能力侧字段提取的值列表
                             如 ['人工智能（软件）', 'AI平台']（多字段时会有多个值）
      - o_vals (list[str]): 从机会侧字段提取的值列表
                             如 ['人工智能大模型应用...', '智能制造']
      - params (dict):     维度私有参数（string_match 不使用额外参数，始终为 {}）

    ══════════════════════════════════════════════════════════════════════
    多字段匹配策略
    ══════════════════════════════════════════════════════════════════════

    当维度配置了多个 ability_fields 或 opportunity_fields 时（如文本匹配同时看 overview 和 target_customer），
    compute 会遍历 a_vals × o_vals 的笛卡尔积，对每一对调用 _score_string_match，
    取最高分作为最终得分。

    这种「最佳对齐」策略确保了：只要任意一对字段能匹配上，该维度就有分。
    同时汇总所有命中组合的信息到详情中，方便用户理解匹配来源。
    """
    # 从 dim_def.method_labels 取中文标签（用于评分详情消息的人类可读展示）
    ability_label = (
        dim_def.get('method_labels', {})
        .get('ability', '能力值')
    )
    opp_label = (
        dim_def.get('method_labels', {})
        .get('opportunity', '机会值')
    )
    def compute(a_vals, o_vals, params):
        # 过滤空值：空字符串和纯空白字符串不参与匹配（无意义且可能引发异常）
        clean_a = [v for v in a_vals if v and v.strip()]
        clean_o = [v for v in o_vals if v and v.strip()]

        # 如果过滤后任一侧为空，仍然调用一次 _score_string_match 让它返回标准的"无有效信息"提示
        if not clean_a or not clean_o:
            return _score_string_match(
                clean_a[0] if clean_a else '',
                clean_o[0] if clean_o else '',
                ability_label=ability_label,
                opp_label=opp_label,
            )

        # 多字段笛卡尔积匹配：遍历所有 (ability_value, opportunity_value) 组合
        best_score = 0.0
        best_detail = ''
        hits = []   # 记录所有得分为正的匹配对，用于构建汇总信息

        for av in clean_a:
            for ov in clean_o:
                s, d = _score_string_match(
                    av, ov,
                    ability_label=ability_label,
                    opp_label=opp_label,
                )
                if s > 0:
                    hits.append((av, ov, s))  # 记录命中组：(能力值, 机会值得分)
                if s > best_score:
                    best_score = s
                    best_detail = d   # 始终保留最佳匹配的详情

        # 构建汇总详情：优先展示最佳匹配详情，若有多组命中则追加列表
        if hits:
            parts = [best_detail]
            if len(hits) > 1:
                # 多组命中时，列出所有匹配对及其得分
                hit_strs = [f'  - {a} <-> {o}（得分 {s:.3f}）' for a, o, s in hits]
                parts.append(f'多字段匹配命中 {len(hits)} 组：\n' + '\n'.join(hit_strs))
            return best_score, '\n'.join(parts)

        # 无任何匹配命中
        return best_score, best_detail or f'无匹配：（{ability_label}）vs（{opp_label}）未命中'

    return compute


def _make_bigram_adapter(dim_def):
    """
    为 bigram（中文 2-gram 文本相似度）方法构建 compute 闭包。

    与 string_match 的「逐对精确匹配」不同，bigram 采用「拼接后整体比较」策略：
    将能力侧所有字段值和机会侧所有字段值分别用空格拼成一段长文本，
    然后对这两段文本做中文 2-gram Jaccard 相似度计算。

    这种方式适合评估两段较长文本之间整体的主题相关性，
    对个别词汇差异不敏感（因为 Jaccard 只关心字符组合的重叠比例）。

    闭包签名：
      compute(a_vals, o_vals, params) → tuple[score, detail]

    参数说明（来自 dim_def.params）：
      - params['max_length']: 文本截取长度（默认 300）
                                 避免超长文本产生过多 bigram 导致相似度被稀释
    """
    def compute(a_vals, o_vals, params):
        max_len = params.get('max_length', 300)
        # 多字段值用空格拼接成一段连续文本
        # 例如：overview="提供AI解决方案" + target_customer="面向制造业企业"
        #     → "提供AI解决方案 面向制造业企业"
        return _score_text(
            ' '.join(a_vals),
            ' '.join(o_vals),
            max_len
        )
    return compute


def _make_vector_adapter(dim_def):
    """
    为 vector_semantic（向量语义匹配）方法构建 compute 闭包。

    ══════════════════════════════════════════════════════════════════════
    技术原理
    ══════════════════════════════════════════════════════════════════════

    1. 文本拼接：将用户选的能力侧/机会侧字段值拼成一段完整文本
    2. 向量编码：调用 SentenceTransformer 模型将文本转为高维稠密向量
    3. 相似度计算：由于向量已 L2 归一化，点积 ≈ 余弦相似度
    4. 阈值过滤：低于 threshold 的匹配按 0 分处理（过滤噪声）

    与 string_match/bigram 的区别：
      - string_match/bigram 基于「表面形式」（字面是否相同）
      - vector_semantic 基于「语义含义」（意思是否相近）
      - 例如："深度学习算法" 和 "神经网络模型" 字面不同但语义相近，
        vector_semantic 能识别出它们的关联性

    ══════════════════════════════════════════════════════════════════════
    闭包参数（来自 dim_def.params）
    ══════════════════════════════════════════════════════════════════════

      model_name (str):   嵌入模型标识名
                           推荐：'BAAI/bge-small-zh-v1.5' (~95MB，速度快)
                           精准：'BAAI/bge-large-zh-v1.5' (~326MB，精度高)
      threshold  (float): 最低相似度阈值（默认 0.0）
                           低于此值的匹配直接得 0 分，用于过滤弱相关噪声

    ══════════════════════════════════════════════════════════════════════
    返回格式
    ══════════════════════════════════════════════════════════════════════

      detail 字典包含：
        similarity    (float): 实际余弦相似度值
        threshold     (float): 配置的最低阈值
        text_a_snippet (str):  能力侧文本摘要（前100字符）
        text_b_snippet (str):  机会侧文本摘要（前100字符）
        reason        (str):   结果原因说明（低于阈值/正常匹配/字段为空）
    """
    from .vector_tool import encode  # 懒 import，避免 torch 在启动时被导入（加速冷启动）

    def compute(a_vals, o_vals, params):
        # 读取维度私有参数（防御 json null → Python None 的情况）
        model_name = params.get('model_name') or 'BAAI/bge-small-zh-v1.5'
        threshold  = float(params.get('threshold', 0.0))

        # 将多字段值拼成一段文本（中间用空格分隔，保持语义完整性）
        text_a = ' '.join(str(v) for v in a_vals if v).strip()
        text_b = ' '.join(str(v) for v in o_vals if v).strip()

        # 任一文本为空 → 无法计算语义相似度（没有内容可供编码）
        if not text_a or not text_b:
            return 0.0, {
                'similarity': 0.0,
                'threshold': threshold,
                'text_a_snippet': text_a[:100] + ('...' if len(text_a) > 100 else ''),
                'text_b_snippet': text_b[:100] + ('...' if len(text_b) > 100 else ''),
                'reason': '一侧或多侧字段值为空，无法计算语义相似度',
            }

        # 调用共享向量工具层（vector_tool.py）：文本 → 归一化向量
        vec_a = encode(model_name, text_a)
        vec_b = encode(model_name, text_b)

        # 向量已在 encode() 中做了 L2 归一化（normalize_embeddings=True）
        # 因此点积(dot product)数学上等价于余弦相似度(cosine similarity)
        # 理论范围 [-1, 1]，但语义嵌入模型的实际输出通常 ≥ 0
        sim = round(float(np.dot(vec_a, vec_b)), 4)

        # 构建详情信息
        detail = {
            'similarity': sim,
            'threshold': threshold,
            'text_a_snippet': text_a[:100] + ('...' if len(text_a) > 100 else ''),
            'text_b_snippet': text_b[:100] + ('...' if len(text_b) > 100 else ''),
        }

        # 阈值过滤：低于设定阈值的匹配按 0 分处理（相当于噪声过滤）
        if sim < threshold:
            detail['reason'] = (
                f'余弦相似度 {sim:.3f} 低于最低阈值 {threshold}，按 0 分处理'
            )
            return 0.0, detail

        detail['reason'] = f'余弦相似度 = {sim:.3f}'
        return max(0.0, sim), detail  # 安全兜底：负数也截断为 0

    return compute


# 方法注册表（新增匹配方法在此添加条目）
# 这是整个可插拔架构的核心数据结构——引擎通过查找这个表来决定如何创建评分函数
METHOD_REGISTRY = {
    # ── 字符串匹配方法 ──
    # 适用：精确关键词匹配场景，如领域名称匹配、区域名称匹配
    # 特点：结果确定性强（要么命中要么没命中），适合需要精确控制的维度
    'string_match': {
        'build_compute': _make_string_match_adapter,    # 工厂函数引用
        'default_detail_type': 'text',                   # 前端用纯文本渲染详情
        'default_params': {},                            # 无需额外参数
        'default_icon': '\U0001f50d',                     # 🔍 图标
        'default_color': '#3B82F6',                      # 蓝色主题色（Tailwind blue-500）
    },
    # ── Bigram 文本相似度方法 ──
    # 适用：长文本粗粒度比较，如能力概述 vs 机会概述的整体相关性
    # 特点：基于字符组合的重叠比例，对同义词不敏感但计算极快（无需模型推理）
    'bigram': {
        'build_compute': _make_bigram_adapter,
        'default_detail_type': 'bigram',                 # 前端高亮展示重叠的 bigram 词
        'default_params': {
            'max_length': {
                'default': 300,                           # 默认截取300个中文字符
                'label': '文本截取长度',
                'hint': '文本匹配时截取前 N 个中文字符，'
                        '避免超长文本稀释相似度。',
                'type': 'int',                            # 前端控件类型：整数输入框
                'min': 50,                                # 最小值
                'max': 2000,                              # 最大值
                'step': 10,                               # 步进值
                'slider_max': 2000,                       # 滑块最大值
            }
        },
        'default_icon': '\U0001f4d0',                     # 📐 图标
        'default_color': '#22C55E',                      # 绿色主题色（Tailwind green-500）
    },
    # ── 向量语义匹配方法 ──
    # 适用：需要理解语义而非字面的场景，如"深度学习"vs"神经网络"
    # 特点：依赖预训练嵌入模型，首次使用需下载模型，但能捕捉深层语义关联
    'vector_semantic': {
        'build_compute': _make_vector_adapter,
        'default_detail_type': 'vector',                 # 前端展示向量相似度数值和阈值
        'default_params': {
            'model_name': {
                'default': 'BAAI/bge-small-zh-v1.5',     # 默认使用小模型（95MB，快速）
                'label': '嵌入模型',
                'hint': '文本→向量的语义模型。'
                        'small=95MB/快速, large=326MB/精准。'
                        '首次使用自动下载。',
                'type': 'select',                         # 前端控件类型：下拉选择框
                'options': [
                    'BAAI/bge-small-zh-v1.5',             # 轻量级中文嵌入模型
                    'BAAI/bge-large-zh-v1.5',             # 高精度中文嵌入模型
                ],
            },
            'threshold': {
                'default': 0.0,                           # 默认不过滤（全部保留）
                'label': '最低相似度阈值',
                'hint': '低于此值的匹配直接得 0 分。'
                        '0.0 表示不过滤。',
                'type': 'float',                          # 前端控件类型：浮点数输入框
                'min': 0.0,
                'max': 1.0,
                'step': 0.05,
            },
        },
        'default_icon': '\U0001f9e0',                     # 🧠 图标
        'default_color': '#8B5CF6',                      # 紫色主题色（Tailwind violet-500）
    },
}


# ============================================================================
# 种子维度（默认维度配置，dimensions.json 不存在时写入此数据）
# ============================================================================
#
# 这些是系统出厂时的三个默认匹配维度，覆盖了最常见的三种匹配场景：
#   1. domain  (领域匹配)  → 精确/近似字符串匹配 → 权重最高(0.4)→ 决定性因素
#   2. text    (文本匹配)  → bigram 文本相似度    → 权重中等(0.3) → 参考因素
#   3. region  (区域匹配)  → 精确字符串匹配       → 权重中等(0.3) → 地域限制因素
#
# 用户可通过 API 动态增删维度，新维度会追加到此列表之后并持久化

DEFAULT_DIMENSIONS = [
    {
        # ────────────────────────────────────────────────────────────────
        # 领域匹配维度 —— 最关键的匹配维度，决定能力和机会是否属于同一行业
        # ────────────────────────────────────────────────────────────────
        'id': 'domain',
        'label': '领域匹配',
        'weight_key': 'domain_weight',                     # config.json 中的权重键名
        'ability_fields': ['domain'],                      # 取能力的 domain 字段
        'opportunity_fields': ['welcome'],                 # 取机会的 welcome（欢迎合作方向）字段
        'method': 'string_match',                          # 使用精确/近似字符串匹配
        'method_labels': {                                 # 评分详情中的中文标签
            'ability': '能力领域',
            'opportunity': '欢迎合作方向',
        },
        'default_weight': 0.4,                             # 最高权重（40%）
        'detail_type': 'text',
        'icon': '\U0001f50d',                              # 🔍
        'score_label': '领域',
        'color': '#3B82F6',
        'params': {},                                      # string_match 无需参数
        'focus_description': '关注场景能力所属产业领域与场景机会欢迎合作方向之间的关联度。',
    },
    {
        # ────────────────────────────────────────────────────────────────
        # 文本匹配维度 —— 评估能力和机会在文字描述层面的整体相关性
        # ────────────────────────────────────────────────────────────────
        'id': 'text',
        'label': '文本匹配',
        'weight_key': 'text_weight',
        # 同时考察两个字段：能力概述(overview)+意向客户(target_customer)
        # 这样可以从产品介绍和目标客户两个层面评估文本相关性
        'ability_fields': ['overview', 'target_customer'],
        # 机会侧同样考察概述和合作方向两个字段
        'opportunity_fields': ['overview', 'welcome'],
        'method': 'bigram',                                # 使用中文 2-gram Jaccard 相似度
        'default_weight': 0.3,
        'detail_type': 'bigram',
        'icon': '\U0001f4d0',                              # 📐
        'score_label': '文本',
        'color': '#22C55E',
        'params': {
            'max_length': {                                # bigram 方法的私有参数
                'default': 300,
                'label': '文本截取长度',
                'hint': '文本匹配时截取前 N 个中文字符，'
                        '避免超长文本稀释相似度。',
                'type': 'int',
                'min': 50,
                'max': 2000,
                'step': 10,
                'slider_max': 2000,
            }
        },
        'focus_description': '关注能力概述/意向客户与机会概述/合作方向在关键词层面的文本重叠度。',
    },
    {
        # ────────────────────────────────────────────────────────────────
        # 区域匹配维度 —— 评估地理位置上的匹配程度（本地偏好/政策要求等）
        # ────────────────────────────────────────────────────────────────
        'id': 'region',
        'label': '区域匹配',
        'weight_key': 'region_weight',
        'ability_fields': ['district'],                    # 能力的所属区字段
        'opportunity_fields': ['area'],                    # 机会的所属区域字段
        'method': 'string_match',                          # 区域名通常是精确匹配
        'method_labels': {
            'ability': '能力所属区',
            'opportunity': '机会所属区域',
        },
        'default_weight': 0.3,
        'detail_type': 'text',
        'icon': '\U0001f4cd',                              # 📍
        'score_label': '区域',
        'color': '#F59E0B',                               # 琥珀色（Tailwind amber-500）
        'params': {},
        'focus_description': '关注场景能力提供方所在区域与场景机会需求方所在区域的地理位置匹配度。',
    },
]


# ============================================================================
# 维度持久化路径
# ============================================================================

# 维度定义文件的绝对路径（相对于本模块所在目录的上级目录下的"后台数据"文件夹）
_DIMENSIONS_FILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '后台数据', 'dimensions.json'
))


# ============================================================================
# 运行时维度列表（含 compute 函数，由 _load_dimensions 构建）
# ============================================================================
# 全局变量 DIMENSIONS 是整个匹配系统的核心数据结构：
#   - 引擎（engine.py）遍历此列表来决定如何评分
#   - API 层（app.py）读写此列表来增删维度
#   - 每个元素是一个完整的 dict，包含 JSON 定义 + 运行时附加的 compute 闭包
#   - 注意：compute 闭包不可 JSON 序列化，持久化时需先剥离

DIMENSIONS = []  # 运行时列表，模块加载时由 _load_dimensions() 初始化填充


def _build_compute(dim_def):
    """
    根据 dim_def['method'] 从 METHOD_REGISTRY 构建对应的 compute 闭包。

    这是「工厂方法」的核心调度函数。它根据维度定义中指定的 method 名称，
    从注册表中查找对应的 build_compute 工厂函数并调用之。

    参数:
        dim_def (dict): 维度定义字典（必须包含 'method' 键）

    返回:
        callable|None: 成功则返回 compute 闭包（签名为 compute(a_vals, o_vals, params)），
                        如果 method 未在 METHOD_REGISTRY 中注册则返回 None
    """
    method = dim_def.get('method', 'string_match')  # 默认回退到字符串匹配
    if method not in METHOD_REGISTRY:
        return None
    # 调用对应方法的工厂函数，传入完整的维度定义（工厂内部会读取需要的字段）
    return METHOD_REGISTRY[method]['build_compute'](dim_def)


def _dim_def_to_runtime(dim_def):
    """
    将 JSON 持久化格式转换为运行时格式。

    关键区别：JSON 文件中只存储纯数据（不含函数），
    而运行时需要在每个维度上附加上 compute 闭包才能参与匹配计算。

    转换过程：
      输入：{'id':'domain', 'method':'string_match', ...}  ← 来自 JSON
      输出：{'id':'domain', 'method':'string_match', ..., 'compute': <closure>}  ← 运行时

    参数:
        dim_def (dict): 来自 JSON 文件的纯数据字典

    返回:
        dict: 附带 compute 闭包的运行时维度对象
    """
    rt = dict(dim_def)           # 浅拷贝，避免修改原字典
    rt['compute'] = _build_compute(dim_def)  # 关键：附加上 compute 闭包
    return rt


def _runtime_to_dim_def(rt):
    """
    将运行时格式转换回可 JSON 序列化的纯数据字典。

    与 _dim_def_to_runtime 互为逆操作。核心目的是剥离不可序列化的 compute 闭包，
    使维度定义可以安全地写入 JSON 文件。

    参数:
        rt (dict): 运行时维度对象（包含 compute 闭包）

    返回:
        dict: 纯数据字典（不含 compute 键，可直接 json.dump）
    """
    # 字典推导式过滤掉 compute 键（它是函数/closure，不能 JSON 序列化）
    d = {k: v for k, v in rt.items() if k != 'compute'}
    return d


# 公开版本（供 app.py 等外部模块直接调用）
def dim_def_to_runtime(dim_def):
    """_dim_def_to_runtime 的公开封装版本。"""
    return _dim_def_to_runtime(dim_def)


def runtime_to_dim_def(rt):
    """_runtime_to_dim_def 的公开封装版本。"""
    return _runtime_to_dim_def(rt)


def _load_dimensions():
    """
    从 dimensions.json 加载维度列表到全局变量 DIMENSIONS。

    ══════════════════════════════════════════════════════════════════════
    加载流程
    ══════════════════════════════════════════════════════════════════════

      情况A：文件不存在
        → 使用 DEFAULT_DIMENSIONS 种子数据初始化
        → 自动调用 _save_dimensions() 创建文件
        → 适用于首次启动或文件被删除的场景

      情况B：文件存在且合法
        → 解析 JSON 为 Python list
        → 对每个元素调用 _dim_def_to_runtime() 附加 compute 闭包
        → 赋值给全局 DIMENSIONS

      情况C：文件存在但解析失败（JSON 格式错误等）
        → 捕获异常，降级使用 DEFAULT_DIMENSIONS
        → 保证系统不会因配置文件损坏而无法启动

    注意：本函数在模块底部被自动调用（_load_dimensions()），
    确保 DIMENSIONS 在任何 import 此模块的代码执行前就已就绪。
    """
    global DIMENSIONS  # 声明修改全局变量

    if not os.path.exists(_DIMENSIONS_FILE):
        print('[dimensions] 未找到维度文件，使用默认维度初始化')
        # 首次运行：用种子数据初始化，并为每个种子维度构建 compute 闭包
        DIMENSIONS = [
            _dim_def_to_runtime(d)
            for d in DEFAULT_DIMENSIONS
        ]
        _save_dimensions()  # 自动创建 dimensions.json 文件
        return

    try:
        # 正常情况：从文件读取并解析 JSON
        with open(_DIMENSIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        DIMENSIONS = [
            _dim_def_to_runtime(d)
            for d in data
        ]
        print(f'[dimensions] 已从 {_DIMENSIONS_FILE} 加载 '
              f'{len(DIMENSIONS)} 个维度')
    except Exception as e:
        # 异常降级：配置文件损坏时使用默认配置，保证系统可用性
        print(f'[dimensions] 加载维度文件失败: {e}，使用默认维度')
        DIMENSIONS = [
            _dim_def_to_runtime(d)
            for d in DEFAULT_DIMENSIONS
        ]


def _save_dimensions():
    """
    将当前 DIMENSIONS 全局列表持久化写入 dimensions.json。

    写入前的关键操作：
      1. 对每个运行时维度调用 _runtime_to_dim_def() 剥离 compute 闭包
      2. ensure_ascii=False 保证中文字符以原生 UTF-8 存储（非 \\uXXXX 转义）

    目录处理：自动创建父目录（如果"后台数据"文件夹不存在的话）。
    异常保护：捕获 IO 异常并打印日志，不会因为写失败而崩溃。
    """
    try:
        os.makedirs(os.path.dirname(_DIMENSIONS_FILE), exist_ok=True)
        with open(_DIMENSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(
                [_runtime_to_dim_def(d) for d in DIMENSIONS],  # 先剥离 compute
                f, ensure_ascii=False, indent=2                  # 中文不转义 + 缩进美化
            )
        print(f'[dimensions] 已保存 {len(DIMENSIONS)} 个维度到 '
              f'{_DIMENSIONS_FILE}')
    except Exception as e:
        print(f'[dimensions] 保存维度文件失败: {e}')


# 模块加载时立即执行初始化（Python 的 import 机制保证此语句只执行一次）
_load_dimensions()


# ============================================================================
# 公共查询接口 —— 供 engine.py、app.py 等外部模块读取维度数据
# ============================================================================

def get_dimensions():
    """
    返回维度注册表的浅拷贝副本。

    返回副本而非原始引用是为了防止外部代码意外修改 DIMENSIONS 全局列表。
    外部对返回值的修改不会影响内部的 DIMENSIONS。

    返回:
        list[dict]: 当前所有维度的运行时副本（每个元素含 compute 闭包）
    """
    return list(DIMENSIONS)


def get_dimension_by_id(dim_id):
    """
    按维度 ID 查找单个维度定义。

    参数:
        dim_id (str): 维度唯一标识符，如 'domain'、'text'、'region' 或自定义的 'dim_1'

    返回:
        dict|None: 找到返回运行时维度对象（含 compute），未找到返回 None
    """
    for d in DIMENSIONS:
        if d['id'] == dim_id:
            return d
    return None


def get_dimension_by_weight_key(weight_key):
    """
    按 weight_key（配置文件中的权重键名）查找维度。

    weight_key 的命名规则：'{dim_id}_weight'，例如 'domain_weight'、'text_weight'。
    engine.py 通过 weight_key 来读取 config.json 中的权重值。

    参数:
        weight_key (str): 权重键名

    返回:
        dict|None: 找到返回运行时维度对象，未找到返回 None
    """
    for d in DIMENSIONS:
        if d['weight_key'] == weight_key:
            return d
    return None


def get_weight_keys():
    """
    返回当前所有维度的 weight_key 列表。

    engine.py 用此列表来知道 config.json 中应该有哪些权重配置项。
    当维度增删时，此列表也会相应变化，从而驱动 config 的同步更新。

    返回:
        list[str]: 所有维度的 weight_key 字符串列表
    """
    return [d['weight_key'] for d in DIMENSIONS]


def get_next_dim_id():
    """
    自动为新维度生成唯一的 ID。

    命名规则：'dim_N'，其中 N 是现有 dim_* 类型 ID 中的最大数字 + 1。
    例如已有 dim_1, dim_3 → 下一个是 dim_4（跳过空洞，只看最大值）。

    对于内置维度（domain/text/region），它们的 ID 不是 dim_* 前缀，
    所以不会被此函数影响。

    返回:
        str: 新维度 ID，如 'dim_1'、'dim_4'
    """
    max_n = 0
    for d in DIMENSIONS:
        dim_id = d.get('id', '')
        if not dim_id:
            continue
        # 只处理 dim_ 前缀的自定义维度 ID
        if dim_id.startswith('dim_'):
            try:
                n = int(dim_id[4:])  # 提取数字部分
                max_n = max(max_n, n)
            except ValueError:
                pass  # 非法格式（如 dim_abc）跳过
    return f'dim_{max_n + 1}'


# ============================================================================
# 维度增删接口 —— 供 app.py 的 RESTful API 调用以动态管理维度
# ============================================================================

def add_dimension(dim_def):
    """
    添加一个新的匹配维度到系统中。

    ══════════════════════════════════════════════════════════════════════
    处理流程（7步流水线）
    ══════════════════════════════════════════════════════════════════════

      Step 1 — ID 处理
        若用户未传 id 则自动生成 dim_N 格式的 ID；
        若传了 id 则校验唯一性，重复则拒绝。

      Step 2 — Weight Key 生成
        若用户未指定 weight_key，则自动生成为 '{id}_weight' 格式。
        这是 config.json 中存储该维度权重的键名。

      Step 3 — Method 校验
        检查 method 是否在 METHOD_REGISTRY 中注册。未注册的方法会导致
        无法构建 compute 闭包，因此直接拒绝。

      Step 4 — 默认值填充
        从 METHOD_REGISTRY[method] 中取出该方法的默认配置，
        包括 detail_type、icon、color、params 等。
        用户显式传入的值不会被默认值覆盖（setdefault 语义）。

      Step 5 — 字段兼容性转换
        前端可能传单个字符串而非列表（如 ability_fields: "domain"），
        这里统一转为列表格式以保证后续代码的一致性。

      Step 6 — 运行时对象构建与注册
        调用 _dim_def_to_runtime() 附加上 compute 闭包，
        然后追加到全局 DIMENSIONS 列表末尾。

      Step 7 — 持久化与返回
        调用 _save_dimensions() 写入 JSON 文件；
        返回时可序列化的版本（去掉 compute 闭包）。

    ══════════════════════════════════════════════════════════════════════
    参数
    ══════════════════════════════════════════════════════════════════════

      dim_def (dict): 前端提交的新维度定义（JSON 格式，不含 compute）
                      至少应包含：method, label, ability_fields, opportunity_fields
                      可选包含：id, weight_key, method_labels 等

    ══════════════════════════════════════════════════════════════════════
    返回
    ══════════════════════════════════════════════════════════════════════

      tuple[bool, str, dict|None]:
        - success (bool): True 表示添加成功，False 表示失败
        - msg     (str):  人可读的结果消息（成功时含维度名，失败时含原因）
        - dim     (dict|None): 成功时返回新维度的可序列化字典，失败时为 None
    """
    global DIMENSIONS

    # ---- Step 1) ID 处理：用户没传则自动生成 dim_N ----
    dim_id = dim_def.get('id', '').strip()
    if not dim_id:
        dim_id = get_next_dim_id()
        dim_def['id'] = dim_id       # 写回原字典，后续持久化时需要用到
    # 唯一性校验：ID 不能重复
    if get_dimension_by_id(dim_id):
        return False, f'维度 ID「{dim_id}」已存在', None

    # ---- Step 2) weight_key 自动生成 ----
    # 格式约定：{dim_id}_weight，这样 engine.py 可以通过 dim_id 反推出权重键
    if 'weight_key' not in dim_def:
        dim_def['weight_key'] = f'{dim_id}_weight'

    # ---- Step 3) method 合法性校验 ----
    # 必须是 METHOD_REGISTRY 中已注册的方法名，否则无法构建 compute 闭包
    method = dim_def.get('method', 'string_match')
    if method not in METHOD_REGISTRY:
        return False, f'未知匹配方法：{method}', None

    # ---- Step 4) 从 METHOD_REGISTRY 填充该方法专属的默认值 ----
    # setdefault 仅在键不存在时设置，用户显式传入的值具有更高优先级
    reg = METHOD_REGISTRY[method]
    dim_def.setdefault('detail_type', reg['default_detail_type'])
    dim_def.setdefault('icon', reg['default_icon'])
    dim_def.setdefault('color', reg['default_color'])
    dim_def.setdefault('default_weight', 0.0)           # 新增维度默认权重 0（不影响现有总分分布）
    dim_def.setdefault('score_label', dim_def.get('label', dim_id))  # 默认用 label 作为得分列标题
    dim_def.setdefault('params', reg['default_params'])  # 方法的默认参数模板

    # ---- Step 5) 字段兼容性转换：字符串 → 列表 ----
    # 前端 JavaScript 可能传单个字符串而非数组（特别是只有一个字段时）
    # 这里统一转为列表格式，保证后续迭代代码的一致性
    if isinstance(dim_def.get('ability_fields'), str):
        dim_def['ability_fields'] = [dim_def['ability_fields']]
    if isinstance(dim_def.get('opportunity_fields'), str):
        dim_def['opportunity_fields'] = [dim_def['opportunity_fields']]
    # 最终保底：即使什么都没传也有空列表（避免 KeyError）
    dim_def.setdefault('ability_fields', [])
    dim_def.setdefault('opportunity_fields', [])

    # ---- Step 6) 构建运行时格式并追加到全局列表 ----
    rt = _dim_def_to_runtime(dim_def)  # 附加上 compute 闭包
    DIMENSIONS.append(rt)
    _save_dimensions()   # 立即持久化到 dimensions.json

    # ---- Step 7) 返回可序列化版本（不含 compute 函数，方便 JSON 响应） ----
    return True, f'维度「{dim_def["label"]}」已添加', _runtime_to_dim_def(rt)


def delete_dimension(dim_id):
    """
    删除指定 ID 的维度。

    安全约束：
      - 至少保留 1 个维度（全删掉会导致匹配引擎无维度可计算）
      - ID 不存在时返回错误信息

    删除后的联动效果：
      - DIMENSIONS 列表中移除该元素
      - dimensions.json 文件同步更新
      - engine.py 的 sync_config_with_dimensions() 会清理对应的配置项

    参数:
        dim_id (str): 要删除的维度 ID

    返回:
        tuple[bool, str]:
            - success (bool): True 表示删除成功
            - msg     (str):  人可读的消息（成功时含维度名，失败时含原因）
    """
    global DIMENSIONS

    # 安全底线：至少保留 1 个匹配维度
    if len(DIMENSIONS) <= 1:
        return False, '至少保留 1 个匹配维度，删除失败'

    # 线性搜索定位目标维度的索引
    idx = None
    for i, d in enumerate(DIMENSIONS):
        if d['id'] == dim_id:
            idx = i
            break

    if idx is None:
        return False, f'维度 ID「{dim_id}」不存在'

    # 记录被删除维度的标签用于友好消息
    label = DIMENSIONS[idx].get('label', dim_id)
    del DIMENSIONS[idx]      # 从列表中移除
    _save_dimensions()       # 同步持久化

    return True, f'维度「{label}」已删除'


def update_dimension_weight(dim_id, new_weight):
    """
    更新指定维度的默认权重值。

    用途说明：
      本方法更新的是 DIMENSIONS 中各维度的 default_weight 字段，
      它影响的是「重置默认值」时的初始权重。
      而用户在前端拖拽调整后的实际运行权重存储在 config.json 中（通过 MATCH_CONFIG 管理）。
      两者的关系：default_weight 是「出厂设置」，config 中的值是「用户当前设置」。

    参数:
        dim_id    (str):  目标维度 ID
        new_weight (float): 新的默认权重值（通常在 0.0 ~ 1.0 之间）

    返回:
        tuple[bool, str]:
            - success (bool): 更新是否成功
            - msg     (str):  人可读的消息
    """
    for d in DIMENSIONS:
        if d['id'] == dim_id:
            d['default_weight'] = new_weight
            _save_dimensions()  # 持久化变更
            return True, f'维度「{d["label"]}」默认权重已更新'
    return False, f'维度 ID「{dim_id}」不存在'
