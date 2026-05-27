# -*- coding: utf-8 -*-
"""
vector_tool.py —— 向量语义匹配共享工具层

══════════════════════════════════════════════════════════════════════════════
模块概述
══════════════════════════════════════════════════════════════════════════════

本模块为场景匹配系统中的「向量语义匹配」维度提供底层支持，
封装了 SentenceTransformer 模型的加载、文本编码和缓存管理。

它是所有 vector_semantic 维度的**唯一向量服务提供者**——无论系统中有多少个
向量语义维度，它们都共享同一个模型实例和同一套缓存。

══════════════════════════════════════════════════════════════════════════════
核心设计：进程级单例 + 懒加载 + 内存缓存
══════════════════════════════════════════════════════════════════════════════

  ┌──────────────────────────────────────────────────────┐
  │                  进程级全局状态                       │
  │                                                      │
  │   _model     = None | SentenceTransformer 实例       │
  │   _model_name = None | 当前加载的模型标识名           │
  │   _cache     = {}    | 文本 → 向量的内存缓存字典      │
  └──────────────────────────────────────────────────────┘
            │                │                │
            ▼                ▼                ▼
    ┌───────────┐  ┌─────────────┐  ┌──────────────────┐
    │ 模型管理  │  │ 编码服务    │  │ 缓存管理层        │
    │           │  │             │  │                   │
    │_load_model│  │ encode()    │  │ pre_warm_cache()  │
    │           │  │ batch_encode│  │ clear_cache()     │
    │           │  │             │  │ get_model_info()  │
    └───────────┘  └─────────────┘  └──────────────────┘

  三大设计原则：

  1. 单例模式（Singleton）
     整个进程中只有一个模型实例。避免重复加载导致 OOM（显存溢出）。
     所有 vector_semantic 维度的 compute 闭包都调用同一个 encode() 函数。

  2. 懒加载（Lazy Loading）
     模型在首次调用 encode() 时才加载，而非模块导入时。
     如果系统中没有配置任何 vector_semantic 维度，模型永远不会被加载，
     实现了「零开销」的按需初始化。

  3. 内存缓存（In-Memory Cache）
     以文本字符串为 key，numpy 向量为 value 的字典缓存。
     同一文本多次匹配时直接返回缓存的向量，跳过昂贵的模型推理。
     对于 N 个能力 × M 个机会的匹配矩阵，实际推理次数远小于 N×M。

══════════════════════════════════════════════════════════════════════════════
缓存策略详解
══════════════════════════════════════════════════════════════════════════════

  缓存 key: 文本字符串本身（直接用 text 作 key）
  缓存 value: numpy.ndarray（L2 归一化的浮点向量）

  命中条件：
    - 同一模型 + 同一文本 → 命中缓存（最常见的场景）

  不命中的情况：
    - 不同模型 + 相同文本 → 各自缓存，互不干扰（因为切换模型时清空旧缓存）
    - 模型切换后 → 全部缓存作废（不同模型的向量空间不兼容）

  为什么不用 "{model_name}||{text}" 格式的复合 key？
    因为当前实现只支持同时加载一个模型，模型切换时整个 cache 被清空。
    所以用纯文本做 key 就够了，更简洁高效。

  缓存失效时机：
    1. 用户切换嵌入模型（如从 small 切到 large）→ _cache.clear()
    2. 手动调用 clear_cache() → _cache.clear()
    3. 进程重启 → 全部丢失（这是内存缓存的天性）

══════════════════════════════════════════════════════════════════════════════
模型预热机制（pre_warm_cache）
══════════════════════════════════════════════════════════════════════════════

  在应用启动时，收集所有 vector_semantic 维度引用的字段文本，
  使用 batch_encode() 批量一次性完成所有向量的计算并写入缓存。

  预热的好处：
    - 首次用户请求时无需等待模型推理，直接命中缓存 → 秒级响应
    - 批量推理比逐条推理更快（GPU 利用率更高，尤其对 transformer 模型）
    - 启动阶段有时间预算，用户不会感知到延迟

  触发位置：app.py 的 startup 逻辑中调用 pre_warm_cache()
"""

import os
import numpy as np

# 强制设置 HuggingFace 国内镜像站点
# sentence-transformers 库内部下载模型权重时会读取此环境变量
# 对国内网络环境至关重要——不走镜像的话下载速度极慢或完全失败
if not os.environ.get('HF_ENDPOINT'):
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# ---- 进程级单例状态变量 ----
_model = None          # SentenceTransformer 模型实例（None = 尚未加载）
_model_name = None     # 当前加载的模型标识名（如 'BAAI/bge-small-zh-v1.5'）
_cache = {}            # 文本 → 向量的内存缓存字典


