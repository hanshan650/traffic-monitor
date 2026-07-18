"""
智能交通监测与事故预警系统 - 配置管理
基于 YOLOv8 + MongoDB + Redis + Neo4j 的非关系型数据库综合实践项目
"""
import os
from datetime import timedelta


class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'traffic-monitor-secret-2026')
    
    # ==================== MongoDB 配置 ====================
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'traffic_monitor')
    
    # ==================== Redis 配置 ====================
    REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
    REDIS_DB = int(os.environ.get('REDIS_DB', 0))
    REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)
    REDIS_KEY_PREFIX = 'traffic:'
    
    # ==================== Neo4j 配置 ====================
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', '12345678')
    
    # ==================== Session 配置（Redis 后端） ====================
    SESSION_TYPE = 'redis'
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # ==================== YOLO 配置 ====================
    YOLO_MODEL_PATH = os.environ.get('YOLO_MODEL_PATH', 'yolov8n.pt')
    YOLO_CONFIDENCE_THRESHOLD = float(os.environ.get('YOLO_CONF_THRESHOLD', 0.3))
    
    # ==================== 高德地图配置 ====================
    # JS API Key（用于前端地图展示）
    AMAP_JS_KEY = os.environ.get('AMAP_JS_KEY', 'a1fc0ec5f3b78143136030409f1c6e59')
    # Web Service Key（用于后端路线规划 API，需在 https://console.amap.com/ 申请）
    AMAP_WEB_KEY = os.environ.get('AMAP_WEB_KEY', '940441541dffb04f3a132e46ddec7716')
    
    # ==================== 预警阈值配置 ====================
    TRAFFIC_LIGHT_THRESHOLD = 15     # 帧内车辆数 >= 15 → 轻度拥堵
    TRAFFIC_MODERATE_THRESHOLD = 30  # 帧内车辆数 >= 30 → 中度拥堵
    TRAFFIC_HEAVY_THRESHOLD = 50     # 帧内车辆数 >= 50 → 严重拥堵
    ACCIDENT_RISK_SPEED = 80         # 平均速度 > 80km/h → 事故风险升高
    
    # ==================== 缓存 TTL（秒） ====================
    CACHE_TTL_TRAFFIC_SNAPSHOT = 5       # 实时交通快照 5 秒
    CACHE_TTL_ROAD_HEATMAP = 60          # 路段热力图 1 分钟
    CACHE_TTL_ACCIDENT_STATS = 300       # 事故统计缓存 5 分钟
    CACHE_TTL_DETECTION_RESULT = 60      # 检测结果缓存 1 分钟
    
    # ==================== 分页 ====================
    PAGE_SIZE_DETECTIONS = 20
    PAGE_SIZE_ACCIDENTS = 10
    
    # ==================== 上传配置 ====================
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'avi', 'mov'}
    
    # ==================== YOLO 车辆类别 ====================
    # COCO 数据集中车辆相关类别 ID
    VEHICLE_CLASSES = {
        2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck',
        1: 'bicycle', 9: 'traffic_light'
    }
    
    # ==================== 消息队列名称 ====================
    MQ_TRAFFIC_ALERT = 'mq:traffic_alert'
    MQ_ACCIDENT_ALERT = 'mq:accident_alert'
    MQ_SYSTEM_LOG = 'mq:system_log'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
