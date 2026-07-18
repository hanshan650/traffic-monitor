"""主路由 — 首页 Dashboard、实时大屏、数据统计"""
from flask import Blueprint, render_template, jsonify, request, session
from services.detection_service import DetectionService
from services.accident_service import AccidentService
from services.road_network_service import RoadNetworkService
from models.redis_models import redis_service
from models.mongodb_models import mongo

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """首页 Dashboard"""
    # 获取实时交通快照
    snapshots = redis_service.snapshot_get_all()

    # 拥堵排行 Top 5
    congestion_top = redis_service.congestion_rank_top(5)

    # 最近预警
    recent_alerts = redis_service.alert_range(0, 4)

    # 事故统计
    accident_stats = AccidentService.get_accident_stats()

    # 路网摘要
    network_summary = RoadNetworkService.get_network_summary()

    # 最近检测
    recent = DetectionService.get_recent_detections(per_page=6)

    return render_template('index.html',
                           snapshots=snapshots,
                           congestion_top=congestion_top,
                           recent_alerts=recent_alerts,
                           accident_stats=accident_stats,
                           network_summary=network_summary,
                           recent_detections=recent['detections'])


@main_bp.route('/dashboard')
def dashboard():
    """实时监控大屏"""
    snapshots = redis_service.snapshot_get_all()
    congestion_top = redis_service.congestion_rank_top(10)
    recent_alerts = redis_service.alert_range(0, 9)
    accident_stats = AccidentService.get_accident_stats()

    return render_template('dashboard.html',
                           snapshots=snapshots,
                           congestion_top=congestion_top,
                           recent_alerts=recent_alerts,
                           accident_stats=accident_stats)


@main_bp.route('/api/snapshots')
def api_snapshots():
    """API: 实时交通快照"""
    return jsonify(redis_service.snapshot_get_all())


@main_bp.route('/api/congestion-rank')
def api_congestion_rank():
    """API: 拥堵排行"""
    top = redis_service.congestion_rank_top(10)
    return jsonify([{'road_id': r, 'count': int(c)} for r, c in top])


@main_bp.route('/api/recent-alerts')
def api_recent_alerts():
    """API: 最近预警"""
    return jsonify(redis_service.alert_range(0, 9))


@main_bp.route('/stats')
def stats_page():
    """数据统计页面"""
    # 检测统计
    detection_stats = DetectionService.get_detection_stats(24)
    daily_trend = DetectionService.get_daily_trend(7)
    accident_stats = AccidentService.get_accident_stats()
    network_summary = RoadNetworkService.get_network_summary()

    return render_template('stats.html',
                           detection_stats=detection_stats,
                           daily_trend=daily_trend,
                           accident_stats=accident_stats,
                           network_summary=network_summary)


@main_bp.route('/road-network')
def road_network():
    """路网可视化页面"""
    intersections = RoadNetworkService.get_intersections()
    congested = RoadNetworkService.get_congested_roads()
    return render_template('road_network.html',
                           intersections=intersections,
                           congested_roads=congested)


