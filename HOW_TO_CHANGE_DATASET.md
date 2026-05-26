# 如何更换数据集

本文档说明将当前「场景能力」与「场景机会」数据集替换为全新数据集时，需要修改哪些文件、各文件改什么、以及验证流程。

---

## 目录

1. [项目架构速览](#1-项目架构速览)
2. [总体流程（5 步）](#2-总体流程5-步)
3. [步骤 1：准备新 Excel 文件](#3-步骤-1准备新-excel-文件)
4. [步骤 2：修改 data_loader.py](#4-步骤-2修改-data_loaderpy)
5. [步骤 3：修改 field_mapping.json](#5-步骤-3修改-field_mappingjson)
6. [步骤 4：修改 schema.py](#6-步骤-4修改-schemapy)
7. [步骤 5：修改 app.py（如需要）](#7-步骤-5修改-apppy如需要)
8. [其他可能需要调整的文件](#8-其他可能需要调整的文件)
9. [验证清单](#9-验证清单)
10. [常见问题](#10-常见问题)

---

## 1. 项目架构速览
detail_labels
```
scenedemo/
├── app.py                          ← Flask 入口，指定 Excel 文件名和 Sheet 名
├── matcher/
│   ├── data_loader.py              ← 从 Excel 读取数据，Excel列名→dict key 映射
│   ├── schema.py                   ← 字段映射默认值 + 工具函数
│   ├── engine.py                   ← 匹配算法（与具体字段名无关，由 schema 驱动）
│   ├── normalizer.py               ← 领域关键词归一化表
│   └── __init__.py                 ← 包导出
├── 后台数据/
│   ├── 场景能力数据列表.xlsx        ← 能力表 Excel（可替换）
│   ├── 场景机会数据列表.xlsx        ← 机会表 Excel（可替换）
│   ├── field_mapping.json          ← 场景→字段映射（运行时可持久化）
│   └── config.json                 ← 匹配参数配置
└── static/                         ← 前端页面
```

**数据流**：
```
Excel 文件
  → data_loader.py  读取，产出 dict[列名英文key] 格式
  → schema.py       根据 field_mapping.json 决定每个 API 返回哪些字段
  → engine.py       按字段名从 dict 取值做匹配计算
  → app.py          路由组装返回 JSON
```

**核心设计原则**：
- `data_loader.py` 定义了「Excel 列名 → Python dict key」的映射（硬编码）。
- `field_mapping.json` 定义了「每个场景需要哪些 Python dict key」（可配置）。
- `schema.py` 中的工具函数从 item dict 里按 key 取值，key 就是 dict 的真实键名。
- 除了 `data_loader.py`，**不知道 Excel 的列名叫什么**。只要 `data_loader.py` 输出的 dict key 与 `field_mapping.json` 中的字段名一致即可。

---

## 2. 总体流程（5 步）

| 步骤 | 做什么 | 改什么文件 | 难度 |
|------|--------|-----------|------|
| 1 | 准备新 Excel，搞清楚列名和内容 | 无（准备工作） | ⭐ |
| 2 | 修改数据加载器，Excel列名→dict key | `matcher/data_loader.py` | ⭐⭐ |
| 3 | 修改字段映射，定义各场景用哪些字段 | `后台数据/field_mapping.json` | ⭐⭐⭐ |
| 4 | ~~修改 Python 默认映射~~ 无需操作 | `matcher/schema.py`（无需改） | — |
| 5 | 如文件名/Sheet名变了，修改入口 | `app.py` | ⭐ |

> **提示**：如果新数据集的列名和当前完全一样，只需要替换 Excel 文件即可，不需要修改代码。如果只是改 Excel 文件名或 Sheet 名，只需做步骤 5。`schema.py` **任何情况下都不需要修改**，它会自适应 `field_mapping.json` 的内容。

---

## 3. 步骤 1：准备新 Excel 文件

### 3.1 文件要求

- 两个 `.xlsx` 文件：一个能力表、一个机会表
- 放在 `后台数据/` 目录下
- 第一行必须是**表头**（列名），从第二行开始是数据
- 建议有一列作为唯一标识（如序号/ID），用于前后端索引

### 3.2 列名规范

列出新数据集的**所有列名**，例如：

| Excel 列名 | 含义 | 示例值 |
|------------|------|--------|
| 序号 | 唯一 ID | 1 |
| 产品名称 | 能力/机会名称 | 智能客服系统 |
| 企业名称 | 所属企业 | XX科技有限公司 |
| 所属领域 | 产业领域 | 人工智能 |
| 能力描述 | 概述文本 | 基于大模型的... |
| ... | ... | ... |

你会频繁用到这个对照表，建议先整理好。

---

## 4. 步骤 2：修改 `data_loader.py`

文件路径：`matcher/data_loader.py`

这个文件是「**唯一**」知道 Excel 列名的地方。它负责把 Excel 的列名映射为 Python dict 的 key。

### 4.1 修改 `load_abilities()` 函数（约第 38 行）

找到函数中 `ability = { ... }` 的赋值部分，将每个 key 的值改为从新 Excel 列名取值。

**修改前**（当前代码）：
```python
ability = {
    'id':              int(row.get('序号', 0)),
    'name':            _safe_str(row.get('产品名称')),
    'company':         _safe_str(row.get('企业名称')),
    'domain':          _safe_str(row.get('所属产业领域')),
    'overview':        _safe_str(row.get('能力概述')),
    'highlight':       _safe_str(row.get('创新亮点')),
    'effect':          _safe_str(row.get('应用实效')),
    'target_customer': _safe_str(row.get('意向对接客户')),
}
```

**修改后**（示例 - 假设新 Excel 列名变了）：
```python
ability = {
    'id':              int(row.get('序号', 0)),           # Excel 列名
    'name':            _safe_str(row.get('产品名称')),     # Excel 列名
    'company':         _safe_str(row.get('供应商')),       # 新列名
    'domain':          _safe_str(row.get('技术领域')),     # 新列名
    'overview':        _safe_str(row.get('详细描述')),     # 新列名
    'highlight':       _safe_str(row.get('亮点')),         # 新列名
    'effect':          _safe_str(row.get('效果')),         # 新列名
    'target_customer': _safe_str(row.get('目标客户群')),   # 新列名
}
```

> **关键**：dict 的 **key**（`'id'`、`'name'`、`'domain'` 等）是给后端其他模块用的 **内部字段名**。这些 key 的命名**你想叫什么都可以**——但你需要确保后续 `field_mapping.json` 和 `schema.py` 中使用的是**同样的 key 名**。
>
> **建议**：如果新旧数据集概念相似，保持 key 名不变可极大减少后续修改量。如果要新增字段（如 `'price'`），则需要同步在 `field_mapping.json` 和 `schema.py` 中添加。

### 4.2 修改 `load_opportunities()` 函数（约第 82 行）

同理，修改 `opp = { ... }` 部分：

```python
opp = {
    'id':         int(row.get('序号', 0)),
    'name':       _safe_str(row.get('应用场景项目名称')),   # 按需改
    'domain':     _safe_str(row.get('应用场景所属领域')),   # 按需改
    'sub_domain': _safe_str(row.get('应用场景细分领域')),   # 按需改
    'area':       _safe_str(row.get('应用场景所属区域')),   # 按需改
    'overview':   _safe_str(row.get('应用场景概述')),       # 按需改
    'welcome':    _safe_str(row.get('欢迎合作方向')),       # 按需改
    'category':   _safe_str(row.get('场景分类')),           # 按需改
    'unit':       _safe_str(row.get('应用场景搭建单位')),   # 按需改
    'investment': _safe_str(row.get('项目投资方式')),       # 按需改
}
```

### 4.3 也检查一下 Sheet 名

`pd.read_excel(..., sheet_name='创新产品发布审核列表')` 这里的 Sheet 名要和 Excel 中实际 Sheet 名一致。

---

## 5. 步骤 3：修改 `field_mapping.json`

文件路径：`后台数据/field_mapping.json`

这是**字段映射配置文件**。它告诉系统「每个场景需要哪些字段」，运行时可被前端修改并持久化。

### 5.1 理解 JSON 结构

```json
{
  "ability": {
    "keys": ["id", "name", "company", ...],      // 所有字段名列表（纯列表）
    "scenes": {                                    // 各场景需要哪些字段
      "list_summary": ["id", "name", ...],
      "match_source": [...],
      "match_target": [...],
      ...
    },
    "detail_labels": {                             // 字段名 → 中文标签
      "name": "产品名称",
      ...
    },
    "frontend_list": [                             // 前端列表渲染配置
      {"role": "title", "label": "产品名称", "key": "name"},
      ...
    ],
    "table_label": "场景能力数据列表",
    "card_source_subtitle": "company"
  },
  "opportunity": { ... }
}
```

### 5.2 修改清单

根据你在步骤 2 中定义的 dict key（内部字段名），逐一更新以下内容：

#### (a) `keys` 列表
把列表中的字段名替换为你在 `data_loader.py` 中定义的 dict key：

```json
"keys": ["id", "name", "company", "new_field", ...]
```

#### (b) `scenes` 中各场景的字段列表
每个场景是一个字段名列表。根据新数据集的语义，调整每个场景包含哪些字段：

| 场景 | 作用 | 示例 |
|------|------|------|
| `list_summary` | 列表页显示的字段 | `["id", "name", "company", "domain"]` |
| `match_source` | 作为匹配的源数据 | 能力匹配机会时能力的字段列表 |
| `match_target` | 作为匹配的目标数据 | 匹配结果中目标侧的字段列表 |
| `detail_fields` | 匹配明细展示 | 哪些字段在字段对照表中显示 |
| `text_fields` | 参与文本匹配 | 哪些字段拼接后做 bigram Jaccard 计算 |
| `domain_field` | 领域匹配字段 | 用于领域关键词匹配的字段名 |
| `id_field` | ID 字段 | 路由参数用的字段名 |
| `name_field` | 名称字段 | 名称字段名 |

**如果你新增了字段**，需要决定它属于哪些场景。例如新增了一个 `'price'` 字段，你可能把它加到 `match_target` 和 `detail_fields` 中。

#### (c) `detail_labels`（中文标签）
key 为字段名，value 为前端展示的中文标签：

```json
"detail_labels": {
  "name": "产品名称",
  "domain": "技术领域",
  "price": "参考价格",
  ...
}
```

#### (d) `frontend_list`（前端列表渲染）
决定前端列表页每个卡片展示哪些信息。每个对象有三个属性：

```json
{
  "role": "title",       // 角色：title=主标题, subtitle=副标题, tag=标签, id=序号
  "label": "产品名称",    // 前端列标题
  "key": "name"          // 对应的字段名（dict key）
}
```

- `role: "id"` → 序号列（通常不变）
- `role: "title"` → 卡片主标题（通常是 name）
- `role: "subtitle"` → 卡片副标题（通常是 company 或 area）
- `role: "tag"` → 卡片标签（通常是 domain）

#### (e) `table_label` 和 `card_source_subtitle`
- `table_label`：页面顶部显示的表名
- `card_source_subtitle`：匹配结果卡片中源信息的副标题字段名

---

## 6. 步骤 4：`schema.py` 无需修改

`matcher/schema.py` 中有两个地方曾经需要手动维护：

### 6.1 `_DEFAULT_MAPPING` — 无需修改

`_DEFAULT_MAPPING` 仅在 `field_mapping.json` **不存在**时作为兜底使用。只要 `field_mapping.json` 存在（做过步骤 3），该默认值就完全被绕过。

> 换数据集时可以完全忽略这个变量。

### 6.2 `_get_tables_meta()` — 已改为自适应，无需修改

该函数现在**完全由 `field_mapping.json` 驱动**，自动推导每个字段的角色标记：

| 字段元数据 | 推导来源 |
|-----------|---------|
| `key` / `label` | `keys` 列表 + `detail_labels` |
| `type` | 是否等于 `id_field`（int/str） |
| `match` | 是否在 `detail_fields` 场景 |
| `text_source` | 是否在 `text_fields` 场景 |
| `domain_source` | 是否等于 `domain_field` |
| `api_list` / `front_list` | 是否在 `list_summary` 场景 |
| `api_detail` | 是否在 `match_target` 场景 |
| `front_card` | 是否出现在 `frontend_list` |

换数据集后 `/metadata` 页面会**自动反映新字段的参与关系**，无需任何额外操作。



---

## 7. 步骤 5：修改 `app.py`（如需要）

文件路径：`app.py`

### 7.1 Excel 文件名变了？

找到这两行（约第 86-89 行）：

```python
ALL_ABILITIES = load_abilities(os.path.join(DATA_DIR, '场景能力数据列表.xlsx'))
ALL_OPPORTUNITIES = load_opportunities(os.path.join(DATA_DIR, '场景机会数据列表.xlsx'))
```

把文件名改为新文件名：
```python
ALL_ABILITIES = load_abilities(os.path.join(DATA_DIR, '新能力表.xlsx'))
ALL_OPPORTUNITIES = load_opportunities(os.path.join(DATA_DIR, '新机会表.xlsx'))
```

### 7.2 Sheet 名变了？

如果你已经在 `data_loader.py` 中直接修改了 `sheet_name` 参数，这里不需要动。但如果你想让 Sheet 名可配置，可以在 `app.py` 中传递参数——当前设计是硬编码在 `data_loader.py` 中的。

### 7.3 通常不需要修改的部分

- 所有 API 路由逻辑 — 它们通过 `build_scene_dict()` 等 schema 工具函数取值，与具体字段名解耦
- CORS 配置
- 匹配参数配置路由

---

## 8. 其他可能需要调整的文件

### 8.1 `matcher/normalizer.py` — 领域归一化表

如果新数据集的领域分类体系变了，需要更新 `DOMAIN_MAP` 字典。它定义了领域关键词的归一化映射：

```python
DOMAIN_MAP = {
    '人工智能': '人工智能',
    'AI': '人工智能',
    '大数据': '大数据',
    # ... 按新数据集的领域术语调整
}
```

### 8.2 `matcher/engine.py` — 匹配逻辑

`engine.py` 中的匹配逻辑通过 `schema.py` 的工具函数取值，不直接引用字段名，**通常不需要修改**。但以下情况例外：

- 如果你在匹配条件上新增了匹配维度（如新增价格匹配），需要修改引擎
- 如果你改变了文本拼接的逻辑（当前是 `text_fields` 拼起来），可以在 schema 层面通过调整 `text_fields` 场景实现，不需要改引擎

### 8.3 `后台数据/config.json`

匹配参数（权重、Top N、文本截取长度），数据集变化一般不影响。如果需要调整默认参数，直接改这个文件。

### 8.4 前端文件（`static/` 目录）

前端通过 `/api/schema` 和 `/api/mapping` 接口动态获取字段信息，**通常不需要修改**。

但如果你改变了以下内容，可能需要调整前端：
- 卡片样式逻辑变了（如新增了角色类型）
- 列表列数变了（如从 4 列变 5 列）

---

## 9. 验证清单

完成修改后，按以下顺序逐项检查：

### 9.1 启动验证

```bash
python app.py
```

应该看到：
```
[schema] 能力表字段注册：['id', 'name', ...]
[schema] 机会表字段注册：['id', 'name', ...]
数据加载完成：X 条能力，Y 条机会
```

如果报错 `KeyError`，说明 `data_loader.py` 中的 Excel 列名没写对。

### 9.2 API 验证

浏览器访问以下接口，确认返回数据正确：

| 接口 | 检查点 |
|------|--------|
| `http://127.0.0.1:5000/api/abilities` | 返回列表，每个对象包含预期的字段 |
| `http://127.0.0.1:5000/api/opportunities` | 同上 |
| `http://127.0.0.1:5000/api/schema` | 返回的 `frontend`、`mapping`、`tables` 数据完整 |
| `http://127.0.0.1:5000/api/mapping` | 返回的 `field_mapping.json` 内容正确 |
| `http://127.0.0.1:5000/api/match/ability/1` | 匹配结果包含 source、matches、config |
| `http://127.0.0.1:5000/api/match/opportunity/1` | 反向匹配正常 |

### 9.3 前端验证

打开 `http://127.0.0.1:5000`：

- 列表页正常加载
- 卡片显示字段正确
- 点击匹配，结果页正常展示
- 字段对照表正常显示中文标签
- `/metadata` 页面正常显示字段元数据

### 9.4 映射持久化验证

1. 访问 `http://127.0.0.1:5000/api/mapping` 确认映射正确
2. 用 POST 修改一个场景的字段列表
3. 再次 GET 确认已更新
4. 重启服务，确认修改被保留

---

## 10. 常见问题

### Q1：我只想增加一个新字段，不想改数据集，怎么做？

1. 在 `data_loader.py` 中添加新字段的读取
2. 在 `field_mapping.json` 中把新字段加入 `keys` 列表和需要它的 `scenes`（以及 `detail_labels`、`frontend_list` 如需要）
3. 重启服务，`/metadata` 页面会自动反映新字段的参与关系

### Q2：新旧数据集的列名完全一样，但内容不同？

直接替换 `后台数据/` 下的 `.xlsx` 文件即可，不需要改任何代码。重启服务即可看到新数据。

### Q3：我只想换一个表（如只换能力表），另一个保持不变？

只修改对应的 `load_abilities()` 或 `load_opportunities()` 函数，以及对应的 `field_mapping.json` 和 `schema.py` 中对应表的定义。

### Q4：数据加载报 `KeyError`？

检查 `data_loader.py` 中 `row.get('Excel列名')` 的列名是否与 Excel 表头完全一致（包括空格、全角/半角符号等）。

### Q5：匹配结果异常（全部 0 分或全部满分）？

检查 `field_mapping.json` 中的 `text_fields` 和 `domain_field` 配置是否正确指向了有内容的字段。

---

*最后更新：2026-05-25*
