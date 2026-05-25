# CHANGELOG

场景机会与能力智能匹配 Demo 变更日志。按 commit 记录每个文件/函数的修改。

---

## [v2] 2026-05-25 — 匹配结果详细展示重构

> Commit: `800a739` | 9 files, +795 −185

### `matcher/engine.py` — 核心匹配引擎重构 (+287 −?)

| 函数/变更 | 说明 |
|---|---|
| **新增** `MATCH_CONFIG` | 全局配置字典，集中管理 `domain_weight` / `text_weight` / `top_n` / `text_max_length` |
| **新增** `get_config()` | 返回当前匹配参数的副本 |
| **新增** `update_config(new_config)` | 增量更新匹配参数，只改传入的键 |
| **修改** `compute_domain_score(ability_domain, opp_welcome)` | 返回值从 `float` → `tuple[float, str]`，新增 `detail` 字符串描述精确命中/大类近似/未命中的匹配过程 |
| **修改** `compute_text_score(text_a, text_b)` | 返回值从 `float` → `tuple[float, dict]`，新增 `detail` 字典含 `overlapping_bigrams` / `overlap_count` / `union_count` / 双方 bigram 数量 / 文本摘要 |
| **修改** `match_ability_to_opportunities(ability, opportunities)` | 每条匹配结果新增 `domain_match_detail` / `text_match_detail` / `source_fields` / `target_fields` 字段 |
| **修改** `match_opportunity_to_abilities(opp, abilities)` | 同上，且反向匹配时增加兜底策略（领域得分为 0 时用机会领域匹配能力侧意向客户） |

### `matcher/__init__.py` — 包导出更新 (+9 −?)

| 函数/变更 | 说明 |
|---|---|
| **新增导出** `get_config` | 供 app.py 读取当前匹配参数 |
| **新增导出** `update_config` | 供 app.py 更新匹配参数 |

### `app.py` — Flask 路由层升级 (+162 −?)

| 函数/变更 | 说明 |
|---|---|
| **新增** `GET /api/config` | 返回当前匹配参数配置 |
| **新增** `POST /api/config` | 接收 JSON body 更新匹配参数，含类型校验和范围检查 |
| **新增** `OPTIONS` 处理 | `api_config()` 支持 OPTIONS 预检请求 |
| **修改** `api_match_ability(ability_id)` | 返回结构新增 `config` / `domain_match_detail` / `text_match_detail` / `source_fields` / `target_fields` |
| **修改** `api_match_opportunity(opp_id)` | 同上的 v2 返回结构 |

### `static/js/render.js` — 前端渲染模块重写 (+237 −?)

| 函数/变更 | 说明 |
|---|---|
| **新增** `nl2br(text)` | 将 `\n` 转换为 `<br>`，用于渲染领域匹配详情多行文本 |
| **修改** `scoreBar()` | 从单色进度条改为**双色**（蓝=领域贡献、绿=文本贡献），hover title 显示 `原始分 × 权重` 计算明细，传入 `dw`/`tw` 参数 |
| **新增** `renderConfigPanel(config)` | 在右侧面板顶部渲染匹配参数信息条（权重/TopN/截取长度） |
| **修改** `renderCards(data)` | **全新卡片布局**：①排名徽章+标题 ②字段对照表（左源右目标） ③领域匹配详情（原始得分+加权贡献标签+描述文本） ④文本匹配详情（Jaccard 统计+双方摘要+重叠 bigram 关键词标签） ⑤双色进度条 |
| **修改** `showLoading()` / `showEmpty()` | 加载/空状态时清空参数面板 |

### `static/js/state.js` — 全局状态管理 (+22 −?)

| 函数/变更 | 说明 |
|---|---|
| **新增** `_config` | 内部状态变量，缓存当前匹配参数 |
| **新增** `getConfig()` | 获取当前匹配参数配置 |
| **新增** `setConfig(config)` | 设置当前匹配参数配置 |

### `static/js/api.js` — API 请求层 (+36)

