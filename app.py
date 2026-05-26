# -*- coding: utf-8 -*-
"""
app.py —— Flask 路由层 (v3)

职责：
  1. 应用启动时调用 matcher 包加载 Excel 数据到内存
  2. 提供 RESTful API 接口供前端调用
  3. 内置 CORS 支持，允许跨域访问（本地 Demo 必需）
  4. 配置接口感知维度注册表，支持动态增删匹配维度

API 接口一览：
  GET  /api/abilities              → 返回全部场景能力列表（摘要字段）
  GET  /api/opportunities          → 返回全部场景机会列表（摘要字段）
  GET  /api/match/ability/<id>     → 为指定能力返回 Top N 匹配机会（含详细明细）
  GET  /api/match/opportunity/<id> → 为指定机会返回 Top N 匹配能力（含详细明细）
  GET  /api/dimensions             → 返回维度元信息 + 当前配置
  GET  /api/config                 → 返回当前匹配参数配置
  POST /api/config                 → 更新匹配参数（JSON body）

启动方式：
  python app.py
  或双击 start.bat
"""

import os
import sys
from flask import Flask, jsonify, request

# 将项目根目录加入路径，确保能 import matcher 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from matcher import (
    load_abilities,
    load_opportunities,
    match_ability_to_opportunities,
    match_opportunity_to_abilities,
    get_config,
    get_config_with_dimensions,
    update_config,
    load_config_from_file,
    get_weight_keys,
    add_dimension,
    delete_dimension,
    sync_config_with_dimensions,
    METHOD_REGISTRY,
    get_next_dim_id,
    pre_warm_cache,
)


# ============================================================================
# Flask 应用初始化
# ============================================================================
app = Flask(
    __name__,
    static_folder='static',
    static_url_path=''
)


# ============================================================================
# 内置 CORS 支持
# ============================================================================
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    return response


# ============================================================================
# 数据加载（启动时一次性加载到全局变量）
# ============================================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '后台数据')

print('=' * 60)
print('  正在加载数据...')
print('=' * 60)

ALL_ABILITIES = load_abilities(os.path.join(DATA_DIR, '场景能力数据列表.xlsx'))
ALL_OPPORTUNITIES = load_opportunities(os.path.join(DATA_DIR, '场景机会数据列表.xlsx'))

print('=' * 60)
print(f'  数据加载完成：{len(ALL_ABILITIES)} 条能力，{len(ALL_OPPORTUNITIES)} 条机会')
print('=' * 60)

load_config_from_file()

# 预热向量语义缓存——对 vector_semantic 维度引用的所有文本批量编码，
# 避免首次匹配请求因逐个编码 1000+ 条文本而超时（54s → <1s）
print('=' * 60)
print('  正在预热向量语义缓存...')
print('=' * 60)
pre_warm_cache(ALL_ABILITIES, ALL_OPPORTUNITIES)
print('=' * 60)
print('  缓存预热完成，准备接受请求')
print('=' * 60)


# ============================================================================
# API 路由定义
# ============================================================================

@app.route('/')
def index():
    """返回前端页面"""
    return app.send_static_file('index.html')


# ---------------------------------------------------------------------------
# 列表 API
# ---------------------------------------------------------------------------

@app.route('/api/abilities')
def api_abilities():
    """返回全部场景能力列表（摘要字段）。"""
    summary = []
    for a in ALL_ABILITIES:
        summary.append({
            'id': a['id'],
            'name': a['name'],
            'company': a['company'],
            'domain': a['domain'],
            'district': a['district'],
        })
    return jsonify(summary)


@app.route('/api/opportunities')
def api_opportunities():
    """返回全部场景机会列表（摘要字段）。"""
    summary = []
    for o in ALL_OPPORTUNITIES:
        summary.append({
            'id': o['id'],
            'name': o['name'],
            'domain': o['domain'],
            'sub_domain': o['sub_domain'],
            'area': o['area'],
        })
    return jsonify(summary)


# ---------------------------------------------------------------------------
# 匹配 API (v3：含 dimension_scores)
# ---------------------------------------------------------------------------

