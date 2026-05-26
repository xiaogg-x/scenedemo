# -*- coding: utf-8 -*-
"""
schema.py —— 数据表字段集中注册中心（v3：场景→字段映射）

职责：
  将两张业务表的字段名与使用场景集中管理。
  数据加载时只更新「字段注册表」（记录实际有哪些列）；
  所有 API 取字段的逻辑由「场景→字段映射」决定，映射可持久化并通过前端修改。

设计原则：
  1. 字段注册表 = 数据加载时直接覆盖，不做任何启发式匹配
  2. 场景→字段映射 = 一个 JSON 文件，直接用真实字段名定义每个场景取哪些字段
  3. 没有「角色名」中间层 —— scenes、detail_labels、frontend_list 全部使用真实数据列名
  4. 字段名变了 → 在映射中更新所有引用该字段名的地方即可

文件结构：
  后台数据/field_mapping.json  —— 场景→字段映射（可持久化，前端可修改）

使用方式：
  from matcher.schema import init_from_data, build_scene_dict, get_role

  # 数据加载后
  init_from_data(abilities[0], opportunities[0])

  # API 序列化
  summary = build_scene_dict(item, 'ability', 'list_summary')

  # 取单个字段
  domain = get_role(item, 'ability', 'domain')
"""

import json
import os
import copy


# ============================================================================
# 运行时状态
# ============================================================================

def init_from_data(ability_sample=None, opp_sample=None):
    """
    从实际数据的第一行覆盖字段注册表（keys 列表）。
    不做任何启发式匹配。

    参数:
        ability_sample (dict|None): 能力表第一行数据
        opp_sample     (dict|None): 机会表第一行数据
    """
    global _mapping
    if _mapping is None:
        load_mapping()
    if ability_sample is not None and isinstance(ability_sample, dict):
        _mapping['ability']['keys'] = list(ability_sample.keys())
        print(f'[schema] 能力表字段注册：{_mapping["ability"]["keys"]}')
    if opp_sample is not None and isinstance(opp_sample, dict):
        _mapping['opportunity']['keys'] = list(opp_sample.keys())
        print(f'[schema] 机会表字段注册：{_mapping["opportunity"]["keys"]}')


# ============================================================================
# 场景→字段映射（默认值 = 当前测试数据字段名）
# ============================================================================
#
# 结构：
#   {
#     "<table>": {
#       "keys":          ["<actual_col>", ...],           ← 真实字段名列表
#       "scenes":        { "<scene>": ["<col>", ...], ... },
#       "detail_labels": { "<col>": "<中文标签>", ... },  ← key 是真实字段名
#       "frontend_list": [{ "role": "...", "label": "...", "key": "<col>" }, ...],
#       "table_label":   "<中文表名>",
#     }
#   }
#
# scenes、detail_labels、frontend_list 中全部使用真实字段名，
# 没有中间映射层。

