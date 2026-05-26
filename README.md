# 场景机会与能力智能匹配 Demo

基于**多维加权模型**的场景能力与场景机会自动匹配系统。支持双向匹配（能力→机会 / 机会→能力），匹配维度可动态增删，前端展示完整的匹配过程明细。

## 项目概述

- **数据源**：后台数据中的两张 Excel 表（场景能力 406 条、场景机会 1186 条）
- **后端**：Python Flask + 模块化 matcher 包
- **前端**：纯 HTML/CSS/JS，拆分为 state / api / render / main / add_dimension 五个模块
- **匹配算法**：多维加权模型——每个维度独立定义字段、算法、权重，综合评分 = Σ(维度得分 × 权重)

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | Flask (Python) |
| 数据读取 | pandas + openpyxl |
| 前端 | HTML5 + CSS3 + Vanilla JS (ES6) |
| 匹配算法 | 精确子串+大类归一化 / 中文 2-gram Jaccard 相似度 |
| 配置持久化 | JSON 文件（dimensions.json + config.json） |

## 项目结构

```
scenedemo/
├── app.py                      # Flask 应用入口，路由定义
├── requirements.txt            # Python 依赖
├── start.bat                   # 一键启动脚本 (Windows)
├── matcher/                    # 匹配引擎核心包
│   ├── __init__.py             # 包入口，统一导出所有公共接口
│   ├── data_loader.py          # Excel 数据加载与清洗
│   ├── normalizer.py           # 领域归一化映射（领域→大类）
│   ├── dimensions.py           # 匹配维度注册表（文件持久化版）
│   └── engine.py               # 匹配引擎（遍历注册表、加权求和）
├── static/                     # 前端静态文件
│   ├── index.html              # 主页面
│   ├── css/
│   │   ├── style.css           # 主样式表
│   │   └── add_dimension.css   # 添加维度模态框样式
│   └── js/
│       ├── state.js            # 全局状态管理（IIFE 模块）
│       ├── api.js              # API 请求层（封装所有 fetch）
│       ├── render.js           # DOM 渲染模块（列表/卡片/配置面板）
│       ├── main.js             # 主流程编排与事件绑定
│       └── add_dimension.js    # 添加维度模态框交互逻辑
├── 后台数据/                    # 源数据 + 持久化配置
│   ├── 场景能力数据列表.xlsx
│   ├── 场景机会数据列表.xlsx
│   ├── dimensions.json         # 匹配维度定义（运行时修改）
│   └── config.json             # 匹配参数配置（运行时修改）
├── README.md                   # 项目文档（本文件）
└── CHANGELOG.md                # 变更日志
```

## 快速启动

### 环境要求

- Python 3.10+（Conda 管理虚拟环境）
- conda

### 安装与运行

#### 方式一：一键启动（推荐）

双击 `start.bat`，脚本会自动检查/创建 conda 虚拟环境 `scenedemo` 并安装依赖后启动。

#### 方式二：手动启动

```bash
# 创建并激活 conda 虚拟环境
conda create -n scenedemo python=3.10 -y
conda activate scenedemo

# 安装 PyTorch（CPU 版）
conda install pytorch cpuonly -c pytorch -y

# 安装其他依赖
pip install flask sentence-transformers

# 启动服务
python app.py
```

启动后访问 **http://127.0.0.1:5000**。

## 匹配算法

### 综合评分公式

```
total_score = Σ (dim_score × dim_weight)  对所有注册的维度求和
```

维度由 `后台数据/dimensions.json` 定义，默认 3 个维度：

| 维度 | 方法 | 能力侧字段 | 机会侧字段 | 默认权重 |
|------|------|-----------|-----------|---------|
| 领域匹配 | string_match | domain | welcome | 0.4 |
| 文本匹配 | bigram | overview, target_customer | overview, welcome | 0.3 |
| 区域匹配 | string_match | district | area | 0.3 |

### 匹配方法说明

#### string_match（精确子串 + 大类归一化）

| 匹配方式 | 得分 | 说明 |
|---|---|---|
| 精确命中 | 1.0 | 能力侧字段值作为子串出现在机会侧字段中 |
| 大类近似 | 0.5 | 归一化后属于同一大类（通过 `normalizer.py` 映射表） |
| 未命中 | 0.0 | 无匹配关系 |

#### bigram（中文 2-gram Jaccard 相似度）

```
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

- 提取两侧文本的中文 bigram 集合
- 截取前 N 字（可配置，默认 300）避免长文本稀释相似度
- 返回重叠 bigram 列表供前端展示

## API 接口

> 所有接口基础路径：`http://127.0.0.1:5000`

