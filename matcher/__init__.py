# -*- coding: utf-8 -*-
"""
matcher 包 —— 场景机会与场景能力匹配核心模块 (v3)

============================================
包概述
============================================
matcher 是场景匹配系统的核心业务逻辑包，采用"可插拔维度"架构。
它将数据加载、领域归一化、维度注册、匹配计算和向量缓存等功能
封装为独立的子模块，通过 __init__.py 统一导出公共接口。

外部调用方（如 app.py）只需 import matcher 即可使用全部功能，
无需关心内部实现细节。

============================================
子模块说明
============================================
  - data_loader.py  : 从 Excel 加载并清洗能力和机会数据
  - normalizer.py   : 将异名同义的领域值归一化到标准大类
  - dimensions.py   : 维度注册表、方法注册表、维度动态增删
  - engine.py       : 匹配引擎核心——多维度加权打分与排序
  - vector_tool.py  : 向量语义工具——sentence-transformers 编码与缓存
  - llm_explainer.py: LLM 解释生成——调用 LLM API 解释匹配结果

============================================
v3 版本新增
============================================
  - 维度动态增删接口（基于 dimensions.json 持久化）
  - 向量语义匹配维度（vector_semantic）
  - LLM 流式解释（SSE + 缓存）
  - 权重自动缩放与维度私有参数校验

============================================
版本历史
============================================
  v1: 固定维度（领域 + 区域），硬编码匹配逻辑
  v2: 可配置权重（domain_weight, region_weight），前端动态调整
  v3: 完全可插拔维度架构，支持运行时增删匹配维度和自定义方法
"""

# ============================================================================
# 数据加载子模块
# ============================================================================
# 从 Excel 文件中加载场景能力和场景机会数据，进行字段清洗后返回 dict 列表
from .data_loader import load_abilities, load_opportunities

# ============================================================================
# 领域归一化子模块
# ============================================================================
# 将不同数据源中表述不一致的领域值统一映射到标准大类（如"人工智能（软件）"→"人工智能"）
from .normalizer import normalize_domain

# ============================================================================
# 维度注册表子模块
# ============================================================================
# DIMENSIONS:  运行时维度注册表（list[dict]），记录所有活跃的匹配维度定义
# METHOD_REGISTRY: 匹配方法注册表（dict），记录所有可用的匹配算法及其参数模板
from .dimensions import (
    DIMENSIONS,
    get_dimensions,             # 返回当前维度列表（深拷贝，避免外部修改）
    get_dimension_by_id,        # 按 dim_id 查找维度定义
    get_dimension_by_weight_key, # 按权重 key（如 domain_weight）查找维度
    get_weight_keys,            # 返回当前所有有效的权重 key 列表
    get_next_dim_id,            # 生成下一个可用的维度 ID
    add_dimension,              # 添加新维度（校验 + 持久化到 dimensions.json）
    delete_dimension,           # 删除维度（校验数量限制 + 更新持久化文件）
    METHOD_REGISTRY,            # 匹配方法注册表（供前端展示方法列表）
    dim_def_to_runtime,         # 将持久化格式的维度定义转为运行时格式
    runtime_to_dim_def,         # 将运行时格式的维度定义转回持久化格式
)

# ============================================================================
# 匹配引擎子模块
# ============================================================================
# 核心匹配逻辑：遍历所有维度对每条候选进行打分，加权求和后排序返回 Top N
from .engine import (
    match_ability_to_opportunities,   # 能力 → 机会匹配（主入口）
    match_opportunity_to_abilities,   # 机会 → 能力匹配（对称入口）
    get_config,                       # 获取当前完整配置（权重、top_n、维度参数）
    get_config_with_dimensions,       # 获取配置 + 维度元信息（供前端 /api/dimensions 使用）
    update_config,                    # 更新配置（持久化到 config.json）
    load_config_from_file,            # 从 config.json 加载配置
    sync_config_with_dimensions,      # 同步 config 与 DIMENSIONS——增删权重 key
)

# ============================================================================
# 向量缓存子模块
# ============================================================================
# 在服务启动时批量编码所有文本为向量，存入内存缓存，加速后续匹配请求
from .vector_tool import pre_warm_cache


# ============================================================================
# 公共接口声明
# ============================================================================
# __all__ 定义了 from matcher import * 的行为，也作为包的公开 API 文档
__all__ = [
    # ---- 数据加载 ----
    'load_abilities',
    'load_opportunities',

    # ---- 归一化 ----
    'normalize_domain',

    # ---- 维度注册表（动态） ----
    'DIMENSIONS',
    'get_dimensions',
    'get_dimension_by_id',
    'get_dimension_by_weight_key',
    'get_weight_keys',
    'get_next_dim_id',
    'add_dimension',
    'delete_dimension',
    'METHOD_REGISTRY',
    'dim_def_to_runtime',
    'runtime_to_dim_def',

    # ---- 匹配引擎 ----
    'match_ability_to_opportunities',
    'match_opportunity_to_abilities',
    'get_config',
    'get_config_with_dimensions',
    'update_config',
    'load_config_from_file',
    'sync_config_with_dimensions',

    # ---- 向量预热 ----
    'pre_warm_cache',
]