_DEFAULT_MAPPING = {
    'ability': {
        'keys': ['id', 'name', 'company', 'domain', 'overview', 'highlight', 'effect', 'target_customer'],
        'scenes': {
            'list_summary':   ['id', 'name', 'company', 'domain'],
            'match_source':   ['id', 'name', 'company', 'domain', 'overview', 'target_customer'],
            'match_target':   ['id', 'name', 'company', 'domain', 'overview', 'highlight', 'effect', 'target_customer'],
            'detail_fields':  ['name', 'domain', 'overview', 'target_customer'],
            'text_fields':    ['overview', 'target_customer'],
            'domain_field':   'domain',
            'id_field':       'id',
            'name_field':     'name',
        },
        'detail_labels': {
            'name':            '产品名称',
            'domain':          '所属产业领域',
            'overview':        '能力概述',
            'target_customer': '意向对接客户',
        },
        'frontend_list': [
            {'role': 'id',       'label': '序号',           'key': 'id'},
            {'role': 'title',    'label': '产品名称',       'key': 'name'},
            {'role': 'subtitle', 'label': '企业名称',       'key': 'company'},
            {'role': 'tag',      'label': '所属产业领域',   'key': 'domain'},
        ],
        'table_label': '场景能力数据列表',
        'card_source_subtitle': 'company',
    },
    'opportunity': {
        'keys': ['id', 'name', 'domain', 'sub_domain', 'area', 'overview', 'welcome', 'category', 'unit', 'investment'],
        'scenes': {
            'list_summary':   ['id', 'name', 'domain', 'sub_domain', 'area'],
            'match_source':   ['id', 'name', 'domain', 'overview', 'welcome'],
            'match_target':   ['id', 'name', 'domain', 'sub_domain', 'area', 'overview', 'welcome', 'category', 'unit'],
            'detail_fields':  ['name', 'domain', 'overview', 'welcome'],
            'text_fields':    ['overview', 'welcome'],
            'domain_field':   'domain',
            'welcome_field':  'welcome',
            'id_field':       'id',
            'name_field':     'name',
        },
        'detail_labels': {
            'name':     '应用场景项目名称',
            'domain':   '应用场景所属领域',
            'overview': '应用场景概述',
            'welcome':  '欢迎合作方向',
        },
        'frontend_list': [
            {'role': 'id',       'label': '序号',               'key': 'id'},
            {'role': 'title',    'label': '应用场景项目名称',   'key': 'name'},
            {'role': 'subtitle', 'label': '应用场景所属区域',   'key': 'area'},
            {'role': 'tag',      'label': '应用场景所属领域',   'key': 'domain'},
        ],
        'table_label': '场景机会数据列表',
        'card_source_subtitle': 'domain',
    },
}

# 运行时映射（从文件加载或使用默认值）
_mapping = None

# 映射持久化路径
_MAPPING_FILE = None


def _get_mapping_file():
    global _MAPPING_FILE
    if _MAPPING_FILE is None:
        _MAPPING_FILE = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', '后台数据', 'field_mapping.json'
        ))
    return _MAPPING_FILE


