"""
智能交通监测与事故预警系统 - 主应用入口
===========================================
基于 YOLOv8 + MongoDB + Redis + Neo4j 的非关系型数据库综合实践项目

数据库分工：
  MongoDB — 检测记录（灵活嵌套文档）、事故报告、用户数据
  Redis    — 实时车流量缓存、预警消息队列、拥堵排行榜、Session、限流
  Neo4j    — 道路网络拓扑图、事故因果图谱、绕行推荐（最短路径）

YOLOv8   — 车辆目标检测（图片/视频流）
"""
import os
from flask import Flask
from flask_session import Session
from config import config_map


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config_map.get(config_name, config_map['default']))

    # 确保上传目录存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # ==================== 初始化数据库连接 ====================

    # 1. MongoDB — 核心业务数据
    from models.mongodb_models import mongo
    mongo.init_app(app)

    # 2. Redis — 实时缓存 + 消息队列
    from models.redis_models import redis_service
    redis_service.init_app(app)

    # 3. Neo4j — 路网图 + 事故因果图
    neo4j_available = False
    try:
        from models.neo4j_models import neo4j_db
        neo4j_db.init_app(app)
        neo4j_available = True
    except Exception as e:
        print(f"[警告] Neo4j 连接失败: {e}")
        print("  路网图功能将不可用，但系统其他功能正常运行。")
        print("  请确保 Neo4j 已启动并检查连接配置。")

    # Flask-Session（Redis 后端）— 需要独立的二进制模式连接
    import redis as redis_lib
    session_redis = redis_lib.Redis(
        host=app.config['REDIS_HOST'],
        port=app.config['REDIS_PORT'],
        db=app.config['REDIS_DB'],
        password=app.config['REDIS_PASSWORD'],
        decode_responses=False,  # Flask-Session 存的是二进制 msgpack，不能 decode
        socket_connect_timeout=5,
        socket_timeout=5
    )
    app.config['SESSION_REDIS'] = session_redis
    Session(app)

    # ==================== 初始化演示数据 ====================
    with app.app_context():
        _init_demo_data(app, neo4j_available)

    # ==================== 注册蓝图 ====================
    from routes.main_routes import main_bp
    from routes.detection_routes import detection_bp
    from routes.accident_routes import accident_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(detection_bp)
    app.register_blueprint(accident_bp)

    # ==================== 全局模板变量 ====================
    @app.context_processor
    def inject_globals():
        from flask import session
        return {
            'session_user': session,
            'neo4j_available': neo4j_available,
        }

    # ==================== 模板过滤器 ====================
    @app.template_filter('congestion_color')
    def congestion_color_filter(level):
        colors = {
            'normal': 'success', 'light': 'info',
            'moderate': 'warning', 'heavy': 'danger'
        }
        return colors.get(level, 'secondary')

    @app.template_filter('congestion_label')
    def congestion_label_filter(level):
        labels = {
            'normal': '畅通', 'light': '轻度拥堵',
            'moderate': '中度拥堵', 'heavy': '严重拥堵'
        }
        return labels.get(level, level)

    @app.template_filter('severity_label')
    def severity_label_filter(level):
        labels = {
            'minor': '轻微', 'moderate': '一般',
            'severe': '严重', 'fatal': '致命'
        }
        return labels.get(level, level)

    @app.template_filter('weather_label')
    def weather_label_filter(val):
        labels = {
            'sunny': '晴天', 'rain': '雨天',
            'snow': '雪天', 'fog': '雾天'
        }
        return labels.get(val, val)

    @app.template_filter('road_condition_label')
    def road_condition_label_filter(val):
        labels = {
            'dry': '干燥', 'wet': '湿滑',
            'icy': '结冰', 'damaged': '损坏'
        }
        return labels.get(val, val)

    @app.template_filter('vehicle_type_label')
    def vehicle_type_label_filter(val):
        labels = {
            'car': '小汽车', 'bus': '公交车',
            'truck': '卡车', 'motorcycle': '摩托车',
            'bicycle': '自行车'
        }
        return labels.get(val, val)

    @app.template_filter('status_label')
    def status_label_filter(val):
        labels = {
            'reported': '已上报', 'processing': '处理中',
            'resolved': '已解决'
        }
        return labels.get(val, val)

    @app.template_filter('risk_level_label')
    def risk_level_label_filter(val):
        labels = {
            'high': '高风险', 'medium': '中风险',
            'low': '低风险'
        }
        return labels.get(val, val)

    @app.template_filter('time_ago')
    def time_ago_filter(dt):
        from datetime import datetime
        if not dt:
            return ''
        now = datetime.utcnow()
        diff = now - dt
        if diff.days > 0:
            return f'{diff.days}天前'
        if diff.seconds > 3600:
            return f'{diff.seconds // 3600}小时前'
        if diff.seconds > 60:
            return f'{diff.seconds // 60}分钟前'
        return '刚刚'

    # ==================== 错误处理 ====================
    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template('500.html'), 500

    return app