@main_bp.route('/api/road-network')
def api_road_network():
    """API: 返回路网数据（GeoJSON 格式，供地图渲染）"""
    from models.neo4j_models import neo4j_db
    from models.redis_models import redis_service
    import json

    try:
        # 获取所有路口
        nodes = neo4j_db.run("""
            MATCH (i:Intersection)
            RETURN i.id AS id, i.name AS name, i.lat AS lat, i.lng AS lng
        """)
        node_map = {}
        features = []
        for n in nodes:
            node_map[n['id']] = n
            features.append({
                'id': n['id'],
                'name': n['name'],
                'lng': float(n['lng']),
                'lat': float(n['lat']),
            })

        # 获取所有路段及拥堵状态
        edges_raw = neo4j_db.run("""
            MATCH (a:Intersection)-[r:CONNECTS]->(b:Intersection)
            WHERE r.id IS NOT NULL AND NOT r.id ENDS WITH '_rev'
            RETURN r.id AS id, r.name AS name, a.id AS from_id, b.id AS to_id,
                   r.length AS length, r.speed_limit AS speed_limit,
                   r.congestion_level AS congestion, r.vehicle_count AS vehicles,
                   r.lanes AS lanes
            ORDER BY r.id
        """)

        edges = []
        for e in edges_raw:
            # 实时拥堵数据优先使用 Redis
            road_id = e['id']
            redis_traffic = redis_service.traffic_count_get(road_id)
            total_v = redis_traffic.get('total', 0) if redis_traffic else 0

            congestion = e.get('congestion', 'normal')
            if total_v >= 50:
                congestion = 'heavy'
            elif total_v >= 30:
                congestion = 'moderate'
            elif total_v >= 15:
                congestion = 'light'

            edges.append({
                'id': road_id,
                'name': e['name'],
                'from': e['from_id'],
                'to': e['to_id'],
                'from_lng': float(node_map[e['from_id']]['lng']) if e['from_id'] in node_map else 0,
                'from_lat': float(node_map[e['from_id']]['lat']) if e['from_id'] in node_map else 0,
                'to_lng': float(node_map[e['to_id']]['lng']) if e['to_id'] in node_map else 0,
                'to_lat': float(node_map[e['to_id']]['lat']) if e['to_id'] in node_map else 0,
                'length': float(e['length']) if e.get('length') else 0,
                'speed_limit': int(e['speed_limit']) if e.get('speed_limit') else 60,
                'lanes': int(e['lanes']) if e.get('lanes') else 2,
                'congestion': congestion,
                'vehicles': total_v or e.get('vehicles', 0),
            })

        return jsonify({
            'success': True,
            'nodes': features,
            'edges': edges,
            'stats': {
                'nodes': len(features),
                'edges': len(edges),
                'heavy': sum(1 for e in edges if e['congestion'] == 'heavy'),
                'moderate': sum(1 for e in edges if e['congestion'] == 'moderate'),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@main_bp.route('/monitor-wall')
def monitor_wall():
    """多路监控大屏"""
    return render_template('monitor_wall.html')


@main_bp.route('/api/amap-route')
def api_amap_route():
    """
    高德地图驾车路线规划 API
    使用 Web Service Key（需在 https://console.amap.com/ 申请"Web服务"类型）
    返回完整路线坐标，前端绘制导航路径
    """
    import requests as req
    from flask import current_app
    
    origin = request.args.get('origin', '121.4737,31.2304')
    destination = request.args.get('destination', '121.3200,31.1970')
    
    web_key = current_app.config.get('AMAP_WEB_KEY', '')
    if not web_key:
        return jsonify({'success': False, 'error': '未配置高德 Web Service Key，请在 .env 中设置 AMAP_WEB_KEY'}), 500

    try:
        resp = req.get('https://restapi.amap.com/v3/direction/driving', params={
            'key': web_key,
            'origin': origin,
            'destination': destination,
            'strategy': '0',
            'extensions': 'all',
            'show_fields': 'polyline',
        }, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = resp.json()

        if data.get('status') == '1' and data.get('route', {}).get('paths'):
            path = data['route']['paths'][0]
            steps = []
            for s in path.get('steps', []):
                coords = _decode_amap_polyline(s.get('polyline', ''))
                # 交通状态映射
                tmc_status = s.get('tmcs', [{}])[0].get('status', '') if s.get('tmcs') else ''
                steps.append({
                    'road': s.get('road', ''),
                    'instruction': s.get('instruction', ''),
                    'distance': int(s.get('distance', 0)),
                    'duration': int(s.get('duration', 0)),
                    'polyline': coords,
                    'traffic_status': tmc_status,
                })
            return jsonify({
                'success': True,
                'distance': int(path.get('distance', 0)),
                'duration': int(path.get('duration', 0)),
                'steps': steps,
                'traffic_light': int(path.get('traffic_light', 0)),
            })
        return jsonify({'success': False, 'error': data.get('info', '规划失败')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _decode_amap_polyline(polyline_str):
    """
    解码高德地图 polyline 编码字符串
    格式：坐标差值 + 字符编码的压缩格式
    """
    if not polyline_str:
        return []
    
    coords = []
    # 高德 polyline 使用类似 Google 的编码算法
    # 但 coordtype 可能不同，这里直接解析 lng,lat 对
    # 简化：polyline 格式为 "lng1,lat1;lng2,lat2;..."
    if ';' in polyline_str:
        for pair in polyline_str.split(';'):
            parts = pair.split(',')
            if len(parts) == 2:
                coords.append([float(parts[0]), float(parts[1])])
    else:
        # 可能是单点
        parts = polyline_str.split(',')
        if len(parts) == 2:
            coords.append([float(parts[0]), float(parts[1])])
    
    return coords


@main_bp.route('/api/amap-geocode')
def api_amap_geocode():
    """高德地理编码 API 代理（地址→坐标）"""
    import requests as req
    from flask import current_app
    
    address = request.args.get('address', '')
    if not address:
        return jsonify({'success': False, 'error': '缺少 address 参数'}), 400

    web_key = current_app.config.get('AMAP_WEB_KEY', '')
    if not web_key:
        return jsonify({'success': False, 'error': '未配置 AMAP_WEB_KEY'}), 500

    try:
        resp = req.get('https://restapi.amap.com/v3/geocode/geo', params={
            'key': web_key, 'address': address, 'city': '上海',
        }, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = resp.json()
        if data.get('status') == '1' and data.get('geocodes'):
            geo = data['geocodes'][0]
            loc = geo['location'].split(',')
            return jsonify({
                'success': True,
                'lng': float(loc[0]), 'lat': float(loc[1]),
                'formatted_address': geo.get('formatted_address', ''),
            })
        return jsonify({'success': False, 'error': data.get('info', '解析失败')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