| 函数/变更 | 说明 |
|---|---|
| **新增** `fetchConfig()` | GET `/api/config` 获取匹配参数 |
| **新增** `updateConfigAPI(newConfig)` | POST `/api/config` 更新匹配参数 |

### `static/js/main.js` — 主流程编排 (+25 −?)

| 函数/变更 | 说明 |
|---|---|
| **修改** `init()` | 并行加载数据+配置，`fetchConfig` 失败不阻塞页面 |
| **修改** 列表点击事件 | 匹配完成后从 `result.config` 缓存配置到全局状态 |

### `static/index.html` — 主页面 (+3)

| 变更 | 说明 |
|---|---|
| **新增** `<div id="config-panel">` | 参数配置面板容器，JS 动态渲染 |

### `static/css/style.css` — 样式表 (+199 −?)

| 变更 | 说明 |
|---|---|
| **新增** `.config-panel` / `.config-panel-inner` / `.config-panel-title` / `.config-item` / `.config-sep` | 参数面板样式（浅蓝底、flex 横向排列） |
| **新增** `.cards-grid` 改为 `flex-direction: column` | 卡片从网格改为单列垂直布局 |
| **新增** `.card-section` / `.card-section-title` / `.section-score` / `.section-score-weighted` | 卡片内分区块及评分标签样式 |
| **新增** `.field-compare` / `.field-row` / `.field-col` / `.field-col-left` / `.field-col-right` / `.field-arrow` / `.field-label` / `.field-value` | 字段对照表样式（左右蓝/黄底色对照 + →箭头） |
| **新增** `.card-detail-text` | 领域匹配详情文本样式（浅灰底 + 蓝色左边框） |
| **新增** `.text-stats` / `.text-stat` / `.text-stat-label` / `.text-stat-val` / `.text-stat-hint` | 文本匹配统计行样式 |
| **新增** `.text-snippets` / `.text-snippet-label` / `.text-snippet-val` | 文本摘要展示样式（等宽字体） |
| **新增** `.bigram-tags` / `.bigram-tags-label` / `.bigram-tag` / `.bigram-tags-empty` | 重叠关键词标签样式（绿色圆角 pills + hover 放大） |
| **修改** 响应式 `.cards-grid` | 从 `grid-template-columns` 改为 `flex-direction: column` |

---

## [v1] 2026-05-25 — 项目初始化

> Commit: `7c46595` | 16 files, +1970

### 项目整体

| 模块 | 说明 |
|---|---|
| **项目结构** | 建立 Flask + 纯前端模块化架构 |
| **数据加载** | 从 Excel 读取 406 条能力 + 1186 条机会到内存 |
| **匹配算法** | 加权双因子：领域得分(60%) + 2-gram Jaccard 文本得分(40%)，Top3 |
| **前端交互** | 双模式切换、列表点击匹配、卡片展示 |

### `app.py`

| 函数/变更 | 说明 |
|---|---|
| **新增** `add_cors_headers()` | 内置 CORS 支持 |
| **新增** `GET /` | 返回 index.html |
| **新增** `GET /api/abilities` | 返回全部能力摘要列表 |
| **新增** `GET /api/opportunities` | 返回全部机会摘要列表 |
| **新增** `GET /api/match/ability/<id>` | 为能力匹配 Top3 机会 |
| **新增** `GET /api/match/opportunity/<id>` | 为机会匹配 Top3 能力 |
| **新增** 启动入口 | Flask 127.0.0.1:5000 + debug 模式 |

### `matcher/data_loader.py`

| 函数/变更 | 说明 |
|---|---|
| **新增** `_safe_str(value)` | NaN/None → 空字符串转换 |
| **新增** `load_abilities(filepath)` | 从「创新产品发布审核列表」sheet 加载场景能力 |
| **新增** `load_opportunities(filepath)` | 从「应用场景发布审核」sheet 加载场景机会 |
| **新增** `get_by_id(items, item_id)` | 按 ID 查找条目 |

### `matcher/normalizer.py`

