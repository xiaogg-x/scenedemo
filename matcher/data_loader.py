# -*- coding: utf-8 -*-
"""
data_loader.py —— 数据加载与清洗模块

============================================
模块职责
============================================
本模块负责场景匹配系统所有数据的读入和预处理工作，是整个系统
的数据入口层（Data Access Layer）。

核心功能：
  1. 使用 pandas + openpyxl 从 .xlsx 文件中读取原始数据
  2. 通过 _safe_str() 清洗每个字段：NaN → 空字符串，去除首尾空白
  3. 为每条数据生成唯一 ID（序号），确保后续匹配检索的定位能力
  4. 封装为标准 dict 列表格式，供所有上层模块使用

============================================
数据格式约定
============================================
能力侧字段:
  id, name, company, domain, district, overview, highlight, effect, target_customer

机会侧字段:
  id, name, domain, sub_domain, area, overview, welcome, category, unit, investment

两类数据的字段不完全相同，这反映了数据源本身的差异。
匹配引擎通过维度定义中的 source_field / target_field 指定具体匹配哪些字段。

============================================
设计考量
============================================
  - Excel 读取：使用 pandas.read_excel + 指定 sheet_name，而非 openpyxl 裸调
    pandas 自动处理合并单元格、空行等边界情况
  - 数据清洗：_safe_str() 统一处理 None、NaN、空字符串三种空值情况
  - 内存模型：所有数据一次性加载到内存 list[dict]，后续请求零磁盘 I/O
  - 启动时加载：在 Flask 启动时执行，而非按需加载，保证首次请求延迟低
"""

import pandas as pd


def _safe_str(value):
    """
    安全转换：将 None、NaN 等非字符串值转为空字符串，并去除首尾空白。

    这是数据清洗的核心工具函数，被所有字段读取逻辑共用。
    设计为独立函数而非内联代码，便于统一维护清洗规则。

    处理逻辑（优先级从高到低）：
      1. 如果 value 为 None（Python 原生空值） → 返回空字符串
      2. 如果 value 是 NaN（pandas/numpy 空值） → 返回空字符串
      3. 其他情况 → 转为字符串并去除首尾空白

    参数:
        value: 单元格原始值，类型可能是 str / float / None / numpy.float64

    返回:
        str: 清洗后的字符串，永远不会返回 None

    注意:
        NaN 值需要用 pd.isna() 判断，不能用 value is NaN 或 value == NaN，
        因为 NaN != NaN（IEEE 754 标准规定 NaN 不等于任何值，包括自身）。
    """
    # 先检查 Python None——比 pd.isna 更快
    if value is None:
        return ''
    try:
        # pd.isna 可以检测 numpy.nan, pandas.NA, None 等多种空值
        # 对应 Excel 中的空白单元格
        if pd.isna(value):
            return ''
    except TypeError:
        # 某些类型（如字符串）传给 pd.isna 可能抛 TypeError
        # 这是正常的，忽略后继续下一步
        pass
    # .strip() 去除字符串两端的多余空白（空格、制表符、换行等）
    return str(value).strip()