def _load_model(model_name):
    """
    加载 SentenceTransformer 模型到内存。

    ══════════════════════════════════════════════════════════════════════
    加载策略：本地优先，联网兜底
    ══════════════════════════════════════════════════════════════════════

      策略A — 本地缓存优先（local_files_only=True）
        直接从 ~/.cache/huggingface/ 目录加载已缓存的模型文件。
        无需网络请求，速度最快（毫秒级）。
        适用于：模型之前已经下载过的情况。

      策略B — 联网下载（local_files_only=False）
        当本地没有找到模型缓存时，通过 HuggingFace Hub 下载。
        由于已设置 HF_ENDPOINT=https://hf-mirror.com，
        下载会走国内镜像站，速度较快。

    参数:
        model_name (str): HuggingFace 上的模型 ID 或本地路径
                         如 'BAAI/bge-small-zh-v1.5'

    返回:
        SentenceTransformer: 已加载并可用的模型实例

    异常:
        可能抛出网络错误（无法连接镜像站）、OSError（磁盘空间不足）等异常
        由调用方 encode() 捕获并转换为 RuntimeError
    """
    from sentence_transformers import SentenceTransformer
    try:
        # 第一步尝试：仅从本地缓存加载（不发起任何网络请求）
        # 这是最快路径，对于已使用过的模型通常是秒开
        return SentenceTransformer(model_name, local_files_only=True)
    except Exception:
        pass  # 本地无缓存 → 继续联网下载
    # 第二步兜底：允许联网下载（走 HF_ENDPOINT 环境变量指定的镜像站）
    print(f'[vector_tool] 本地无缓存，从镜像下载模型: {model_name}')
    return SentenceTransformer(model_name, local_files_only=False)


def encode(model_name, text):
    """
    将一段文本转换为 L2 归一化的语义向量（核心 API）。

    ══════════════════════════════════════════════════════════════════════
    处理流程（4 步管线）
    ══════════════════════════════════════════════════════════════════════

      Step 1 — 模型切换检测
        如果请求的 model_name 与当前加载的模型不同：
          → 调用 _load_model() 加载新模型
          → 清空全部缓存（新旧模型向量空间不兼容）
        如果相同：跳过，直接复用当前模型。

      Step 2 — 空文本处理
        空文本或纯空白文本无法产生有意义的语义表示，
        返回与模型维度相同的全零向量（不影响后续点积结果）。

      Step 3 — 缓存查找
        以原始文本为 key 在 _cache 字典中查找。
        命中 → 直接返回缓存的 numpy 数组（零拷贝，极快）。

      Step 4 — 模型推理 + 缓存写入
        未命中 → 调用 _model.encode() 进行前向推理，
        设置 normalize_embeddings=True 确保 L2 归一化，
        将结果存入缓存后返回。

    ══════════════════════════════════════════════════════════════════════
    关于 L2 归一化的重要说明
    ══════════════════════════════════════════════════════════════════════

    normalize_embeddings=True 使输出的向量模长为 1（||v|| = 1）。
    这个属性使得两个归一化向量的点积在数学上等价于余弦相似度：

      cos(θ) = (A · B) / (||A|| × ||B||) = A · B   （当 ||A||=||B||=1 时）

    因此调用方可以直接用 np.dot(vec_a, vec_b) 得到相似度，
    无需额外做除法运算，效率更高且数值更稳定。

    参数:
        model_name (str): 嵌入模型标识名，如 'BAAI/bge-small-zh-v1.5'
                          也支持本地文件路径
        text       (str): 待编码的原始文本（中文/英文均可）

    返回:
        numpy.ndarray: L2 归一化的浮点向量（shape = [embedding_dim]）
                        维度数取决于具体模型：
                          - bge-small-zh-v1.5: 512 维
                          - bge-large-zh-v1.5: 1024 维
                        空文本返回全零向量（同维度）

    异常:
        RuntimeError: 模型加载失败时抛出（含详细的错误原因和建议）
    """
    global _model, _model_name, _cache

    # ---- Step 1) 模型切换检测 ----
    if model_name != _model_name:
        from sentence_transformers import SentenceTransformer  # 懒 import（见下方说明）
        try:
            _model = _load_model(model_name)
        except Exception as e:
            # 加载失败时的恢复策略：重置状态为"未加载"
            # 这样下次调用 encode() 时可以再次尝试（可能是临时网络问题）
            _model = None
            _model_name = None
            raise RuntimeError(
                f'无法加载嵌入模型 "{model_name}": {e}\n'
                f'请确认模型名称是否正确，以及网络连通性（已配置镜像 hf-mirror.com）。'
            )
        _model_name = model_name
        _cache.clear()   # 关键！不同模型的向量空间不可混用，必须全部清空

    # ---- Step 2) 空文本处理 ----
    if not text or not text.strip():
        # 返回与模型输出维度一致的全零向量
        # 这样后续的点积运算不会因维度不匹配而报错
        dim = _model.get_sentence_embedding_dimension()
        return np.zeros(dim)

    # ---- Step 3) 缓存查找 ----
    cache_key = text  # 直接用文本字符串作为缓存 key（简洁且确定性好）
    if cache_key in _cache:
        return _cache[cache_key]  # 缓存命中：零拷贝返回 numpy 数组引用

    # ---- Step 4) 模型推理 + 存入缓存 ----
    # normalize_embeddings=True: 输出 L2 归一化向量（模长=1）
    vec = _model.encode(text, normalize_embeddings=True)
    _cache[cache_key] = vec  # 写入缓存供后续复用
    return vec