| 函数/变更 | 说明 |
|---|---|
| **新增** `DOMAIN_MAP` | 13 条领域→大类映射规则 |
| **新增** `normalize_domain(raw_domain)` | 根据映射表归一化领域关键词 |

### `matcher/engine.py` (v1)

| 函数/变更 | 说明 |
|---|---|
| **新增** `_clean_text(text)` | 清洗非中文字符 |
| **新增** `_extract_bigrams(text)` | 提取中文 2-gram 字符集 |
| **新增** `_jaccard_similarity(set_a, set_b)` | Jaccard 相似度计算 |
| **新增** `compute_domain_score(ability_domain, opp_welcome)` | 精确匹配 1.0 / 大类近似 0.5 / 无 0.0 |
| **新增** `compute_text_score(text_a, text_b)` | 2-gram Jaccard 文本得分 |
| **新增** `match_ability_to_opportunities(ability, opportunities)` | 能力→机会匹配入口 |
| **新增** `match_opportunity_to_abilities(opp, abilities)` | 机会→能力匹配入口 |

### `matcher/__init__.py`

| 函数/变更 | 说明 |
|---|---|
| **新增** 导出 `load_abilities` / `load_opportunities` / `normalize_domain` / `match_ability_to_opportunities` / `match_opportunity_to_abilities` |

### `static/js/state.js`

| 函数/变更 | 说明 |
|---|---|
| **新增** `State` IIFE 模块 | 封装 `_currentMode` / `_selectedId` / `_abilities` / `_opportunities` 状态 |
| **新增** `getMode()` / `setMode()` / `getSelectedId()` / `setSelectedId()` | 模式与选中状态 |
| **新增** `getAbilities()` / `setAbilities()` / `getOpportunities()` / `setOpportunities()` | 数据缓存 |
| **新增** `getCurrentList()` / `getCurrentItem()` | 按模式获取列表/当前项 |

### `static/js/api.js`

| 函数/变更 | 说明 |
|---|---|
| **新增** `fetchAbilities()` | GET /api/abilities |
| **新增** `fetchOpportunities()` | GET /api/opportunities |
| **新增** `fetchMatchForAbility(abilityId)` | GET /api/match/ability/:id |
| **新增** `fetchMatchForOpportunity(oppId)` | GET /api/match/opportunity/:id |

### `static/js/render.js`

| 函数/变更 | 说明 |
|---|---|
| **新增** `truncateText(text, maxLen)` | 文本截断 |
| **新增** `scoreBar()` | 百分比进度条 |
| **新增** `renderList()` | 左侧列表渲染（能力/机会双模式） |
| **新增** `renderCards(data)` | 右侧匹配卡片渲染（v1 基础版） |
| **新增** `showLoading()` | Loading 动画 |
| **新增** `showEmpty()` | 空状态提示 |

### `static/js/main.js`

| 函数/变更 | 说明 |
|---|---|
| **新增** `init()` | 页面初始化：加载数据、渲染列表 |
| **新增** 列表点击事件委托 | 选中 → 匹配 → 渲染 |
| **新增** 模式切换事件 | `switchMode()` 切换能力/机会视图 |
| **新增** `DOMContentLoaded` 启动 | 页面加载完成后自动 `init()` |

### `static/index.html`

| 变更 | 说明 |
|---|---|
| **新增** 完整 HTML 骨架 | 顶栏 + 双栏布局（左侧列表 + 右侧卡片）+ JS 模块引用 |

### `static/css/style.css`

| 变更 | 说明 |
|---|---|
| **新增** 完整样式表 | CSS 变量、顶栏、双栏、列表项、卡片、进度条、Loading、空状态、响应式 |

### 其他文件

| 文件 | 说明 |
|---|---|
| `requirements.txt` | Flask 依赖 |
| `start.bat` | Windows 一键启动脚本（检查依赖 + 启动 Flask） |
| `.gitignore` | 排除 pyc / ~$* 临时文件 / _test* / .workbuddy |