def load_mapping():
    """
    从 field_mapping.json 加载映射。文件不存在时使用默认值。
    自动将旧版 {role: col} dict 格式的 keys 迁移为列表。
    """
    global _mapping
    mf = _get_mapping_file()
    if os.path.exists(mf):
        try:
            with open(mf, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if 'ability' in loaded and 'opportunity' in loaded:
                    # 兼容旧格式：keys 为 dict 时转为 list
                    for tbl in ('ability', 'opportunity'):
                        if isinstance(loaded[tbl].get('keys'), dict):
                            loaded[tbl]['keys'] = list(loaded[tbl]['keys'].values())
                    _mapping = loaded
                    print(f'[schema] 已从 {mf} 加载字段映射')
                    return
        except Exception as e:
            print(f'[schema] 加载映射文件失败: {e}，使用默认值')
    _mapping = copy.deepcopy(_DEFAULT_MAPPING)
    print('[schema] 使用默认字段映射')


def save_mapping():
    """将当前映射持久化到 field_mapping.json。"""
    global _mapping
    mf = _get_mapping_file()
    try:
        os.makedirs(os.path.dirname(mf), exist_ok=True)
        with open(mf, 'w', encoding='utf-8') as f:
            json.dump(_mapping, f, ensure_ascii=False, indent=2)
        print(f'[schema] 字段映射已保存至 {mf}')
    except Exception as e:
        print(f'[schema] 保存映射文件失败: {e}')


def get_mapping():
    """返回当前场景→字段映射的深拷贝（防止外部修改）。"""
    global _mapping
    if _mapping is None:
        load_mapping()
    return copy.deepcopy(_mapping)


def update_mapping(new_mapping):
    """
    更新映射并持久化。

    参数:
        new_mapping (dict): 新映射，必须包含 ability 和 opportunity
    """
    global _mapping
    if 'ability' not in new_mapping or 'opportunity' not in new_mapping:
        raise ValueError('映射必须包含 ability 和 opportunity')
    _mapping = copy.deepcopy(new_mapping)
    save_mapping()


# ============================================================================
# 工具函数 —— 从数据 item 中直接按字段名取值
# ============================================================================
# scenes 和 detail_labels 中使用的就是真实列名，无需任何中间映射。
# 字段缺失时静默返回 ''。


def get_role(item, table, col):
    """
    取单个字段值。col 是真实数据列名。

    参数:
        item  (dict): 数据行
        table (str):  'ability' | 'opportunity'（仅用于兼容旧签名，实际不使用）
        col   (str):  真实列名

    返回:
        str/int: 字段值，缺失时返回 ''
    """
    return item.get(col, '')


def get_indirect_role(item, table, scene):
    """
    scene 存储的值就是真实列名，直接取值。
    例如 scene='domain_field' 值为 'domain'，等价于 item.get('domain', '')。

    参数:
        item  (dict): 数据行
        table (str):  'ability' | 'opportunity'
        scene (str):  场景名（其值为真实列名）

    返回:
        str/int: 字段值
    """
    col = _mapping[table]['scenes'][scene]
    return item.get(col, '')


def build_scene_dict(item, table, scene):
    """
    按场景定义的字段列表，从 item 中直接组装 dict。
    key 就是真实列名，前端直接用列名访问。

    参数:
        item  (dict): 数据行
        table (str):  'ability' | 'opportunity'
        scene (str):  场景名，如 'list_summary'、'match_source'

    返回:
        dict: {列名: 值, ...}
    """
    cols = _mapping[table]['scenes'][scene]
    return {col: item.get(col, '') for col in cols}


def build_detail_dict(item, table):
    """
    组装字段对照表 dict（中文标签→值），供匹配明细展示。

    返回:
        dict: {中文标签: 值, ...}
    """
    cols = _mapping[table]['scenes']['detail_fields']
    labels = _mapping[table]['detail_labels']
    return {labels[col]: item.get(col, '') for col in cols}


def join_text_roles(item, table):
    """
    将 text_fields 场景中定义的多个字段值用空格拼接。

    返回:
        str: 拼接后的文本
    """
    cols = _mapping[table]['scenes']['text_fields']
    parts = [item.get(col, '') for col in cols if item.get(col, '')]
    return ' '.join(parts)


# ============================================================================
# 前端渲染数据（供 /api/schema 返回）
# ============================================================================

def _get_frontend_schema():
    """返回前端渲染所需的 list_fields / table_label 等。"""
    return {
        'ability': {
            'table_label':          _mapping['ability']['table_label'],
            'list_fields':          _mapping['ability']['frontend_list'],
            'card_source_subtitle': _mapping['ability']['card_source_subtitle'],
            'raw_keys':             _mapping['ability']['keys'],
        },
        'opportunity': {
            'table_label':          _mapping['opportunity']['table_label'],
            'list_fields':          _mapping['opportunity']['frontend_list'],
            'card_source_subtitle': _mapping['opportunity']['card_source_subtitle'],
            'raw_keys':             _mapping['opportunity']['keys'],
        },
    }


# ============================================================================
# metadata.html 兼容（自适应 tables 数据，由 field_mapping.json 驱动）
# ============================================================================

def _get_tables_meta():
    """
    自适应生成 tables 元数据，供 metadata.html 使用。
    所有布尔标记从 field_mapping.json 中的场景定义自动推导，无需手动维护。
    换数据集时此函数无需修改。
    """

    def _in_scene(table, col, *scenes):
        """判断字段是否出现在指定场景中（支持列表场景和单值场景）。"""
        for s in scenes:
            val = _mapping[table]['scenes'].get(s)
            if val is None:
                continue
            if isinstance(val, list) and col in val:
                return True
            if isinstance(val, str) and val == col:
                return True
        return False

    def _infer_type(col, table):
        """根据字段名推断类型：id 字段为 int，其余为 str。"""
        id_field = _mapping[table]['scenes'].get('id_field', 'id')
        return 'int' if col == id_field else 'str'

    def _build_match_role(col, table):
        """根据字段所在场景自动生成匹配用途描述。"""
        parts = []
        if _in_scene(table, col, 'text_fields'):
            parts.append('文本匹配')
        if _in_scene(table, col, 'domain_field'):
            parts.append('领域匹配')
        if _in_scene(table, col, 'detail_fields'):
            parts.append('详情展示')
        return '、'.join(parts) if parts else None

    def _front_card_role(col, table):
        """判断字段是否出现在 frontend_list 中（前端卡片展示）。"""
        for entry in _mapping[table].get('frontend_list', []):
            if entry.get('key') == col:
                return True
        return False

    result = []
    table_meta = {
        'ability':     {'table_name': _mapping['ability'].get('table_label', '能力表'),     'table_key': 'ability'},
        'opportunity': {'table_name': _mapping['opportunity'].get('table_label', '机会表'), 'table_key': 'opportunity'},
    }

    for table_key, meta in table_meta.items():
        tbl = _mapping[table_key]
        labels = tbl.get('detail_labels', {})
        fields = []

        for col in tbl.get('keys', []):
            fields.append({
                'key':           col,
                'label':         labels.get(col, col),
                'type':          _infer_type(col, table_key),
                'match':         _in_scene(table_key, col, 'detail_fields'),
                'match_role':    _build_match_role(col, table_key),
                'text_source':   _in_scene(table_key, col, 'text_fields'),
                'domain_source': _in_scene(table_key, col, 'domain_field'),
                'api_list':      _in_scene(table_key, col, 'list_summary'),
                'api_detail':    _in_scene(table_key, col, 'match_target'),
                'front_list':    _in_scene(table_key, col, 'list_summary'),
                'front_card':    _front_card_role(col, table_key),
            })

        result.append({
            'table_name': meta['table_name'],
            'table_key':  table_key,
            'fields':     fields,
        })

    return result


# ============================================================================
# /api/schema 完整响应
# ============================================================================

def get_schema_json():
    """
    返回 /api/schema 的完整 JSON。
    包含字段映射、前端渲染信息、匹配配置、领域映射表。
    """
    from .engine import MATCH_CONFIG
    from .normalizer import DOMAIN_MAP

    if _mapping is None:
        load_mapping()

    return {
        'frontend': _get_frontend_schema(),
        'mapping': get_mapping(),          # 完整映射，供前端映射配置页使用
        'tables': _get_tables_meta(),
        'match_config': {
            'description': '当前匹配参数配置（默认值，运行时可通过 /api/config 动态调整）',
            'fields': [
                {'key': 'domain_weight',   'label': '领域匹配权重', 'type': 'float', 'default': MATCH_CONFIG['domain_weight'],   'range': '0~1', 'note': '与 text_weight 之和应为 1'},
                {'key': 'text_weight',     'label': '文本相似度权重', 'type': 'float', 'default': MATCH_CONFIG['text_weight'],     'range': '0~1', 'note': '与 domain_weight 之和应为 1'},
                {'key': 'top_n',           'label': '返回前N条',     'type': 'int',   'default': MATCH_CONFIG['top_n'],           'range': '1~20', 'note': '匹配结果返回条数'},
                {'key': 'text_max_length', 'label': '文本截取长度',   'type': 'int',   'default': MATCH_CONFIG['text_max_length'], 'range': '50~2000', 'note': '文本匹配时截取前 N 个中文字符'},
            ],
        },
        'match_logic': (
            '匹配算法说明：\n'
            '  total_score = domain_score × domain_weight + text_score × text_weight\n'
            '\n'
            '  领域得分 (domain_score)：\n'
            '    - 能力侧 domain 字段在机会侧 welcome 字段中做子串精确匹配 → 1.0\n'
            '    - 归一化后大类相同（通过 normalizer.py 的 DOMAIN_MAP）→ 0.5\n'
            '    - 均未命中 → 0.0\n'
            '\n'
            '  文本得分 (text_score)：\n'
            '    - 能力侧文本 = overview + target_customer（清洗后截取前 N 字）\n'
            '    - 机会侧文本 = overview + welcome（清洗后截取前 N 字）\n'
            '    - 分别提取中文 2-gram（bigram）字符集\n'
            '    - Jaccard 相似度 = |交集| / |并集|\n'
            '\n'
            '  反向匹配 (机会→能力) 额外逻辑：\n'
            '    - 领域得分先用机会侧 welcome 匹配能力侧 domain\n'
            '    - 若得分为 0，再用机会侧 domain 匹配能力侧 target_customer 兜底\n'
        ),
        'domain_map': {
            'description': '领域归一化映射表（normalizer.py DOMAIN_MAP）',
            'entries': [{'raw': k, 'normalized': v} for k, v in sorted(DOMAIN_MAP.items())],
        },
    }


# ============================================================================
# 启动时自动加载映射
# ============================================================================
load_mapping()
