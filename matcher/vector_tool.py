# -*- coding: utf-8 -*-
"""
vector_tool.py —— 向量语义匹配共享工具层

职责：
  提供进程级单例的文本→向量转换服务。所有向量匹配维度共享同一个模型实例。
  模型懒加载（首次 encode 时），文本向量自动缓存。

缓存策略：
  以文本字符串为 key（格式："{model_name}||{text}"），numpy 向量为 value。
  - 同一模型、同一文本 → 缓存命中，避免重复推理
  - 不同模型、相同文本 → 各自缓存，互不干扰
  - 模型切换时清空该模型对应缓存（向量空间不同不可混用）

模型加载时机：
  首次调用 encode() 时加载。系统没有向量维度时，模型不会被加载，内存零开销。
"""

import numpy as np

# ---- 进程级单例 ----
_model = None          # SentenceTransformer 实例（None 表示未加载）
_model_name = None     # 当前加载的模型标识名
_cache = {}            # 文本→向量缓存，key 格式: "{model_name}||{text}"


def encode(model_name, text):
    """
    将文本转为归一化的语义向量。

    参数:
        model_name (str): 模型标识名，如 'BAAI/bge-small-zh-v1.5'
        text       (str): 待编码的文本

    返回:
        numpy.ndarray: 归一化向量（L2 范数为 1），可直接用点积算余弦相似度
                      空文本返回零向量（维度 = 模型的嵌入维度）

    异常:
        RuntimeError: 模型加载失败时抛出
    """
    global _model, _model_name, _cache

    # ---- 1) 模型切换检测：模型名变了 → 重新加载 ----
    if model_name != _model_name:
        from sentence_transformers import SentenceTransformer  # 懒 import，避免启动时加载 torch
        try:
            _model = SentenceTransformer(model_name)
        except Exception as e:
            # 加载失败时重置状态，让下次可以重试
            _model = None
            _model_name = None
            raise RuntimeError(
                f'无法加载嵌入模型 "{model_name}": {e}\n'
                f'请确认模型名称是否正确，以及网络是否可达 HuggingFace。'
            )
        _model_name = model_name
        _cache.clear()   # 不同模型的向量空间不同，全部缓存作废

    # ---- 2) 空文本处理 ----
    if not text or not text.strip():
        dim = _model.get_sentence_embedding_dimension()
        return np.zeros(dim)

    # ---- 3) 缓存查找 ----
    cache_key = text  # 直接用文本字符串作 key（简洁，且同模型下文本→向量是确定性的）
    if cache_key in _cache:
        return _cache[cache_key]

    # ---- 4) 模型推理 + 存入缓存 ----
    vec = _model.encode(text, normalize_embeddings=True)
    _cache[cache_key] = vec
    return vec


def batch_encode(model_name, texts):
    """
    批量编码：对一组文本一次性进行向量推理，大幅快于逐条 encode()。

    参数:
        model_name (str):    模型标识名
        texts      (list[str]): 待编码的文本列表

    返回:
        list[numpy.ndarray]: 与 texts 一一对应的归一化向量列表
    """
    global _model, _model_name, _cache

    # 过滤空文本和已缓存文本
    uncached_texts = []
    uncached_indices = []
    results = [None] * len(texts)

    for i, t in enumerate(texts):
        if not t or not t.strip():
            # 空文本后面统一处理
            uncached_texts.append(t)
            uncached_indices.append(i)
            continue
        if t in _cache:
            results[i] = _cache[t]
        else:
            uncached_texts.append(t)
            uncached_indices.append(i)

    if not uncached_texts:
        return results

    # 确保模型已加载
    if model_name != _model_name:
        encode(model_name, '')  # 触发模型加载

    # 批量推理
    vecs = _model.encode(uncached_texts, normalize_embeddings=True, show_progress_bar=False)

    for idx, vec in zip(uncached_indices, vecs):
        if not texts[idx] or not texts[idx].strip():
            dim = _model.get_sentence_embedding_dimension()
            results[idx] = np.zeros(dim)
        else:
            _cache[texts[idx]] = vec
            results[idx] = vec

    return results


def pre_warm_cache(all_abilities, all_opportunities):
    """
    预热缓存：在应用启动时，收集所有 vector_semantic 维度引用的字段文本，
    批量编码后存入缓存。这样首次匹配请求就能秒级响应。

    参数:
        all_abilities    (list[dict]): 全部能力数据
        all_opportunities (list[dict]): 全部机会数据
    """
    global _model, _model_name

    from .dimensions import DIMENSIONS

    # 收集所有 vector_semantic 维度及其模型配置
    vector_dims = []
    for dim in DIMENSIONS:
        if dim.get('method') == 'vector_semantic':
            vector_dims.append(dim)

    if not vector_dims:
        print('[vector_tool] 无向量语义维度，跳过预热')
        return

    total_texts = 0

    for dim in vector_dims:
        dim_id = dim['id']
        # 从 MATCH_CONFIG 获取模型名
        from .engine import MATCH_CONFIG
        model_name = MATCH_CONFIG.get(f'{dim_id}_model_name', 'BAAI/bge-small-zh-v1.5')
        if not model_name:
            model_name = 'BAAI/bge-small-zh-v1.5'

        # 收集能力侧和机会侧所有相关字段的唯一文本
        texts = set()
        for item in all_abilities:
            for f in dim['ability_fields']:
                val = item.get(f, '')
                if val and val.strip():
                    texts.add(val)
        for item in all_opportunities:
            for f in dim['opportunity_fields']:
                val = item.get(f, '')
                if val and val.strip():
                    texts.add(val)

        if not texts:
            print(f'[vector_tool] 维度 {dim_id} 无文本数据，跳过')
            continue

        text_list = list(texts)
        print(f'[vector_tool] 维度 {dim_id} ({dim["label"]})：收集 {len(text_list)} 条唯一文本，开始批量编码...')

        # 确保模型加载
        if model_name != _model_name:
            from sentence_transformers import SentenceTransformer
            print(f'[vector_tool] 加载模型: {model_name}')
            _model = SentenceTransformer(model_name)
            _model_name = model_name
            _cache.clear()

        # 批量编码
        vecs = _model.encode(text_list, normalize_embeddings=True, show_progress_bar=True)
        for text, vec in zip(text_list, vecs):
            _cache[text] = vec

        total_texts += len(text_list)
        print(f'[vector_tool] 维度 {dim_id} 预热完成：{len(text_list)} 条文本已缓存')

    print(f'[vector_tool] 全部预热完成：共 {total_texts} 条文本，缓存条目 {len(_cache)} 个')


def clear_cache():
    """
    手动清空缓存。用于切换模型或释放内存。
    多数情况下不需要显式调用，模型切换时自动清。
    """
    global _cache
    _cache.clear()


def is_model_loaded():
    """检查模型是否已加载（供外部查询状态）。"""
    return _model is not None


def get_model_info():
    """
    获取当前模型信息。
    返回: dict 或 None
    """
    if _model is None:
        return None
    return {
        'model_name': _model_name,
        'dimension': _model.get_sentence_embedding_dimension(),
        'cache_size': len(_cache),
    }
