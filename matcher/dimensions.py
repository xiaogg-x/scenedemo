# -*- coding: utf-8 -*-
"""
dimensions.py —— 匹配维度注册表（文件持久化版）

职责：
  1. 定义可用的匹配方法（字符串匹配 / bigram 文本匹配）
  2. 管理维度列表的加载、保存、增删
  3. 提供适配器工厂：根据 method 名称 + 字段定义生成 compute 闭包
  4. 维度定义持久化到 后台数据/dimensions.json
     文件不存在时，用 DEFAULT_DIMENSIONS 种子数据初始化

维度 JSON 格式（存文件用，不含 compute 函数）：
  {
    "id":               "domain",
    "label":            "领域匹配",
    "weight_key":       "domain_weight",
    "ability_fields":   ["domain"],
    "opportunity_fields": ["welcome"],
    "method":           "string_match",
    "method_labels":   {"ability": "能力领域", "opportunity": "欢迎合作方向"},
    "default_weight":   0.4,
    "detail_type":      "text",
    "icon":             "🔍",
    "score_label":      "领域",
    "color":            "#3B82F6",
    "params":           {}
  }

匹配方法注册表 METHOD_REGISTRY：
  "string_match"    → 精确子串 + 大类归一化（_score_string_match）
  "bigram"          → 中文 2-gram Jaccard 相似度（_score_text）
  "vector_semantic" → 语义向量嵌入 + 余弦相似度（_make_vector_adapter）
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
    """清洗文本：去除非中文字符，保留纯中文。"""
    if not text:
        return ''
    return re.sub(r'[^\u4e00-\u9fff]', '', text)


def _extract_bigrams(text):
    """
    从中文文本中提取 2-gram（bigram）字符集合。
    例如 "智慧交通" → {"智慧", "慧交", "交通"}
    """
    bigrams = set()
    for i in range(len(text) - 1):
        bigrams.add(text[i:i+2])
    return bigrams


def _jaccard_similarity(set_a, set_b):
    """计算 Jaccard 相似度 = |A∩B| / |A∪B|"""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    if len(union) == 0:
        return 0.0
    return len(intersection) / len(union)


# ============================================================================
# 核心评分函数
# ============================================================================

def _score_string_match(ability_val, opp_val,
                       ability_label='能力值', opp_label='机会值'):
    """
    通用字符串匹配得分（精确子串 + 大类归一化近似）。

    策略:
      1. 精确子串命中 → 1.0
      2. 大类归一化近似 → 0.5
      3. 未命中 → 0.0

    参数:
      ability_val  : 能力侧字段值
      opp_val      : 机会侧字段值（被搜索的文本）
      ability_label: 能力侧字段的中文标签（用于详情消息）
      opp_label    : 机会侧字段的中文标签（用于详情消息）

    返回: tuple[float, str]  (score, detail_text)
    """
    if not ability_val or not opp_val:
        return 0.0, (
            f'无有效信息可供匹配'
            f'（一侧{ability_label}或{opp_label}字段为空）'
        )

    # 策略1：精确子串匹配
    if ability_val in opp_val:
        idx = opp_val.find(ability_val)
        start = max(0, idx - 20)
        end = min(len(opp_val), idx + len(ability_val) + 20)
        context = opp_val[start:end].replace('\n', ' ').replace('\r', '')
        return 1.0, (
            f'精确命中（得分：1.0）\n'
            f'{ability_label}：「{ability_val}」\n'
            f'在机会「{opp_label}」字段中直接出现\n'
            f'匹配位置上下文：「…{context}…」'
        )

    # 策略2：大类归一化匹配
    big_cls_a = normalize_domain(ability_val)
    prefix = opp_val[:60] if len(opp_val) > 60 else opp_val

    for i in range(len(prefix)):
        for j in range(i + 2, min(i + 30, len(prefix) + 1)):
            candidate = prefix[i:j]
            cand_norm = normalize_domain(candidate)
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

    return 0.0, (
        f'未命中（得分：0.0）\n'
        f'{ability_label}：「{ability_val}」→ 大类「{big_cls_a}」\n'
        f'在机会「{opp_label}」前60字中未找到匹配项'
    )


def _score_text(text_a, text_b, max_len=300):
    """
    文本重叠度得分：中文 2-gram Jaccard 相似度。

    返回: tuple[float, dict]  (score, detail_dict)
    """
    clean_a = _clean_text(text_a)[:max_len]
    clean_b = _clean_text(text_b)[:max_len]

    bigrams_a = _extract_bigrams(clean_a)
    bigrams_b = _extract_bigrams(clean_b)
    score = _jaccard_similarity(bigrams_a, bigrams_b)

    overlapping = bigrams_a & bigrams_b
    overlap_list = sorted(overlapping)[:15] if overlapping else []

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
# 每种方法的条目结构：
#   build_compute(dim_def)     → 工厂函数，接收 dim_def，返回 compute 闭包
#   default_detail_type        → 前端渲染方式（'text' 或 'bigram'）
#   default_params             → 默认私有参数定义（无则为 {}）
#   default_icon / default_color → 前端显示用的图标和颜色
#
# 新增方法步骤：
#   1) 在此 METHOD_REGISTRY 中添加条目
#   2) 实现对应的 _make_xxx_adapter(dim_def) 工厂函数
#   3) 前端 add_dimension.js 的 _renderMethodParams() 中加对应的 UI
# ============================================================================

def _make_string_match_adapter(dim_def):
    """
    为 string_match 方法构建 compute 闭包。

    闭包签名：compute(a_vals, o_vals, params) → (score, detail)
      - a_vals: 从能力侧字段提取的值列表（如 ['人工智能（软件）', 'AI平台']）
      - o_vals: 从机会侧字段提取的值列表（如 ['人工智能大模型应用...', '智能制造']）
      - params:  维度私有参数字典（string_match 不使用，始终为 {}）

    支持多字段匹配策略：
      遍历 a_vals × o_vals 所有组合，对每一对调用 _score_string_match，
      取最高分作为最终得分。详情消息为所有命中组合的汇总。

    闭包内部会从 dim_def 中取出 method_labels 作为详情消息的标签，
    然后调用 _score_string_match 执行实际评分。
    """
    # 从 dim_def.method_labels 取中文标签（用于评分详情消息）
    ability_label = (
        dim_def.get('method_labels', {})
        .get('ability', '能力值')
    )
    opp_label = (
        dim_def.get('method_labels', {})
        .get('opportunity', '机会值')
    )
    def compute(a_vals, o_vals, params):
        # 过滤空值（空字符串不参与匹配）
        clean_a = [v for v in a_vals if v and v.strip()]
        clean_o = [v for v in o_vals if v and v.strip()]

        if not clean_a or not clean_o:
            return _score_string_match(
                clean_a[0] if clean_a else '',
                clean_o[0] if clean_o else '',
                ability_label=ability_label,
                opp_label=opp_label,
            )

        # 多字段：遍历所有组合取最佳匹配
        best_score = 0.0
        best_detail = ''
        hits = []

        for av in clean_a:
            for ov in clean_o:
                s, d = _score_string_match(
                    av, ov,
                    ability_label=ability_label,
                    opp_label=opp_label,
                )
                if s > 0:
                    hits.append((av, ov, s))
                if s > best_score:
                    best_score = s
                    best_detail = d

        # 构建汇总详情
        if hits:
            parts = [best_detail]
            if len(hits) > 1:
                hit_strs = [f'  - {a} <-> {o}（得分 {s:.3f}）' for a, o, s in hits]
                parts.append(f'多字段匹配命中 {len(hits)} 组：\n' + '\n'.join(hit_strs))
            return best_score, '\n'.join(parts)

        return best_score, best_detail or f'无匹配：（{ability_label}）vs（{opp_label}）未命中'

    return compute


def _make_bigram_adapter(dim_def):
    """
    为 bigram 方法构建 compute 闭包。

    bigram 方法支持多字段：将 ability_fields 和 opportunity_fields
    对应的所有字段值用空格拼接成一大段文本，然后调用 _score_text 做
    中文 2-gram Jaccard 相似度计算。

    闭包签名：compute(a_vals, o_vals, params) → (score, detail)
      - params['max_length']: 文本截取长度（默认 300，避免超长文本稀释相似度）
    """
    def compute(a_vals, o_vals, params):
        max_len = params.get('max_length', 300)
        # 多字段值用空格拼接（如 overview + target_customer 拼接）
        return _score_text(
            ' '.join(a_vals),
            ' '.join(o_vals),
            max_len
        )
    return compute


def _make_vector_adapter(dim_def):
    """
    为 vector_semantic 方法构建 compute 闭包。

    将用户选的能力侧/机会侧字段值拼成文本，用语义嵌入模型转为归一化向量，
    再以点积（等价于余弦相似度）计算语义相似度得分。

    参数（params）：
      - model_name (str):  嵌入模型名，如 'BAAI/bge-small-zh-v1.5'
      - threshold  (float): 最低相似度阈值，低于此值的匹配直接得 0 分

    闭包签名：compute(a_vals, o_vals, params) → (score, detail)
      - 返回的 detail 字典含 similarity、threshold、text_snippet、reason 字段
    """
    from .vector_tool import encode  # 懒 import，避免 torch 在启动时被导入

    def compute(a_vals, o_vals, params):
        # 读取维度私有参数（防御 json null → Python None 的情况）
        model_name = params.get('model_name') or 'BAAI/bge-small-zh-v1.5'
        threshold  = float(params.get('threshold', 0.0))

        # 将多字段值拼成一段文本（中间用空格分隔）
        text_a = ' '.join(str(v) for v in a_vals if v).strip()
        text_b = ' '.join(str(v) for v in o_vals if v).strip()

        # 任一文本为空 → 无法计算语义相似度
        if not text_a or not text_b:
            return 0.0, {
                'similarity': 0.0,
                'threshold': threshold,
                'text_a_snippet': text_a[:100] + ('...' if len(text_a) > 100 else ''),
                'text_b_snippet': text_b[:100] + ('...' if len(text_b) > 100 else ''),
                'reason': '一侧或多侧字段值为空，无法计算语义相似度',
            }

        # 调用共享向量工具层：文本 → 归一化向量
        vec_a = encode(model_name, text_a)
        vec_b = encode(model_name, text_b)

        # 向量已 L2 归一化，点积 = 余弦相似度，范围理论上 [-1, 1]
        # 实际中语义嵌入模型的相似度通常 ≥ 0
        sim = round(float(np.dot(vec_a, vec_b)), 4)

        # 构建详情
        detail = {
            'similarity': sim,
            'threshold': threshold,
            'text_a_snippet': text_a[:100] + ('...' if len(text_a) > 100 else ''),
            'text_b_snippet': text_b[:100] + ('...' if len(text_b) > 100 else ''),
        }

        # 低于阈值 → 按 0 分处理
        if sim < threshold:
            detail['reason'] = (
                f'余弦相似度 {sim:.3f} 低于最低阈值 {threshold}，按 0 分处理'
            )
            return 0.0, detail

        detail['reason'] = f'余弦相似度 = {sim:.3f}'
        return max(0.0, sim), detail  # 负数截断为 0

    return compute


# 方法注册表（新增匹配方法在此添加条目）
METHOD_REGISTRY = {
    'string_match': {
        'build_compute': _make_string_match_adapter,
        'default_detail_type': 'text',
        'default_params': {},
        'default_icon': '🔍',
        'default_color': '#3B82F6',
    },
    'bigram': {
        'build_compute': _make_bigram_adapter,
        'default_detail_type': 'bigram',
        'default_params': {
            'max_length': {
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
        'default_icon': '📐',
        'default_color': '#22C55E',
    },
    'vector_semantic': {
        'build_compute': _make_vector_adapter,
        'default_detail_type': 'vector',
        'default_params': {
            'model_name': {
                'default': 'BAAI/bge-small-zh-v1.5',
                'label': '嵌入模型',
                'hint': '文本→向量的语义模型。'
                        'small=95MB/快速, large=326MB/精准。'
                        '首次使用自动下载。',
                'type': 'select',
                'options': [
                    'BAAI/bge-small-zh-v1.5',
                    'BAAI/bge-large-zh-v1.5',
                ],
            },
            'threshold': {
                'default': 0.0,
                'label': '最低相似度阈值',
                'hint': '低于此值的匹配直接得 0 分。'
                        '0.0 表示不过滤。',
                'type': 'float',
                'min': 0.0,
                'max': 1.0,
                'step': 0.05,
            },
        },
        'default_icon': '🧠',
        'default_color': '#8B5CF6',
    },
}


# ============================================================================
# 种子维度（文件不存在时写入 dimensions.json）
# ============================================================================

DEFAULT_DIMENSIONS = [
    {
        'id': 'domain',
        'label': '领域匹配',
        'weight_key': 'domain_weight',
        'ability_fields': ['domain'],
        'opportunity_fields': ['welcome'],
        'method': 'string_match',
        'method_labels': {
            'ability': '能力领域',
            'opportunity': '欢迎合作方向',
        },
        'default_weight': 0.4,
        'detail_type': 'text',
        'icon': '🔍',
        'score_label': '领域',
        'color': '#3B82F6',
        'params': {},
    },
    {
        'id': 'text',
        'label': '文本匹配',
        'weight_key': 'text_weight',
        'ability_fields': ['overview', 'target_customer'],
        'opportunity_fields': ['overview', 'welcome'],
        'method': 'bigram',
        'default_weight': 0.3,
        'detail_type': 'bigram',
        'icon': '📐',
        'score_label': '文本',
        'color': '#22C55E',
        'params': {
            'max_length': {
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
    },
    {
        'id': 'region',
        'label': '区域匹配',
        'weight_key': 'region_weight',
        'ability_fields': ['district'],
        'opportunity_fields': ['area'],
        'method': 'string_match',
        'method_labels': {
            'ability': '能力所属区',
            'opportunity': '机会所属区域',
        },
        'default_weight': 0.3,
        'detail_type': 'text',
        'icon': '📍',
        'score_label': '区域',
        'color': '#F59E0B',
        'params': {},
    },
]


# ============================================================================
# 维度持久化路径
# ============================================================================

_DIMENSIONS_FILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '后台数据', 'dimensions.json'
))


# ============================================================================
# 运行时维度列表（含 compute 函数，由 _load_dimensions 构建）
# ============================================================================

DIMENSIONS = []  # 运行时列表，每个元素是完整 dict（含 compute 函数）


def _build_compute(dim_def):
    """
    根据 dim_def['method'] 从 METHOD_REGISTRY 构建 compute 闭包。
    如果 method 未注册，返回 None。
    """
    method = dim_def.get('method', 'string_match')
    if method not in METHOD_REGISTRY:
        return None
    return METHOD_REGISTRY[method]['build_compute'](dim_def)


def _dim_def_to_runtime(dim_def):
    """
    将 JSON 中的维度定义（不含 compute）转换为运行时格式（含 compute）。
    """
    rt = dict(dim_def)
    rt['compute'] = _build_compute(dim_def)
    return rt


def _runtime_to_dim_def(rt):
    """
    将运行时维度（含 compute）转换为可序列化的 dict（去除 compute）。
    """
    d = {k: v for k, v in rt.items() if k != 'compute'}
    return d


# 公开版本（供 app.py 等外部模块调用）
def dim_def_to_runtime(dim_def):
    """_dim_def_to_runtime 的公开版本。"""
    return _dim_def_to_runtime(dim_def)


def runtime_to_dim_def(rt):
    """_runtime_to_dim_def 的公开版本。"""
    return _runtime_to_dim_def(rt)


def _load_dimensions():
    """
    从 dimensions.json 加载维度列表到 DIMENSIONS 全局变量。
    文件不存在时用 DEFAULT_DIMENSIONS 初始化并写入文件。
    """
    global DIMENSIONS

    if not os.path.exists(_DIMENSIONS_FILE):
        print('[dimensions] 未找到维度文件，使用默认维度初始化')
        DIMENSIONS = [
            _dim_def_to_runtime(d)
            for d in DEFAULT_DIMENSIONS
        ]
        _save_dimensions()
        return

    try:
        with open(_DIMENSIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        DIMENSIONS = [
            _dim_def_to_runtime(d)
            for d in data
        ]
        print(f'[dimensions] 已从 {_DIMENSIONS_FILE} 加载 '
              f'{len(DIMENSIONS)} 个维度')
    except Exception as e:
        print(f'[dimensions] 加载维度文件失败: {e}，使用默认维度')
        DIMENSIONS = [
            _dim_def_to_runtime(d)
            for d in DEFAULT_DIMENSIONS
        ]


def _save_dimensions():
    """将 DIMENSIONS 持久化到 dimensions.json（去除 compute 函数）。"""
    try:
        os.makedirs(os.path.dirname(_DIMENSIONS_FILE), exist_ok=True)
        with open(_DIMENSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(
                [_runtime_to_dim_def(d) for d in DIMENSIONS],
                f, ensure_ascii=False, indent=2
            )
        print(f'[dimensions] 已保存 {len(DIMENSIONS)} 个维度到 '
              f'{_DIMENSIONS_FILE}')
    except Exception as e:
        print(f'[dimensions] 保存维度文件失败: {e}')


# 模块加载时立即初始化
_load_dimensions()


# ============================================================================
# 公共查询接口
# ============================================================================

def get_dimensions():
    """返回维度注册表的副本（防止外部意外修改）。"""
    return list(DIMENSIONS)


def get_dimension_by_id(dim_id):
    """按 ID 查找单个维度定义。"""
    for d in DIMENSIONS:
        if d['id'] == dim_id:
            return d
    return None


def get_dimension_by_weight_key(weight_key):
    """按 weight_key 查找单个维度定义。"""
    for d in DIMENSIONS:
        if d['weight_key'] == weight_key:
            return d
    return None


def get_weight_keys():
    """返回所有维度的权重配置 key 列表。"""
    return [d['weight_key'] for d in DIMENSIONS]


def get_next_dim_id():
    """自动生成新维度 ID：dim_N，N 为当前最大数字 +1。"""
    max_n = 0
    for d in DIMENSIONS:
        dim_id = d.get('id', '')
        if not dim_id:
            continue
        if dim_id.startswith('dim_'):
            try:
                n = int(dim_id[4:])
                max_n = max(max_n, n)
            except ValueError:
                pass
    return f'dim_{max_n + 1}'


# ============================================================================
# 维度增删接口（供 app.py API 调用）
# ============================================================================

def add_dimension(dim_def):
    """
    添加一个新维度。

    处理流程：
      1) 自动生成/校验 id（不重复）
      2) 自动生成 weight_key（格式：{id}_weight）
      3) 校验 method 在 METHOD_REGISTRY 中
      4) 从 METHOD_REGISTRY 填充默认值（detail_type, icon, color, params 等）
      5) ability_fields / opportunity_fields 字符串→列表兼容转换
      6) _dim_def_to_runtime() 构建含 compute 闭包的运行时对象
      7) 追加到 DIMENSIONS 全局列表 + 持久化 JSON

    dim_def 是 JSON 格式的 dict（不含 compute）。
    返回：(success: bool, msg: str, dim: dict|None)
    """
    global DIMENSIONS

    # ---- 1) id 处理：用户没传则自动生成 dim_N ----
    dim_id = dim_def.get('id', '').strip()
    if not dim_id:
        dim_id = get_next_dim_id()
        dim_def['id'] = dim_id       # 写回，后续持久化时需要
    if get_dimension_by_id(dim_id):
        return False, f'维度 ID「{dim_id}」已存在', None

    # ---- 2) weight_key 生成 ----
    if 'weight_key' not in dim_def:
        dim_def['weight_key'] = f'{dim_id}_weight'

    # ---- 3) method 校验 ----
    method = dim_def.get('method', 'string_match')
    if method not in METHOD_REGISTRY:
        return False, f'未知匹配方法：{method}', None

    # ---- 4) 从 METHOD_REGISTRY 填充该方法专属的默认值 ----
    reg = METHOD_REGISTRY[method]
    dim_def.setdefault('detail_type', reg['default_detail_type'])
    dim_def.setdefault('icon', reg['default_icon'])
    dim_def.setdefault('color', reg['default_color'])
    dim_def.setdefault('default_weight', 0.0)           # 新增维度默认权重 0（不抢分）
    dim_def.setdefault('score_label', dim_def.get('label', dim_id))
    dim_def.setdefault('params', reg['default_params'])

    # ---- 5) ability_fields / opportunity_fields 字符串→列表兼容 ----
    # 前端可能传单个字符串而非列表，这里做兼容处理
    if isinstance(dim_def.get('ability_fields'), str):
        dim_def['ability_fields'] = [dim_def['ability_fields']]
    if isinstance(dim_def.get('opportunity_fields'), str):
        dim_def['opportunity_fields'] = [dim_def['opportunity_fields']]
    dim_def.setdefault('ability_fields', [])
    dim_def.setdefault('opportunity_fields', [])

    # ---- 6) 构建运行时格式（含 compute 闭包）并追加到全局列表 ----
    rt = _dim_def_to_runtime(dim_def)
    DIMENSIONS.append(rt)
    _save_dimensions()   # 持久化到 dimensions.json

    # ---- 7) 返回可序列化版本（不含 compute 函数） ----
    return True, f'维度「{dim_def["label"]}」已添加', _runtime_to_dim_def(rt)


def delete_dimension(dim_id):
    """
    删除指定 ID 的维度。
    至少保留 1 个维度。
    返回：(success: bool, msg: str)
    """
    global DIMENSIONS

    if len(DIMENSIONS) <= 1:
        return False, '至少保留 1 个匹配维度，删除失败'

    idx = None
    for i, d in enumerate(DIMENSIONS):
        if d['id'] == dim_id:
            idx = i
            break

    if idx is None:
        return False, f'维度 ID「{dim_id}」不存在'

    label = DIMENSIONS[idx].get('label', dim_id)
    del DIMENSIONS[idx]
    _save_dimensions()

    return True, f'维度「{label}」已删除'


def update_dimension_weight(dim_id, new_weight):
    """
    更新指定维度的默认权重（供前端拖拽后持久化）。
    注意：权重 key 对应的值存在 config.json 中，此方法更新的是
    DIMENSIONS 中的 default_weight（仅影响重置默认值）。
    返回：(success: bool, msg: str)
    """
    for d in DIMENSIONS:
        if d['id'] == dim_id:
            d['default_weight'] = new_weight
            _save_dimensions()
            return True, f'维度「{d["label"]}」默认权重已更新'
    return False, f'维度 ID「{dim_id}」不存在'
