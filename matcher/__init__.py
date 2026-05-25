# -*- coding: utf-8 -*-
"""
matcher 包 —— 场景机会与场景能力匹配核心模块

导出数据加载、领域归一化和匹配引擎三个子模块的公共接口。
外部调用方（如 app.py）只需 import matcher 即可使用全部功能。
"""

from .data_loader import load_abilities, load_opportunities
from .normalizer import normalize_domain
from .engine import match_ability_to_opportunities, match_opportunity_to_abilities

__all__ = [
    'load_abilities',
    'load_opportunities',
    'normalize_domain',
    'match_ability_to_opportunities',
    'match_opportunity_to_abilities',
]