def batch_encode(model_name, texts):
    """
    批量编码：对一组文本一次性进行向量推理（性能优化版）。

    ══════════════════════════════════════════════════════════════════════
    为什么批量比逐条快？
    ══════════════════════════════════════════════════════════════════════

    Transformer 模型的推理瓶颈主要在 GPU/CPU 的矩阵乘法运算。
    将多个文本拼成一个 batch 后：
      - 可以利用 GPU 的并行计算能力（一次矩阵乘法处理整个 batch）
      - 减少 Python → C++ 的跨语言调用次数（减少 overhead）
      - 对长序列模型来说，batch 推理通常比循环调用 encode() 快 3~10 倍

    ══════════════════════════════════════════════════════════════════════
    内部的缓存智能过滤
    ══════════════════════════════════════════════════════════════════════

    函数内部会自动将输入分为三类：
      1. 已缓存的文本 → 直接从 _cache 取结果，不参与推理
      2. 空文本       → 生成零向量，不参与推理
      3. 未缓存的非空文本 → 收集后统一进行 batch 推理

    这种「部分命中」优化确保即使大部分文本都已缓存过，
    也只需对少量新文本做推理，最大化缓存利用率。

    参数:
        model_name (str):    模型标识名
        texts      (list[str]): 待编码的文本列表

    返回:
        list[numpy.ndarray]: 与 texts 一一对应的归一化向量列表
                             （顺序不变，第 i 个输出对应第 i 个输入）
    """
    global _model, _model_name, _cache

    # 分类收集：区分已缓存、未缓存、空文本三种情况
    uncached_texts = []       # 需要推理的文本列表
    uncached_indices = []     # 对应在原数组中的索引位置
    results = [None] * len(texts)  # 预分配结果数组（用 None 占位）

    for i, t in enumerate(texts):
        if not t or not t.strip():
            # 空文本先标记，后面统一生成零向量
            uncached_texts.append(t)
            uncached_indices.append(i)
            continue
        if t in _cache:
            # 缓存命中：直接填入结果
            results[i] = _cache[t]
        else:
            # 未命中：收集起来准备批量推理
            uncached_texts.append(t)
            uncached_indices.append(i)

    # 所有文本都已有缓存 → 直接返回
    if not uncached_texts:
        return results

    # 确保模型已加载（如果需要的话会触发懒加载）
    if model_name != _model_name:
        encode(model_name, '')  # 用空字符串触发模型加载（轻量操作）

    # 核心步骤：批量推理（show_progress_bar=False 避免日志刷屏）
    # 返回的是 shape=[len(uncached_texts), embedding_dim] 的 2D numpy 数组
    vecs = _model.encode(uncached_texts, normalize_embeddings=True, show_progress_bar=False)

    # 将批量推理的结果回填到对应的位置
    for idx, vec in zip(uncached_indices, vecs):
        if not texts[idx] or not texts[idx].strip():
            # 空文本：生成对应维度的零向量
            dim = _model.get_sentence_embedding_dimension()
            results[idx] = np.zeros(dim)
        else:
            # 正常文本：存入缓存 + 填入结果
            _cache[texts[idx]] = vec
            results[idx] = vec

    return results


