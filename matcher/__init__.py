# -*- coding: utf-8 -*-
"""
matcher 包 —— 场景机会与场景能力匹配核心模块 (v3)

导出数据加载、维度注册表和匹配引擎三个子模块的公共接口。
外部调用方（如 app.py）只需 import matcher 即可使用全部功能。

v3 新增：维度动态增删接口（基于 dimensions.json 持久化）
"""

from .data_loader import load_abilities, load_opportunities
from .normalizer import normalize_domain
from .dimensions import (
    DIMENSIONS,
    get_dimensions,
    get_dimension_by_id,
    get_dimension_by_weight_key,
    get_weight_keys,
    get_next_dim_id,
    add_dimension,
    delete_dimension,
    METHOD_REGISTRY,
    dim_def_to_runtime,
    runtime_to_dim_def,
)
from .engine import (
    match_ability_to_opportunities,
    match_opportunity_to_abilities,
    get_config,
    get_config_with_dimensions,
    update_config,
    load_config_from_file,
    sync_config_with_dimensions,
)
from .vector_tool import pre_warm_cache


__all__ = [
    # 数据加载
    'load_abilities',
    'load_opportunities',
    # 归一化
    'normalize_domain',
    # 维度注册表（动态）
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
    # 匹配引擎
    'match_ability_to_opportunities',
    'match_opportunity_to_abilities',
    'get_config',
    'get_config_with_dimensions',
    'update_config',
    'load_config_from_file',
    'sync_config_with_dimensions',
    # 向量预热
    'pre_warm_cache',
]