def load_abilities(filepath):
    """
    加载并清洗场景能力数据。

    数据来源: 场景能力数据列表.xlsx → Sheet "创新产品发布审核列表"

    处理流程:
      1. 用 pandas 读取 Excel（自动处理编码、合并单元格等）
      2. 遍历每一行，将 Excel 列映射为 dict 字段
      3. 用 _safe_str() 清洗每个字段值
      4. 跳过名称为空的无效数据
      5. 修复 ID 为 0 的异常数据（自动赋序号）

    参数:
        filepath (str): 场景能力 Excel 文件的绝对路径

    返回:
        list[dict]: 每条场景能力为一个 dict，包含以下字段：
            - id:             int, 序号（唯一标识，从 1 开始）
            - name:           str, 产品名称（清洗后）
            - company:        str, 企业名称
            - domain:         str, 所属产业领域（待归一化的原始值）
            - district:       str, 所属区（开发区）
            - overview:       str, 能力概述
            - highlight:      str, 创新亮点
            - effect:         str, 应用实效
            - target_customer: str, 意向对接客户

    异常:
        如果 Excel 文件不存在或 sheet 名称不匹配，pandas 会直接抛出异常。
        这些异常不在函数内捕获，由调用方（app.py）在启动时处理。
    """
    # 读取指定 sheet，pandas 自动推断列类型
    df = pd.read_excel(filepath, sheet_name='创新产品发布审核列表')

    abilities = []  # 存放所有清洗后的能力数据
    for _, row in df.iterrows():
        # 逐行映射 Excel 列 → dict 字段
        # _safe_str 确保所有值都是字符串（空值变为空字符串）
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

        # 跳过名称为空的数据行（可能是 Excel 中的空行或测试数据）
        if not ability['name']:
            continue

        # 修复 ID 为 0 的异常情况（数据导入时序号列可能缺失）
        # 自动赋予递增 ID，保证每条数据都有唯一标识
        if ability['id'] == 0:
            ability['id'] = len(abilities) + 1

        abilities.append(ability)

    print(f'[data_loader] 加载场景能力 {len(abilities)} 条')
    return abilities


def load_opportunities(filepath):
    """
    加载并清洗场景机会数据。

    数据来源: 场景机会数据列表.xlsx → Sheet "应用场景发布审核"

    处理流程与 load_abilities 相同，但字段映射不同：
      - 能力侧的 "产品名称" 对应机会侧的 "应用场景项目名称"
      - 能力侧的 "所属区" 对应机会侧的 "应用场景所属区域"
      - 机会侧多了 sub_domain, category, unit, investment 等字段

    参数:
        filepath (str): 场景机会 Excel 文件的绝对路径

    返回:
        list[dict]: 每条场景机会为一个 dict，包含以下字段：
            - id:           int, 序号（唯一标识，从 1 开始）
            - name:         str, 应用场景项目名称
            - domain:       str, 应用场景所属领域（待归一化的原始值）
            - sub_domain:   str, 应用场景细分领域
            - area:         str, 应用场景所属区域
            - overview:     str, 应用场景概述
            - welcome:      str, 欢迎合作方向（清洗后，用于领域匹配）
            - category:     str, 场景分类
            - unit:         str, 应用场景搭建单位
            - investment:   str, 项目投资方式

    异常:
        如果 Excel 文件不存在或 sheet 名称不匹配，pandas 会直接抛出异常。
    """
    # 机会数据的 sheet 名称与能力数据不同
    df = pd.read_excel(filepath, sheet_name='应用场景发布审核')

    opportunities = []  # 存放所有清洗后的机会数据
    for _, row in df.iterrows():
        # 逐行映射 Excel 列 → dict 字段
        # 注意机会侧的列名和能力侧不同，所以字段映射也不同
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

        # 跳过名称为空的数据行
        if not opp['name']:
            continue

        # 修复 ID 为 0 的异常情况
        if opp['id'] == 0:
            opp['id'] = len(opportunities) + 1

        opportunities.append(opp)

    print(f'[data_loader] 加载场景机会 {len(opportunities)} 条')
    return opportunities


def get_by_id(items, item_id):
    """
    按 ID 从列表中进行线性查找。

    数据量较小（通常 < 200 条），线性查找性能足够，不需要建哈希索引。
    如果数据量增长到万级以上，可考虑在加载时就建 {id: item} 字典。

    参数:
        items   (list[dict]): 场景能力或机会的完整列表
        item_id (int):        要查找的 ID

    返回:
        dict or None: 匹配到的条目，未找到则返回 None

    示例:
        >>> ability = get_by_id(ALL_ABILITIES, 5)
        >>> if ability:
        >>>     print(ability['name'])
    """
    for item in items:
        if item['id'] == item_id:
            return item
    return None
