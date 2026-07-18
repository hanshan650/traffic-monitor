"""事故路由 — 事故上报 & 预测分析"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from services.accident_service import AccidentService
from services.road_network_service import RoadNetworkService
from models.redis_models import redis_service

accident_bp = Blueprint('accident', __name__, url_prefix='/accident')


@accident_bp.route('/')
def accident_list():
    """事故列表"""
    page = request.args.get('page', 1, type=int)
    result = AccidentService.get_recent_accidents(page=page)
    return render_template('accident_list.html', **result)


@accident_bp.route('/report', methods=['GET', 'POST'])
def accident_report():
    """事故上报"""
    if request.method == 'POST':
        road_id = request.form.get('road_id', '').strip()
        severity = request.form.get('severity', 'moderate')
        description = request.form.get('description', '').strip()
        weather = request.form.get('weather', 'sunny')
        road_condition = request.form.get('road_condition', 'dry')
        vehicle_types = request.form.getlist('vehicle_types') or ['car']
        lat = request.form.get('lat', type=float)
        lng = request.form.get('lng', type=float)

        if not road_id or not description:
            flash('请填写必填字段', 'danger')
            return render_template('accident_report.html')

        try:
            AccidentService.create_accident(
                road_id=road_id, severity=severity,
                description=description, weather=weather,
                road_condition=road_condition,
                vehicle_types=vehicle_types,
                lat=lat, lng=lng
            )
            flash('事故报告已提交，相关部门将尽快处理', 'success')
            return redirect(url_for('accident.accident_list'))
        except Exception as e:
            flash(f'提交失败: {str(e)}', 'danger')

    return render_template('accident_report.html')


@accident_bp.route('/detail/<accident_id>')
def accident_detail(accident_id):
    """事故详情（含 Neo4j 因果链）"""
    result = AccidentService.get_accident_detail(accident_id)
    if not result['accident']:
        flash('事故记录不存在', 'danger')
        return redirect(url_for('accident.accident_list'))
    return render_template('accident_detail.html', **result)


@accident_bp.route('/edit/<accident_id>', methods=['GET', 'POST'])
def accident_edit(accident_id):
    """编辑事故"""
    result = AccidentService.get_accident_detail(accident_id)
    if not result['accident']:
        flash('事故记录不存在', 'danger')
        return redirect(url_for('accident.accident_list'))

    if request.method == 'POST':
        updates = {
            'road_id': request.form.get('road_id', '').strip(),
            'severity': request.form.get('severity', 'moderate'),
            'description': request.form.get('description', '').strip(),
            'weather': request.form.get('weather', 'sunny'),
            'road_condition': request.form.get('road_condition', 'dry'),
            'vehicle_types': request.form.getlist('vehicle_types') or ['car'],
            'status': request.form.get('status', 'reported'),
        }
        if not updates['road_id'] or not updates['description']:
            flash('请填写必填字段', 'danger')
            return render_template('accident_edit.html', **result)

        success, msg = AccidentService.update_accident(accident_id, updates)
        flash(msg, 'success' if success else 'danger')
        if success:
            return redirect(url_for('accident.accident_detail', accident_id=accident_id))

    return render_template('accident_edit.html', **result)


@accident_bp.route('/delete/<accident_id>', methods=['POST'])
def accident_delete(accident_id):
    """删除事故"""
    success, msg = AccidentService.delete_accident(accident_id)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('accident.accident_list'))


@accident_bp.route('/stats')
def accident_stats():
    """事故统计"""
    stats = AccidentService.get_accident_stats()
    return render_template('accident_stats.html', stats=stats)


@accident_bp.route('/alerts')
def alerts_page():
    """预警列表"""
    alerts = redis_service.alert_range(0, 49)
    return render_template('alerts.html', alerts=alerts)


@accident_bp.route('/api/predict', methods=['GET'])
def api_predict():
    """
    基于 Neo4j 因果图谱的事故风险预测
    根据当前天气 + 路况 + 拥堵数据，查询历史上相似条件下的事故频率
    """
    weather = request.args.get('weather', 'rain')
    road_condition = request.args.get('road_condition', 'wet')

    from models.neo4j_models import neo4j_db
    try:
        result = neo4j_db.run("""
            MATCH (a:Accident)-[:DURING_WEATHER]->(w:Weather {type: $weather})
            MATCH (a)-[:ROAD_WAS]->(rc:RoadCondition {type: $condition})
            RETURN count(a) AS accident_count,
                   avg(CASE WHEN a.severity = 'severe' THEN 1
                            WHEN a.severity = 'moderate' THEN 0.5
                            ELSE 0.2 END) AS avg_severity
        """, {'weather': weather, 'condition': road_condition})

        if result and result[0]:
            r = result[0]
            risk_score = round(float(r['avg_severity'] or 0) * float(r['accident_count'] or 1), 2)
            return jsonify({
                'weather': weather,
                'road_condition': road_condition,
                'similar_accidents': int(r['accident_count'] or 0),
                'risk_score': risk_score,
                'risk_level': 'high' if risk_score > 5 else 'medium' if risk_score > 2 else 'low',
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'No data'})