---

### 1. 列表接口

#### `GET /api/abilities`

返回全部场景能力摘要列表。

**请求参数：** 无

**返回格式：**
```json
[
  {
    "id": 1,
    "name": "智慧交通管理平台",
    "company": "某某科技公司",
    "domain": "人工智能（软件）",
    "district": "江宁开发区"
  },
  ...
]
```

#### `GET /api/opportunities`

返回全部场景机会摘要列表。

**请求参数：** 无

**返回格式：**
```json
[
  {
    "id": 1,
    "name": "城市交通信号优化项目",
    "domain": "数字民生服务",
    "sub_domain": "智慧交通",
    "area": "建邺区"
  },
  ...
]
```

---

### 2. 匹配接口

#### `GET /api/match/ability/<id>`

为指定场景能力匹配 Top N 条场景机会。

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 场景能力的序号 ID |

**返回格式：**
```json
{
  "config": {
    "domain_weight": 0.4,
    "text_weight": 0.3,
    "region_weight": 0.3,
    "top_n": 3,
    "text_max_length": 300
  },
  "source": {
    "id": 1,
    "name": "智慧交通管理平台",
    "company": "某某科技公司",
    "domain": "人工智能（软件）",
    "district": "江宁开发区",
    "overview": "...",
    "target_customer": "..."
  },
  "matches": [
    {
      "target": {
        "id": 5,
        "name": "城市交通信号优化项目",
        "domain": "数字民生服务",
        "area": "建邺区",
        "overview": "...",
        "sub_domain": "智慧交通",
        "welcome": "..."
      },
      "total_score": 0.62,
      "dimension_scores": {
        "domain": { "score": 0.5, "detail": "大类近似匹配...", "weight": 0.4 },
        "text": { "score": 0.3, "detail": {...}, "weight": 0.3 },
        "region": { "score": 0.0, "detail": "未命中...", "weight": 0.3 }
      },
      "domain_score": 0.5,
      "domain_match_detail": "大类近似匹配...",
      "text_score": 0.3,
      "text_match_detail": {...},
      "region_score": 0.0,
      "region_match_detail": "未命中...",
      "source_fields": {
        "产品名称": "智慧交通管理平台",
        "所属产业领域": "人工智能（软件）",
        "所属区": "江宁开发区",
        "能力概述": "...",
        "意向对接客户": "..."
      },
      "target_fields": {
        "应用场景项目名称": "城市交通信号优化项目",
        "应用场景所属领域": "数字民生服务",
        "应用场景所属区域": "建邺区",
        "应用场景概述": "...",
        "欢迎合作方向": "..."
      }
    }
  ]
}
```

**返回字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `config` | object | 当前匹配参数配置 |
| `source` | object | 源侧（被匹配方）摘要信息 |
| `matches` | array | Top N 条最佳匹配结果，按 total_score 降序 |
| `matches[].target` | object | 目标侧（匹配到的一方）摘要信息 |
| `matches[].total_score` | float | 综合加权得分（0~1） |
| `matches[].dimension_scores` | object | v3 结构化维度得分（键为 dim_id） |
| `matches[].{dim_id}_score` | float | v2 兼容扁平字段：某维度的原始得分 |
| `matches[].{dim_id}_match_detail` | str/object | v2 兼容扁平字段：某维度的匹配详情 |
| `matches[].source_fields` | object | 源侧参与匹配的字段值（中文标签→值） |
| `matches[].target_fields` | object | 目标侧参与匹配的字段值（中文标签→值） |

#### `GET /api/match/opportunity/<id>`

为指定场景机会匹配 Top N 条场景能力（反向匹配）。

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 场景机会的序号 ID |

**返回格式：** 与 `GET /api/match/ability/<id>` 相同，只是 source 为机会信息，target 为能力信息。

额外逻辑：当领域（domain）维度得分为 0 时，会自动尝试用机会的 domain 字段去匹配能力的 target_customer（意向对接客户）字段作为兜底。

---

### 3. 维度管理接口

#### `GET /api/dimensions`

返回维度元信息 + 当前配置值。

**请求参数：** 无

