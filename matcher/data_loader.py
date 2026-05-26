# -*- coding: utf-8 -*-
"""
data_loader.py —— 数据加载与清洗模块

职责：
  1. 从 Excel 文件中读取场景能力和场景机会原始数据
  2. 清洗字段：将 NaN 替换为空字符串，去除首尾空白
  3. 封装为标准 dict 列表格式，并附带唯一 ID 便于后续匹配检索

使用 pandas + openpyxl 读取 .xlsx 文件。
"""

import pandas as pd


def _safe_str(value):
    """
    安全转换：将 None、NaN 等非字符串值转为空字符串，并去除首尾空白。

    参数:
        value: 单元格原始值（可能是 str / float / None / NaN）

    返回:
        str: 清洗后的字符串
    """
    # pandas 的 NaN（numpy.float64）需要特殊判断
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except TypeError:
        # 非数值类型（如字符串），pd.isna 可能抛异常，忽略继续
        pass
    return str(value).strip()


def load_abilities(filepath):
    """
    加载场景能力数据。

    参数:
        filepath (str): 场景能力 Excel 文件路径

    返回:
        list[dict]: 每条场景能力为一个 dict，包含以下字段：
            - id:           int, 序号（唯一标识）
            - name:         str, 产品名称
            - company:      str, 企业名称
            - domain:       str, 所属产业领域（归一化的领域关键词）
            - district:     str, 所属区（开发区）
            - overview:     str, 能力概述（清洗后）
            - highlight:    str, 创新亮点
            - effect:       str, 应用实效
            - target_customer: str, 意向对接客户
    """
    df = pd.read_excel(filepath, sheet_name='创新产品发布审核列表')

    abilities = []  # 存放所有清洗后的能力数据
    for _, row in df.iterrows():
        ability = {
            'id':              int(row.get('序号', 0)),
            'name':            _safe_str(row.get('产品名称')),
            'company':         _safe_str(row.get('企业名称')),
            'domain':          _safe_str(row.get('所属产业领域')),
            'district':        _safe_str(row.get('所属区（开发区）')),
            'overview':        _safe_str(row.get('能力概述')),
            'highlight':       _safe_str(row.get('创新亮点')),
            'effect':          _safe_str(row.get('应用实效')),
            'target_customer': _safe_str(row.get('意向对接客户')),
        }
        # 跳过名称为空的数据（数据质量问题）
        if not ability['name']:
            continue
        # 确保 ID 唯一且有效
        if ability['id'] == 0:
            ability['id'] = len(abilities) + 1
        abilities.append(ability)

    print(f'[data_loader] 加载场景能力 {len(abilities)} 条')
    return abilities


def load_opportunities(filepath):
    """
    加载场景机会数据。

    参数:
        filepath (str): 场景机会 Excel 文件路径

    返回:
        list[dict]: 每条场景机会为一个 dict，包含以下字段：
            - id:              int, 序号（唯一标识）
            - name:            str, 应用场景项目名称
            - domain:          str, 应用场景所属领域
            - sub_domain:      str, 应用场景细分领域
            - area:            str, 应用场景所属区域
            - overview:        str, 应用场景概述（清洗后）
            - welcome:         str, 欢迎合作方向（清洗后，用于领域匹配）
            - category:        str, 场景分类
            - unit:            str, 应用场景搭建单位
            - investment:      str, 项目投资方式
    """
    df = pd.read_excel(filepath, sheet_name='应用场景发布审核')

    opportunities = []  # 存放所有清洗后的机会数据
    for _, row in df.iterrows():
        opp = {
            'id':         int(row.get('序号', 0)),
            'name':       _safe_str(row.get('应用场景项目名称')),
            'domain':     _safe_str(row.get('应用场景所属领域')),
            'sub_domain': _safe_str(row.get('应用场景细分领域')),
            'area':       _safe_str(row.get('应用场景所属区域')),
            'overview':   _safe_str(row.get('应用场景概述')),
            'welcome':    _safe_str(row.get('欢迎合作方向')),
            'category':   _safe_str(row.get('场景分类')),
            'unit':       _safe_str(row.get('应用场景搭建单位')),
            'investment': _safe_str(row.get('项目投资方式')),
        }
        if not opp['name']:
            continue
        if opp['id'] == 0:
            opp['id'] = len(opportunities) + 1
        opportunities.append(opp)

    print(f'[data_loader] 加载场景机会 {len(opportunities)} 条')
    return opportunities


def get_by_id(items, item_id):
    """
    按 ID 从列表中查找单条数据。

    参数:
        items   (list[dict]): 场景能力或机会的完整列表
        item_id (int):        要查找的 ID

    返回:
        dict or None: 匹配到的条目，未找到则返回 None
    """
    for item in items:
        if item['id'] == item_id:
            return item
    return None
