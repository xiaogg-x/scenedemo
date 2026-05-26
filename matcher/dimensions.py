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
  "string_match"  → 精确子串 + 大类归一化（_score_string_match）
  "bigram"        → 中文 2-gram Jaccard 相似度（_score_text）
"""

import re
import json
import os

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
# 每种方法需要定义：
#   build_compute(dim_def) → compute 闭包
#   default_detail_type       → 前端渲染方式
#   default_params           → 默认私有参数（无则为 {}）
# ============================================================================

def _make_string_match_adapter(dim_def):
    """
    为 string_match 方法构建 compute 闭包。
    dim_def['method_labels'] 提供 ability_label / opportunity_label。
    """
    ability_label = (
        dim_def.get('method_labels', {})
        .get('ability', '能力值')
    )
    opp_label = (
        dim_def.get('method_labels', {})
        .get('opportunity', '机会值')
    )
    def compute(a_vals, o_vals, params):
        return _score_string_match(
            a_vals[0] if a_vals else '',
            o_vals[0] if o_vals else '',
            ability_label=ability_label,
            opp_label=opp_label,
        )
    return compute


def _make_bigram_adapter(dim_def):
    """
    为 bigram 方法构建 compute 闭包。
    使用 dim_def['ability_fields'] / opportunity_fields 拼接文本。
    """
    def compute(a_vals, o_vals, params):
        max_len = params.get('max_length', 300)
        return _score_text(
            ' '.join(a_vals),
            ' '.join(o_vals),
            max_len
        )
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
    dim_def 是 JSON 格式的 dict（不含 compute）。
    自动生成 id / weight_key（如果未提供）。
    返回：(success: bool, msg: str, dim: dict|None)
    """
    global DIMENSIONS

    # 检查 id 冲突（自动生成则写回 dim_def）
    dim_id = dim_def.get('id', '').strip()
    if not dim_id:
        dim_id = get_next_dim_id()
        dim_def['id'] = dim_id
    if get_dimension_by_id(dim_id):
        return False, f'维度 ID「{dim_id}」已存在', None

    # 自动生成 weight_key
    if 'weight_key' not in dim_def:
        dim_def['weight_key'] = f'{dim_id}_weight'

    # 方法校验
    method = dim_def.get('method', 'string_match')
    if method not in METHOD_REGISTRY:
        return False, f'未知匹配方法：{method}', None

    # 填充方法默认值
    reg = METHOD_REGISTRY[method]
    dim_def.setdefault('detail_type', reg['default_detail_type'])
    dim_def.setdefault('icon', reg['default_icon'])
    dim_def.setdefault('color', reg['default_color'])
    dim_def.setdefault('default_weight', 0.0)
    dim_def.setdefault('score_label', dim_def.get('label', dim_id))
    dim_def.setdefault('params', reg['default_params'])

    # 转换 ability_fields / opportunity_fields 为列表（前端可能传字符串）
    if isinstance(dim_def.get('ability_fields'), str):
        dim_def['ability_fields'] = [dim_def['ability_fields']]
    if isinstance(dim_def.get('opportunity_fields'), str):
        dim_def['opportunity_fields'] = [dim_def['opportunity_fields']]
    dim_def.setdefault('ability_fields', [])
    dim_def.setdefault('opportunity_fields', [])

    # 构建运行时格式（含 compute）
    rt = _dim_def_to_runtime(dim_def)
    DIMENSIONS.append(rt)
    _save_dimensions()

    # 返回可序列化版本（不含 compute）
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