**返回格式：**
```json
{
  "config": {
    "domain_weight": 0.4,
    "text_weight": 0.3,
    "region_weight": 0.3,
    "top_n": 3,
    "text_max_length": 300
  },
  "dimensions": [
    {
      "id": "domain",
      "label": "领域匹配",
      "weight_key": "domain_weight",
      "weight": 0.4,
      "score_label": "领域",
      "icon": "🔍",
      "color": "#3B82F6",
      "detail_type": "text",
      "params": {}
    },
    {
      "id": "text",
      "label": "文本匹配",
      "weight_key": "text_weight",
      "weight": 0.3,
      "score_label": "文本",
      "icon": "📐",
      "color": "#22C55E",
      "detail_type": "bigram",
      "params": {
        "max_length": {
          "default": 300,
          "label": "文本截取长度",
          "type": "int",
          "min": 50,
          "max": 2000,
          "step": 10,
          "slider_max": 2000,
          "config_key": "text_max_length",
          "value": 300
        }
      }
    },
    {
      "id": "region",
      "label": "区域匹配",
      "weight_key": "region_weight",
      "weight": 0.3,
      "score_label": "区域",
      "icon": "📍",
      "color": "#F59E0B",
      "detail_type": "text",
      "params": {}
    }
  ]
}
```

#### `POST /api/dimensions`

添加新匹配维度。

**请求头：** `Content-Type: application/json`

**请求体：**
```json
{
  "label": "投资匹配",
  "method": "string_match",
  "ability_fields": ["effect"],
  "opportunity_fields": ["investment"],
  "method_labels": {
    "ability": "能力效果",
    "opportunity": "投资金额"
  }
}
```

**请求体字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `label` | string | 是 | 维度显示名称，如"投资匹配" |
| `method` | string | 是 | 匹配方法，可选 `string_match` 或 `bigram` |
| `ability_fields` | array | 否 | 能力侧字段名列表，如 `["effect"]`。默认 `[]` |
| `opportunity_fields` | array | 否 | 机会侧字段名列表，如 `["investment"]`。默认 `[]` |
| `method_labels` | object | 否 | 仅 `string_match` 方法使用，定义详情中的中文标签 |
| `method_labels.ability` | string | 否 | 能力侧字段的中文标签，如"能力效果"。默认"能力值" |
| `method_labels.opportunity` | string | 否 | 机会侧字段的中文标签，如"投资金额"。默认"机会值" |
| `icon` | string | 否 | 自定义图标 emoji，默认由方法决定 |
| `color` | string | 否 | 自定义颜色 HEX 值，默认由方法决定 |

后端自动生成的字段（无需传入）：
- `id`：自动分配 `dim_N` 格式
- `weight_key`：自动生成 `{id}_weight` 格式
- `default_weight`：固定为 `0.0`（用户需在配置面板手动调整）
- `detail_type`、`icon`、`color`、`params`：由匹配方法决定默认值

**成功返回 (200)：**
```json
{
  "success": true,
  "message": "维度「投资匹配」已添加",
  "dimension": {
    "id": "dim_4",
    "label": "投资匹配",
    "method": "string_match",
    "weight_key": "dim_4_weight",
    "ability_fields": ["effect"],
    "opportunity_fields": ["investment"],
    "detail_type": "text",
    "icon": "🔍",
    "color": "#3B82F6",
    "default_weight": 0.0,
    "score_label": "投资匹配",
    "params": {}
  }
}
```

**失败返回 (400)：**
```json
{
  "error": "缺少必需字段：label"
}
```

#### `DELETE /api/dimensions/<dim_id>`

删除指定匹配维度。

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `dim_id` | string | 维度 ID，如 `"domain"` 或 `"dim_4"` |

**限制：** 至少保留 1 个维度。如果只剩 1 个维度，删除请求会返回 400 错误。

**成功返回 (200)：**
```json
{
  "success": true,
  "message": "维度「投资匹配」已删除"
}
```

**失败返回 (400)：**
```json
{
  "error": "至少保留 1 个匹配维度，删除失败"
}
```

#### `GET /api/dimensions/methods`

返回可用的匹配方法及其默认参数。

**请求参数：** 无

**返回格式：**
```json
{
  "string_match": {
    "default_detail_type": "text",
    "default_params": {},
    "default_icon": "🔍",
    "default_color": "#3B82F6"
  },
  "bigram": {
    "default_detail_type": "bigram",
    "default_params": {
      "max_length": {
        "default": 300,
        "label": "文本截取长度",
        "hint": "文本匹配时截取前 N 个中文字符，避免超长文本稀释相似度。",
        "type": "int",
        "min": 50,
        "max": 2000,
        "step": 10,
        "slider_max": 2000
      }
    },
    "default_icon": "📐",
    "default_color": "#22C55E"
  }
}
```

---

### 4. 字段列表接口

#### `GET /api/fields`

返回能力侧和机会侧可用于匹配的字段列表。前端添加维度时选择字段的下拉框来源。

**请求参数：** 无

