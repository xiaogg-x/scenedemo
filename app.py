# -*- coding: utf-8 -*-
"""
app.py —— Flask 路由层

职责：
  1. 应用启动时调用 matcher 包加载 Excel 数据到内存
  2. 提供 4 个 RESTful API 接口供前端调用
  3. 内置 CORS 支持，允许跨域访问（本地 Demo 必需）

API 接口一览：
  GET /api/abilities       → 返回全部场景能力列表（摘要字段）
  GET /api/opportunities   → 返回全部场景机会列表（摘要字段）
  GET /api/match/ability/<id>    → 为指定能力返回 Top3 匹配机会
  GET /api/match/opportunity/<id> → 为指定机会返回 Top3 匹配能力

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
    response.headers['Access-Control-Allow-Methods']  = 'GET, OPTIONS'
    return response


# ============================================================================
# 数据加载（启动时一次性加载到全局变量）
# ============================================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '后台数据')

print('=' * 60)
print('正在加载数据...')
print('=' * 60)

# 加载场景能力数据
ALL_ABILITIES = load_abilities(os.path.join(DATA_DIR, '场景能力数据列表.xlsx'))

# 加载场景机会数据
ALL_OPPORTUNITIES = load_opportunities(os.path.join(DATA_DIR, '场景机会数据列表.xlsx'))

print('=' * 60)
print(f'数据加载完成：{len(ALL_ABILITIES)} 条能力，{len(ALL_OPPORTUNITIES)} 条机会')
print('=' * 60)


# ============================================================================
# API 路由定义
# ============================================================================

@app.route('/')
def index():
    """返回前端页面"""
    return app.send_static_file('index.html')


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
            'id':      a['id'],
            'name':    a['name'],
            'company': a['company'],
            'domain':  a['domain'],
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


@app.route('/api/match/ability/<int:ability_id>')
def api_match_ability(ability_id):
    """
    为指定场景能力匹配 Top3 场景机会。

    参数:
        ability_id (int): 场景能力的序号 ID

    返回格式：
      {
        source: {能力的基本信息},
        matches: [{target: {...}, domain_score, text_score, total_score}, ...] (最多3条)
      }
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

    # 构造返回结果
    result = {
        'source': {
            'id':      ability['id'],
            'name':    ability['name'],
            'company': ability['company'],
            'domain':  ability['domain'],
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
            'domain_score': m['domain_score'],
            'text_score':   m['text_score'],
            'total_score':  m['total_score'],
        } for m in matches],
    }
    return jsonify(result)


@app.route('/api/match/opportunity/<int:opp_id>')
def api_match_opportunity(opp_id):
    """
    为指定场景机会匹配 Top3 场景能力。

    参数:
        opp_id (int): 场景机会的序号 ID

    返回格式：
      {
        source: {机会的基本信息},
        matches: [{target: {...}, domain_score, text_score, total_score}, ...] (最多3条)
      }
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
        'source': {
            'id':     opp['id'],
            'name':   opp['name'],
            'domain': opp['domain'],
        },
        'matches': [{
            'target': {
                'id':              m['target']['id'],
                'name':            m['target']['name'],
                'company':         m['target']['company'],
                'domain':          m['target']['domain'],
                'overview':        m['target']['overview'],
                'highlight':       m['target']['highlight'],
                'effect':          m['target']['effect'],
                'target_customer': m['target']['target_customer'],
            },
            'domain_score': m['domain_score'],
            'text_score':   m['text_score'],
            'total_score':  m['total_score'],
        } for m in matches],
    }
    return jsonify(result)


# ============================================================================
# 程序入口
# ============================================================================
if __name__ == '__main__':
    print()
    print('=' * 60)
    print('  场景机会与能力匹配 Demo — 后端服务')
    print(f'  访问地址: http://127.0.0.1:5000')
    print('=' * 60)
    app.run(host='127.0.0.1', port=5000, debug=True)