def _build_match_response(matches, config, source):
    """
    构建匹配结果响应体（v3 格式）。

    响应体同时包含：
      - v3 结构化字段：dimension_scores（{dim_id: {score, detail, weight}}）
      - v2 兼容扁平字段：{dim_id}_score, {dim_id}_match_detail
        这样老前端代码不需要改动就能读取，新代码也用 dimension_scores
    """
    match_list = []
    for m in matches:
        target = m['target']
        entry = {
            'target': {
                'id': target['id'],
                'name': target['name'],
                'domain': target.get('domain', ''),
                # area 字段：机会侧用 'area'，能力侧用 'district'
                'area': target.get('area', target.get('district', '')),
                'overview': target.get('overview', ''),
            },
            'total_score': m['total_score'],
            'dimension_scores': m.get('dimension_scores', {}),
            'source_fields': m.get('source_fields', {}),
            'target_fields': m.get('target_fields', {}),
        }
        # ---- v2 兼容层：把 dimension_scores 拍平为独立 key ----
        # 例如 domain_score=0.8, domain_match_detail="精确命中..."
        # 前端 render.js 中既有 v2 的 dimension_scores 渲染，也有 v2 兼容读取
        if 'dimension_scores' in m:
            for dim_id, ds in m['dimension_scores'].items():
                entry[f'{dim_id}_score'] = ds['score']
                entry[f'{dim_id}_match_detail'] = ds['detail']
        else:
            # 兜底：如果引擎没返回 dimension_scores（旧版本），从扁平字段还原
            for key in m:
                if key.endswith('_score') and key != 'total_score':
                    entry[key] = m[key]
                if key.endswith('_match_detail'):
                    entry[key] = m[key]

        # ---- 透传 target 中的可选字段（机会和能力侧字段不同） ----
        # 不做硬编码，字段存在才透传，这样新增字段只需数据源增加即可
        for extra_field in [
            'sub_domain', 'welcome', 'category', 'unit',
            'company', 'highlight', 'effect', 'target_customer'
        ]:
            if extra_field in target:
                entry['target'][extra_field] = target[extra_field]

        match_list.append(entry)

    return {
        'config': config,
        'source': source,
        'matches': match_list,
    }


@app.route('/api/match/ability/<int:ability_id>')
def api_match_ability(ability_id):
    """为指定场景能力匹配 Top N 场景机会。"""
    ability = None
    for a in ALL_ABILITIES:
        if a['id'] == ability_id:
            ability = a
            break

    if ability is None:
        return jsonify({'error': f'能力 ID={ability_id} 不存在'}), 404

    matches = match_ability_to_opportunities(ability, ALL_OPPORTUNITIES)

    source = {
        'id': ability['id'],
        'name': ability['name'],
        'company': ability['company'],
        'domain': ability['domain'],
        'district': ability['district'],
        'overview': ability['overview'],
        'target_customer': ability['target_customer'],
    }

    return jsonify(_build_match_response(matches, get_config(), source))


@app.route('/api/match/opportunity/<int:opp_id>')
def api_match_opportunity(opp_id):
    """为指定场景机会匹配 Top N 场景能力。"""
    opp = None
    for o in ALL_OPPORTUNITIES:
        if o['id'] == opp_id:
            opp = o
            break

    if opp is None:
        return jsonify({'error': f'机会 ID={opp_id} 不存在'}), 404

    matches = match_opportunity_to_abilities(opp, ALL_ABILITIES)

    source = {
        'id': opp['id'],
        'name': opp['name'],
        'domain': opp['domain'],
        'area': opp['area'],
        'overview': opp['overview'],
        'welcome': opp['welcome'],
    }

    return jsonify(_build_match_response(matches, get_config(), source))


# ---------------------------------------------------------------------------
# 维度 API (v3 新增)
# ---------------------------------------------------------------------------

@app.route('/api/dimensions')
def api_dimensions():
    """返回维度注册表元信息 + 当前配置值。"""
    return jsonify(get_config_with_dimensions())


# ---------------------------------------------------------------------------
# 字段列表 API（前端添加维度时使用）
# ---------------------------------------------------------------------------

@app.route('/api/fields')
def api_fields():
    """返回能力侧和机会侧可用于匹配的字段列表。"""
    return jsonify({
        'ability': ['domain', 'district', 'overview', 'highlight', 'effect', 'target_customer'],
        'opportunity': ['domain', 'sub_domain', 'area', 'overview', 'welcome', 'category', 'unit', 'investment'],
    })


# ---------------------------------------------------------------------------
# 匹配方法 API（前端添加维度时使用）
# ---------------------------------------------------------------------------

@app.route('/api/dimensions/methods')
def api_dimension_methods():
    """返回可用匹配方法及其默认参数。"""
    result = {}
    for name, reg in METHOD_REGISTRY.items():
        result[name] = {
            'default_detail_type': reg['default_detail_type'],
            'default_params': reg['default_params'],
            'default_icon': reg['default_icon'],
            'default_color': reg['default_color'],
        }
    return jsonify(result)


# ---------------------------------------------------------------------------
# 维度增删 API
# ---------------------------------------------------------------------------