**返回格式：**
```json
{
  "ability": ["domain", "district", "overview", "highlight", "effect", "target_customer"],
  "opportunity": ["domain", "sub_domain", "area", "overview", "welcome", "category", "unit", "investment"]
}
```

**说明：** 如需新增可选字段，需同步修改 `app.py` 中的此接口和 `data_loader.py` 中的字段映射。

---

### 5. 参数配置接口

#### `GET /api/config`

返回当前匹配参数配置。

**请求参数：** 无

**返回格式：**
```json
{
  "domain_weight": 0.4,
  "text_weight": 0.3,
  "region_weight": 0.3,
  "top_n": 3,
  "text_max_length": 300
}
```

说明：权重 key 由维度注册表动态决定，`top_n` 和维度私有参数（如 `text_max_length`）始终存在。

#### `POST /api/config`

更新匹配参数配置。

**请求头：** `Content-Type: application/json`

**请求体（只传需要更新的字段）：**
```json
{
  "domain_weight": 0.5,
  "text_weight": 0.5,
  "top_n": 5
}
```

**可配置参数：**

| 参数 | 类型 | 范围 | 说明 |
|------|------|------|------|
| `{dim_id}_weight` | float | 0~1 | 某维度的匹配权重（如 `domain_weight`） |
| `top_n` | int | 1~20 | 返回前 N 条最佳匹配 |
| `{dim_id}_{param}` | int | 由维度定义 | 维度私有参数（如 `text_max_length`） |

**校验规则：**
1. 权重值必须在 0~1 之间
2. `top_n` 必须是 ≥1 的整数
3. 维度私有参数按 `dimensions.json` 中定义的 type/min/max 校验
4. 如果权重之和 ≠ 1.0，自动等比例缩放至和为 1

**成功返回 (200)：** 更新后的完整配置（格式同 GET /api/config）

**失败返回 (400)：**
```json
{
  "error": "domain_weight 必须在 0~1 之间"
}
```

---

## 前端界面

### 功能

- **双模式切换**：能力→机会（默认）/ 机会→能力
- **左侧列表**：按序号展示全部条目，点击选中
- **右侧匹配卡片**：
  - 📋 匹配字段对照表（左右两栏对照）
  - 各维度匹配详情（精确/大类/未命中 + 上下文，或 bigram 统计 + 重叠关键词）
  - 📊 多色进度条（每个维度一个色块，宽度 = × 权重后的贡献）
- **配置面板**（⚙️ 按钮打开）：
  - 动态权重滑块（0~100%，0.1% 精度）
  - 自由 / 联动 两种调整策略
  - 维度私有参数调整
  - ➕ 添加匹配维度 / 🗑 删除维度

### 交互

- 点击左侧列表项 → 自动发起匹配请求 → 右侧展示 Top N 结果
- 切换模式按钮 → 刷新列表 → 清空匹配结果
- 修改配置并保存 → 自动重新匹配

---

## 领域归一化

`matcher/normalizer.py` 维护领域→大类映射表，处理跨表命名不一致：

| 原始值 | 归一化 |
|---|---|
| 人工智能（软件）/ 人工智能（硬件） | 人工智能 |
| 智能制造装备 / 机器人 | 智能制造 |
| 智能网联新能源汽车 | 新能源汽车 |
| 产业转型升级 / 六大新兴产业集群 / 其他 | 综合 |

## 架构设计要点

### 维度注册表模式

匹配维度不是硬编码在引擎中，而是由 `dimensions.py` 集中定义：

```
dimensions.json (持久化文件)
     ↓ 启动时 _load_dimensions()
DIMENSIONS 列表 (内存，含 compute 闭包)
     ↓ 引擎循环遍历
compute(a_vals, o_vals, params) → (score, detail)
```

新增维度只需：
1. 在 `METHOD_REGISTRY` 中注册匹配方法（如已存在则跳过）
2. 前端通过「添加匹配维度」UI 操作，自动调用 `POST /api/dimensions`
3. 引擎无需任何改动

### 配置持久化

- `dimensions.json`：维度定义（ID、方法、字段映射等），增删时自动保存
- `config.json`：匹配参数（权重、TopN、私有参数），每次 `/api/config` POST 保存

### 前/后端数据流

```
用户点击列表项
  → main.js 事件委托
    → api.js 调用 fetchMatchForAbility(id)
      → app.py /api/match/ability/<id>
        → engine.py _compute_dimension_scores()
          → 遍历 DIMENSIONS
            → dim['compute'](a_vals, o_vals, params)
              → _score_string_match / _score_text
        → _build_match_response() 组装响应
      → render.js renderCards() 渲染卡片
```

## License

内部 Demo 项目。
