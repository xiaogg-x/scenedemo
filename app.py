# -*- coding: utf-8 -*-
"""
app.py —— Flask 路由层 (v2)

职责：
  1. 应用启动时调用 matcher 包加载 Excel 数据到内存
  2. 提供 6 个 RESTful API 接口供前端调用
  3. 内置 CORS 支持，允许跨域访问（本地 Demo 必需）
  4. 新增 /api/config 接口，支持前端动态读取和调整匹配参数

API 接口一览：
  GET  /api/abilities              → 返回全部场景能力列表（摘要字段）
  GET  /api/opportunities          → 返回全部场景机会列表（摘要字段）
  GET  /api/match/ability/<id>     → 为指定能力返回 Top3 匹配机会（含详细明细）
  GET  /api/match/opportunity/<id> → 为指定机会返回 Top3 匹配能力（含详细明细）
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
    update_config,
    load_config_from_file,
)


# ============================================================================
# Flask 应用初始化
# ============================================================================
app = Flask(
    __name__,
    static_folder='static',        # 前端静态文件目录
    static_url_path=''             # 静态文件直接通过根路径访问
)


# ============================================================================
# 内置 CORS 支持（允许前端跨域请求）
# ============================================================================
@app.after_request
def add_cors_headers(response):
    """
    为每个响应添加 CORS 头，允许本地前端页面通过 fetch 调用 API。
    注意：生产环境应使用 flask-cors 插件并限定源。
    """
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods']  = 'GET, POST, OPTIONS'
    return response


# ============================================================================
# 数据加载（启动时一次性加载到全局变量）
# ============================================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '后台数据')

print('=' * 60)
print('  正在加载数据...')
print('=' * 60)

# 加载场景能力数据
ALL_ABILITIES = load_abilities(os.path.join(DATA_DIR, '场景能力数据列表.xlsx'))

# 加载场景机会数据
ALL_OPPORTUNITIES = load_opportunities(os.path.join(DATA_DIR, '场景机会数据列表.xlsx'))

print('=' * 60)
print(f'  数据加载完成：{len(ALL_ABILITIES)} 条能力，{len(ALL_OPPORTUNITIES)} 条机会')
print('=' * 60)

# 启动时从持久化文件恢复匹配参数配置
load_config_from_file()


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
    """
    返回全部场景能力列表（仅返回前端展示所需的摘要字段）。

    返回格式：
      [{id, name, company, domain}, ...]
    """
    summary = []
    for a in ALL_ABILITIES:
        summary.append({
            'id':       a['id'],
            'name':     a['name'],
            'company':  a['company'],
            'domain':   a['domain'],
            'district': a['district'],
        })
    return jsonify(summary)


@app.route('/api/opportunities')
def api_opportunities():
    """
    返回全部场景机会列表（仅返回前端展示所需的摘要字段）。

    返回格式：
      [{id, name, domain, sub_domain, area}, ...]
    """
    summary = []
    for o in ALL_OPPORTUNITIES:
        summary.append({
            'id':         o['id'],
            'name':       o['name'],
            'domain':     o['domain'],
            'sub_domain': o['sub_domain'],
            'area':       o['area'],
        })
    return jsonify(summary)


# ---------------------------------------------------------------------------
# 匹配 API（v2：携带详细明细 + 参数配置）
# ---------------------------------------------------------------------------

@app.route('/api/match/ability/<int:ability_id>')
def api_match_ability(ability_id):
    """
    为指定场景能力匹配 Top3 场景机会（v2 增强版）。

    返回 v2 新增字段：
      - config:              当前匹配参数（domain_weight, text_weight 等）
      - matches[i].domain_match_detail:  领域匹配过程描述文本
      - matches[i].text_match_detail:    文本匹配详情（重叠 bigram 等）
      - matches[i].source_fields:        源侧（能力）参与匹配的字段值
      - matches[i].target_fields:        目标侧（机会）参与匹配的字段值
    """
    # 按 ID 查找能力
    ability = None
    for a in ALL_ABILITIES:
        if a['id'] == ability_id:
            ability = a
            break

    if ability is None:
        return jsonify({'error': f'能力 ID={ability_id} 不存在'}), 404

    # 调用匹配引擎
    matches = match_ability_to_opportunities(ability, ALL_OPPORTUNITIES)

    # 构造返回结果（v2 含详细字段）
    result = {
        'config': get_config(),
        'source': {
            'id':              ability['id'],
            'name':            ability['name'],
            'company':         ability['company'],
            'domain':          ability['domain'],
            'district':        ability['district'],
            'overview':        ability['overview'],
            'target_customer': ability['target_customer'],
        },
        'matches': [{
            'target': {
                'id':         m['target']['id'],
                'name':       m['target']['name'],
                'domain':     m['target']['domain'],
                'sub_domain': m['target']['sub_domain'],
                'area':       m['target']['area'],
                'overview':   m['target']['overview'],
                'welcome':    m['target']['welcome'],
                'category':   m['target']['category'],
                'unit':       m['target']['unit'],
            },
            'domain_score':         m['domain_score'],
            'text_score':           m['text_score'],
            'region_score':         m['region_score'],
            'total_score':          m['total_score'],
            'domain_match_detail':  m['domain_match_detail'],
            'text_match_detail':    m['text_match_detail'],
            'region_match_detail':  m['region_match_detail'],
            'source_fields':        m['source_fields'],
            'target_fields':        m['target_fields'],
        } for m in matches],
    }
    return jsonify(result)


@app.route('/api/match/opportunity/<int:opp_id>')
def api_match_opportunity(opp_id):
    """
    为指定场景机会匹配 Top3 场景能力（v2 增强版，反向匹配）。

    返回格式与 api_match_ability 一致，携带 config + 详细匹配明细。
    """
    # 按 ID 查找机会
    opp = None
    for o in ALL_OPPORTUNITIES:
        if o['id'] == opp_id:
            opp = o
            break

    if opp is None:
        return jsonify({'error': f'机会 ID={opp_id} 不存在'}), 404

    # 调用匹配引擎（反向匹配）
    matches = match_opportunity_to_abilities(opp, ALL_ABILITIES)

    # 构造返回结果
    result = {
        'config': get_config(),
        'source': {
            'id':         opp['id'],
            'name':       opp['name'],
            'domain':     opp['domain'],
            'area':       opp['area'],
            'overview':   opp['overview'],
            'welcome':    opp['welcome'],
        },
        'matches': [{
            'target': {
                'id':              m['target']['id'],
                'name':            m['target']['name'],
                'company':         m['target']['company'],
                'domain':          m['target']['domain'],
                'district':        m['target']['district'],
                'overview':        m['target']['overview'],
                'highlight':       m['target']['highlight'],
                'effect':          m['target']['effect'],
                'target_customer': m['target']['target_customer'],
            },
            'domain_score':         m['domain_score'],
            'text_score':           m['text_score'],
            'region_score':         m['region_score'],
            'total_score':          m['total_score'],
            'domain_match_detail':  m['domain_match_detail'],
            'text_match_detail':    m['text_match_detail'],
            'region_match_detail':  m['region_match_detail'],
            'source_fields':        m['source_fields'],
            'target_fields':        m['target_fields'],
        } for m in matches],
    }
    return jsonify(result)


# ---------------------------------------------------------------------------
# 参数配置 API
# ---------------------------------------------------------------------------

@app.route('/api/config', methods=['GET', 'POST', 'OPTIONS'])
def api_config():
    """
    GET  /api/config  → 返回当前匹配参数
    POST /api/config  → 更新匹配参数（接收 JSON body）

    可配置参数：
      - domain_weight   (float): 领域匹配权重 (0~1)
      - text_weight     (float): 文本相似度权重 (0~1)
      - top_n           (int):   返回前 N 条匹配
      - text_max_length (int):   文本匹配截取长度

    示例 POST body:
      {"domain_weight": 0.7, "text_weight": 0.3}
    """
    if request.method == 'OPTIONS':
        return '', 204

    if request.method == 'POST':
        try:
            body = request.get_json(force=True)
            if body is None:
                return jsonify({'error': '请求体为空，请提供 JSON'}), 400

            # 类型校验
            for key in ['domain_weight', 'text_weight', 'region_weight']:
                if key in body and not isinstance(body[key], (int, float)):
                    return jsonify({'error': f'{key} 必须是数值'}), 400
                if key in body and not (0 <= body[key] <= 1):
                    return jsonify({'error': f'{key} 必须在 0~1 之间'}), 400

            if 'top_n' in body and not isinstance(body['top_n'], int):
                return jsonify({'error': 'top_n 必须是整数'}), 400
            if 'top_n' in body and body['top_n'] < 1:
                return jsonify({'error': 'top_n 必须 >= 1'}), 400

            if 'text_max_length' in body and not isinstance(body['text_max_length'], int):
                    return jsonify({'error': 'text_max_length 必须是整数'}), 400
            if 'text_max_length' in body and body['text_max_length'] < 50:
                return jsonify({'error': 'text_max_length 必须 >= 50'}), 400

            # ---- 权重自动缩放（兜底）：三维权重之和 ！= 1 则等比例缩放 ----
            weight_keys = ['domain_weight', 'text_weight', 'region_weight']
            any_weight_updated = any(k in body for k in weight_keys)

            if any_weight_updated:
                # 从 body 或当前配置中取最新值
                current_cfg = get_config()
                weights = []
                for k in weight_keys:
                    val = float(body[k]) if k in body else current_cfg[k]
                    weights.append(val)
                dw, tw, rw = weights
                s = dw + tw + rw
                if s > 0.001 and abs(s - 1.0) > 0.001:
                    factor = 1.0 / s
                    body['domain_weight'] = round(dw * factor, 4)
                    body['text_weight']   = round(tw * factor, 4)
                    body['region_weight'] = round(rw * factor, 4)
                    print(f'[config] 权重已自动缩放至和为1：domain={body["domain_weight"]}, text={body["text_weight"]}, region={body["region_weight"]}')

            new_config = update_config(body)
            print(f'[config] 参数已更新: {new_config}')
            return jsonify(new_config)

        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # GET 请求
    return jsonify(get_config())


# ============================================================================
# 程序入口
# ============================================================================
if __name__ == '__main__':
    print()
    print('=' * 60)
    print('  场景机会与能力匹配 Demo — 后端服务 v2')
    print(f'  访问地址: http://127.0.0.1:5000')
    print('  API 文档: http://127.0.0.1:5000/api/config')
    print('=' * 60)
    app.run(host='127.0.0.1', port=5000, debug=True)