def _init_demo_data(app, neo4j_available):
    """初始化演示数据：摄像头、示例事故、路网"""
    from models.mongodb_models import mongo

    # 初始化摄像头数据
    cameras = [
        {'camera_id': 'CAM_001', 'road_id': 'R001', 'name': '解放大道东', 'lat': 30.593, 'lng': 114.307},
        {'camera_id': 'CAM_002', 'road_id': 'R002', 'name': '解放大道中', 'lat': 30.595, 'lng': 114.312},
        {'camera_id': 'CAM_003', 'road_id': 'R006', 'name': '珞喻路光谷段', 'lat': 30.510, 'lng': 114.395},
        {'camera_id': 'CAM_004', 'road_id': 'R007', 'name': '武珞路街道口', 'lat': 30.530, 'lng': 114.356},
        {'camera_id': 'CAM_005', 'road_id': 'R010', 'name': '长江二桥引桥', 'lat': 30.590, 'lng': 114.330},
        {'camera_id': 'CAM_006', 'road_id': 'R005', 'name': '建设大道汉口站', 'lat': 30.598, 'lng': 114.316},
        {'camera_id': 'CAM_SIM', 'road_id': 'R001', 'name': '模拟监测点', 'lat': 30.593, 'lng': 114.306},
    ]
    for cam in cameras:
        mongo.cameras.update_one(
            {'camera_id': cam['camera_id']}, {'$set': cam}, upsert=True
        )

    # 初始化路网数据到 Neo4j
    if neo4j_available:
        try:
            from services.road_network_service import RoadNetworkService
            RoadNetworkService.init_demo_network()
        except Exception as e:
            print(f"[警告] 路网初始化失败: {e}")

    # 初始化示例事故数据
    sample_accidents = [
        {
            'road_id': 'R001', 'severity': 'moderate', 'weather': 'rain',
            'road_condition': 'wet', 'vehicle_types': ['car', 'car'],
            'description': '两辆小轿车追尾事故，因雨天路面湿滑刹车不及',
            'status': 'resolved', 'timestamp': __import__('datetime').datetime(2026, 7, 1, 8, 30),
        },
        {
            'road_id': 'R006', 'severity': 'severe', 'weather': 'fog',
            'road_condition': 'wet', 'vehicle_types': ['car', 'bus', 'car'],
            'description': '大雾天气多车连环追尾，涉及1辆公交车和2辆小轿车',
            'status': 'resolved', 'timestamp': __import__('datetime').datetime(2026, 7, 2, 7, 15),
        },
    ]
    for acc in sample_accidents:
        existing = mongo.accidents.find_one({
            'road_id': acc['road_id'],
            'description': acc['description']
        })
        if not existing:
            result = mongo.accidents.insert_one(acc)
            acc_id = str(result.inserted_id)
        else:
            acc_id = str(existing['_id'])

        # 同步到 Neo4j 因果图谱（每次都同步，确保已有数据也更新）
        if neo4j_available:
            try:
                from models.neo4j_models import neo4j_db
                neo4j_db.create_accident_node(acc_id, acc['severity'], acc['description'])
                neo4j_db.link_accident_to_road(acc_id, acc['road_id'])
                for vt in acc['vehicle_types']:
                    neo4j_db.link_accident_to_factors(
                        acc_id, acc['weather'], acc['road_condition'], vt
                    )
            except Exception as e:
                pass  # 静默处理，节点已存在时 MERGE 不会重复创建

    print("  ✓ 演示数据初始化完成")


# 创建应用实例
app = create_app()

if __name__ == '__main__':
    banner = """
╔══════════════════════════════════════════════════════════╗
║        🚗 智能交通监测与事故预警系统                      ║
║        YOLOv8 + MongoDB + Redis + Neo4j                  ║
║        非关系型数据库综合实践项目                          ║
╚══════════════════════════════════════════════════════════╝
    """
    print(banner)
    print(f"  MongoDB: {app.config['MONGO_URI']}/{app.config['MONGO_DB_NAME']}")
    print(f"  Redis:   {app.config['REDIS_HOST']}:{app.config['REDIS_PORT']}")
    print(f"  Neo4j:   {app.config['NEO4J_URI']}")
    print(f"  访问地址: http://127.0.0.1:5000")
    print("-" * 60)

    app.run(host='0.0.0.0', port=5000, debug=app.config.get('DEBUG', True))