@app.route('/api/dimensions', methods=['POST', 'OPTIONS'])
def api_add_dimension():
    """添加新匹配维度（默认权重 0）。"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        body = request.get_json(force=True)
        if body is None or not isinstance(body, dict):
            return jsonify({'error': '请求体必须是 JSON 对象'}), 400

        if 'label' not in body:
            return jsonify({'error': '缺少必需字段：label'}), 400
        if 'method' not in body:
            return jsonify({'error': '缺少必需字段：method'}), 400

        success, msg, dim = add_dimension(body)
        if not success:
            return jsonify({'error': msg}), 400

        sync_config_with_dimensions()
        return jsonify({'success': True, 'message': msg, 'dimension': dim})

    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/dimensions/<dim_id>', methods=['DELETE', 'OPTIONS'])
def api_delete_dimension(dim_id):
    """删除指定匹配维度（至少保留 1 个）。"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        success, msg = delete_dimension(dim_id)
        if not success:
            return jsonify({'error': msg}), 400

        sync_config_with_dimensions()
        return jsonify({'success': True, 'message': msg})

    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ---------------------------------------------------------------------------
# 参数配置 API (v3：维度感知)
# ---------------------------------------------------------------------------

@app.route('/api/config', methods=['GET', 'POST', 'OPTIONS'])
def api_config():
    """
    GET  → 返回当前匹配参数（含所有权重 key 和维度私有参数）
    POST → 更新匹配参数

    POST 校验流程：
      1) 类型校验：权重必须是 0~1 的 float，top_n 必须是 >=1 的 int
      2) 维度私有参数校验：从 DIMENSIONS 注册表读取每个 param 的 type/min/max
      3) 权重自动缩放：如果任意权重有更新且和 ≠ 1.0，则等比例缩放到和为 1
         例如 domain=0.5, text=0.5 → sum=1.0 ✓ 不缩放
              domain=0.8, text=0.8 → sum=1.6 → 缩放到 0.5 和 0.5

    POST body 示例：
      {"domain_weight": 0.7, "text_weight": 0.3, "top_n": 5}
    """
    if request.method == 'OPTIONS':
        return '', 204

    if request.method == 'POST':
        try:
            body = request.get_json(force=True)
            if body is None:
                return jsonify({'error': '请求体为空，请提供 JSON'}), 400

            # 从维度注册表获取当前有效的所有权重 key（如 domain_weight, text_weight, region_weight）
            valid_weight_keys = set(get_weight_keys())

            # ---- 1) 权重 key 类型 & 范围校验 ----
            for key in valid_weight_keys:
                if key in body and not isinstance(body[key], (int, float)):
                    return jsonify({'error': f'{key} 必须是数值'}), 400
                if key in body and not (0 <= body[key] <= 1):
                    return jsonify({'error': f'{key} 必须在 0~1 之间'}), 400

            # ---- 2) top_n 校验 ----
            if 'top_n' in body:
                if not isinstance(body['top_n'], int):
                    return jsonify({'error': 'top_n 必须是整数'}), 400
                if body['top_n'] < 1:
                    return jsonify({'error': 'top_n 必须 >= 1'}), 400

            # ---- 3) 维度私有参数校验（遍历 DIMENSIONS 注册表） ----
            from matcher.dimensions import DIMENSIONS
            for dim in DIMENSIONS:
                for pk, pv in dim.get('params', {}).items():
                    config_key = f"{dim['id']}_{pk}"  # 如 "text_max_length"
                    if config_key in body:
                        if pv['type'] == 'int' and not isinstance(body[config_key], int):
                            return jsonify({'error': f'{config_key} 必须是整数'}), 400
                        if 'min' in pv and body[config_key] < pv['min']:
                            return jsonify({'error': f'{config_key} 必须 >= {pv["min"]}'}), 400
                        if 'max' in pv and body[config_key] > pv['max']:
                            return jsonify({'error': f'{config_key} 必须 <= {pv["max"]}'}), 400

            # ---- 4) 权重自动缩放（如果用户修改了任意权重） ----
            weight_updated = any(k in body for k in valid_weight_keys)

            if weight_updated:
                # 收集所有权重值（body 中有的用 body，没有的用当前配置）
                current_cfg = get_config()
                weights = []
                for k in valid_weight_keys:
                    val = float(body[k]) if k in body else current_cfg.get(k, 0.0)
                    weights.append(val)
                s = sum(weights)
                # 如果和不是 1.0 且不是全零，等比例缩放
                if s > 0.001 and abs(s - 1.0) > 0.001:
                    factor = 1.0 / s
                    for k in valid_weight_keys:
                        if k in body or k in current_cfg:
                            body[k] = round((float(body.get(k, current_cfg.get(k, 0.0)))) * factor, 4)
                    print(f'[config] 权重已自动缩放至和为1：{ {k: body[k] for k in valid_weight_keys if k in body} }')

            new_config = update_config(body)
            print(f'[config] 参数已更新: {new_config}')
            return jsonify(new_config)

        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # GET 请求：直接返回当前完整配置
    return jsonify(get_config())


# ============================================================================
# 程序入口
# ============================================================================
if __name__ == '__main__':
    print()
    print('=' * 60)
    print('  场景机会与能力匹配 Demo — 后端服务 v3')
    print(f'  访问地址: http://127.0.0.1:5000')
    print('  API 文档: http://127.0.0.1:5000/api/config')
    print('=' * 60)
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)
