# 场景机会与能力智能匹配 Demo

基于**加权双因子模型**的场景能力与场景机会自动匹配系统。支持双向匹配（能力→机会 / 机会→能力），前端展示完整的匹配过程明细。

## 项目概述

- **数据源**：后台数据中的两张 Excel 表（场景能力 406 条、场景机会 1186 条）
- **后端**：Python Flask + 模块化 matcher 包
- **前端**：纯 HTML/CSS/JS，拆分为 state / api / render / main 四个模块
- **匹配算法**：加权双因子模型（领域精确/大类匹配 + 中文 2-gram Jaccard 文本相似度）

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | Flask (Python) |
| 数据读取 | pandas + openpyxl |
| 前端 | HTML5 + CSS3 + Vanilla JS (ES6) |
| 匹配算法 | 领域子串/归一化匹配 + 2-gram Jaccard |

## 项目结构

```
scenedemo/
├── app.py                      # Flask 应用入口，路由定义
├── requirements.txt            # Python 依赖
├── start.bat                   # 一键启动脚本 (Windows)
├── matcher/                    # 匹配引擎核心包
│   ├── __init__.py             # 包入口，统一导出
│   ├── data_loader.py          # Excel 数据加载与清洗
│   ├── normalizer.py           # 领域归一化映射
│   └── engine.py               # 匹配算法引擎（v2 含详细明细）
├── static/                     # 前端静态文件
│   ├── index.html              # 主页面
│   ├── css/
│   │   └── style.css           # 样式表
│   └── js/
│       ├── state.js            # 全局状态管理
│       ├── api.js              # API 请求层
│       ├── render.js           # DOM 渲染模块
│       └── main.js             # 主流程编排与事件绑定
├── 后台数据/                    # 源数据文件
│   ├── 场景能力数据列表.xlsx
│   └── 场景机会数据列表.xlsx
├── README.md                   # 项目文档（本文件）
└── CHANGELOG.md                # 变更日志
```

## 快速启动

### 环境要求

- Python 3.7+
- pip

### 安装与运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python app.py
```

或双击 `start.bat`（Windows 一键启动）。

启动后访问 **http://127.0.0.1:5000**。

## 匹配算法

### 综合评分公式

```
total_score = domain_score × DOMAIN_WEIGHT + text_score × TEXT_WEIGHT
```

默认权重：领域 `0.6` + 文本 `0.4`（可通过 `/api/config` 动态调整）。

### 领域得分 (domain_score)

| 匹配方式 | 得分 | 说明 |
|---|---|---|
| 精确命中 | 1.0 | 能力领域关键词作为子串出现在机会「欢迎合作方向」中 |
| 大类近似 | 0.5 | 归一化后属于同一大类（通过 `normalizer.py` 映射表） |
| 未命中 | 0.0 | 无匹配关系 |

### 文本得分 (text_score)

中文 2-gram Jaccard 相似度：

```
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

- 提取两侧文本的中文 bigram 集合
- 截取前 300 字（可配置）避免长文本稀释相似度
- 返回重叠 bigram 列表供前端展示

## API 接口

### 列表接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/abilities` | 返回全部场景能力摘要列表 |
| GET | `/api/opportunities` | 返回全部场景机会摘要列表 |

### 匹配接口（v2 含详细明细）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/match/ability/<id>` | 为指定能力匹配 Top3 机会 |
| GET | `/api/match/opportunity/<id>` | 为指定机会匹配 Top3 能力 |

返回字段（v2）：
- `config` — 当前匹配参数
- `source` — 源侧摘要信息
- `matches[].domain_match_detail` — 领域匹配过程描述
- `matches[].text_match_detail` — 文本匹配详情（重叠 bigram、统计等）
- `matches[].source_fields` — 源侧参与匹配的字段值
- `matches[].target_fields` — 目标侧参与匹配的字段值

### 参数配置接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config` | 获取当前匹配参数 |
| POST | `/api/config` | 更新匹配参数（JSON body） |

可配置参数：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `domain_weight` | float | 0.6 | 领域匹配权重 (0~1) |
| `text_weight` | float | 0.4 | 文本相似度权重 (0~1) |
| `top_n` | int | 3 | 返回前 N 条最佳匹配 |
| `text_max_length` | int | 300 | 文本匹配截取汉字数 |

POST 示例：

```json
{ "domain_weight": 0.7, "text_weight": 0.3, "top_n": 5 }
```

## 前端界面

### 功能

- **双模式切换**：能力→机会（默认）/ 机会→能力
- **左侧列表**：按序号展示全部条目，点击选中
- **右侧匹配卡片**（v2 增强）：
  - 📋 匹配字段对照表（左右两栏对照）
  - 🔍 领域匹配详情（精确/大类/未命中 + 上下文）
  - 📐 文本匹配详情（Jaccard 统计 + 重叠 2-gram 关键词标签）
  - 📊 双色进度条（领域贡献 + 文本贡献 + 综合百分比）
- **参数面板**：实时展示当前权重 / TopN / 截取长度

### 交互

- 点击左侧列表项 → 自动发起匹配请求 → 右侧展示 Top3 结果
- 切换模式按钮 → 刷新列表 → 清空匹配结果

## 领域归一化

`matcher/normalizer.py` 维护领域→大类映射表，处理跨表命名不一致：

| 原始值 | 归一化 |
|---|---|
| 人工智能（软件）/ 人工智能（硬件） | 人工智能 |
| 智能制造装备 / 机器人 | 智能制造 |
| 智能网联新能源汽车 | 新能源汽车 |
| 产业转型升级 / 六大新兴产业集群 / 其他 | 综合 |

## License

内部 Demo 项目。