def pre_warm_cache(all_abilities, all_opportunities):
    """
    预热缓存：在应用启动时预计算所有需要的文本向量。

    ══════════════════════════════════════════════════════════════════════
    工作原理
    ══════════════════════════════════════════════════════════════════════

      1. 扫描 DIMENSIONS 注册表，找出所有 method='vector_semantic' 的维度
      2. 对每个向量维度：
         a. 从 MATCH_CONFIG 中获取该维度的模型名
         b. 遍历全部能力和机会数据，提取该维度引用的字段值
         c. 去重后得到唯一文本集合
         d. 调用 batch_encode() 批量编码并存入 _cache
      3. 打印统计信息：共预热了多少条文本，缓存了多少个条目

    ════════════════════════════════════════════════════════════════════
    性能影响分析
    ══════════════════════════════════════════════════════════════════════

    假设系统有 100 条能力 + 200 条机会，某向量维度引用 overview 字段：
      - 唯一文本数量约 ≤ 300 条（可能有重复）
      - batch_encode() 一次推理完成，GPU 上约需 2~5 秒（取决于模型大小）
      - 之后每次匹配请求直接读缓存，响应时间 < 1ms

    如果不做预热：
      - 第一次匹配请求需要实时推理，可能阻塞 0.5~2 秒
      - 后续请求逐渐变快（随着缓存积累），但用户体验不均匀

    参数:
        all_abilities     (list[dict]): 全部场景能力的完整数据列表
        all_opportunities (list[dict]): 全部场景机会的完整数据列表

    注意:
        - 此函数应在应用启动阶段（Flask before_first_request 或 CLI 入口处）调用
        - 如果没有任何 vector_semantic 维度，函数会立即返回（零开销）
        - 多个向量维度共用同一个缓存，后处理的维度可复用先处理的缓存命中
    """
    global _model, _model_name

    from .dimensions import DIMENSIONS

    # 收集所有 vector_semantic 类型的维度（非向量维度不需要预热）
    vector_dims = []
    for dim in DIMENSIONS:
        if dim.get('method') == 'vector_semantic':
            vector_dims.append(dim)

    # 系统中没有配置任何向量语义维度 → 跳过预热（零开销快速返回）
    if not vector_dims:
        print('[vector_tool] 无向量语义维度，跳过预热')
        return

    total_texts = 0  # 统计总预热条目数

    for dim in vector_dims:
        dim_id = dim['id']

        # 从 MATCH_CONFIG 获取该维度使用的模型名
        # 注意：这里不能在文件顶部 import engine（会导致循环依赖），
        # 所以用局部 import 解决
        from .engine import MATCH_CONFIG
        model_name = MATCH_CONFIG.get(f'{dim_id}_model_name', 'BAAI/bge-small-zh-v1.5')
        if not model_name:
            model_name = 'BAAI/bge-small-zh-v1.5'  # 安全兜底

        # 收集该维度引用的所有字段值的唯一文本集合
        # 使用 set 自动去重（相同文本只编码一次）
        texts = set()
        for item in all_abilities:
            for f in dim['ability_fields']:
                val = item.get(f, '')
                if val and val.strip():  # 过滤空值
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
        print(f'[vector_tool] 维度 {dim_id} ({dim["label"]})：'
              f'收集 {len(text_list)} 条唯一文本，开始批量编码...')

        # 确保目标模型已加载（如果当前模型不对则重新加载）
        if model_name != _model_name:
            print(f'[vector_tool] 加载模型: {model_name}')
            _model = _load_model(model_name)
            _model_name = model_name
            _cache.clear()  # 模型切换必须清空旧缓存

        # 批量推理（show_progress_bar=True 显示进度条，方便观察启动状态）
        vecs = _model.encode(text_list, normalize_embeddings=True, show_progress_bar=True)
        # 逐一写入缓存
        for text, vec in zip(text_list, vecs):
            _cache[text] = vec

        total_texts += len(text_list)
        print(f'[vector_tool] 维度 {dim_id} 预热完成：{len(text_list)} 条文本已缓存')

    print(f'[vector_tool] 全部预热完成：共 {total_texts} 条文本，缓存条目 {len(_cache)} 个')


def clear_cache():
    """
    手动清空全部向量缓存。

    典型使用场景：
      - 切换嵌入模型后确保不留旧数据（虽然 encode() 会自动清）
      - 内存紧张时主动释放缓存占用的内存
      - 测试/调试时重置状态

    注意：多数情况下不需要显式调用此函数，
         encode() 在检测到模型切换时会自动调用 _cache.clear()。
    """
    global _cache
    _cache.clear()


def is_model_loaded():
    """
    检查模型是否已加载到内存中。

    可用于：
      - API 端点查询系统状态
      - 决定是否需要提示用户"首次使用需要下载模型"

    返回:
        bool: True 表示模型已就绪可用，False 表示尚未加载
    """
    return _model is not None


def get_model_info():
    """
    获取当前模型的详细信息（用于监控和管理界面展示）。

    返回:
        dict|None: 模型信息字典，包含：
            - model_name (str):     当前模型标识名
            - dimension (int):      嵌入向量维度（如 512、1024）
            - cache_size (int):     当前缓存条目数
          若模型未加载则返回 None
    """
    if _model is None:
        return None
    return {
        'model_name': _model_name,
        'dimension': _model.get_sentence_embedding_dimension(),  # 输出向量维度
        'cache_size': len(_cache),                               # 缓存命中率参考指标
    }
