"""
检测服务 — 整合 YOLO 检测 + MongoDB 存储 + Redis 实时更新 + Neo4j 路网更新
"""
import os
from datetime import datetime
from bson import ObjectId
from models.mongodb_models import mongo
from models.redis_models import redis_service
from models.neo4j_models import neo4j_db
from utils.yolo_utils import detect_vehicles, analyze_traffic_flow
from config import Config


class DetectionService:

    @staticmethod
    def process_image(image_path, camera_id, road_id=None):
        """
        处理单张图片：
        1. YOLO 检测车辆
        2. 存入 MongoDB
        3. 更新 Redis 实时缓存
        4. 检查预警阈值 → Redis 消息队列
        5. 更新 Neo4j 路网拥堵状态
        """
        # 1. YOLO 检测
        detection_result = detect_vehicles(
            image_path, Config.YOLO_CONFIDENCE_THRESHOLD
        )

        # 2. 交通流量分析
        analysis = analyze_traffic_flow(detection_result, road_id, camera_id)

        # 3. 存入 MongoDB — 文档模型：灵活嵌套检测结果
        mongo_doc = {
            'camera_id': camera_id,
            'road_id': road_id,
            'image_path': image_path,
            'total_vehicles': analysis['total_vehicles'],
            'vehicle_counts': analysis['vehicle_counts'],
            'congestion_level': analysis['congestion_level'],
            'risk_level': analysis['risk_level'],
            'detections': analysis['detections'],  # 嵌套完整的检测框数据！
            'timestamp': datetime.utcnow(),
        }
        result = mongo.detections.insert_one(mongo_doc)
        mongo_doc['_id'] = str(result.inserted_id)

        # 4. 更新 Redis 实时缓存（TTL 使用配置中的检测结果缓存时间）
        redis_service.snapshot_set(camera_id, {
            'total_vehicles': analysis['total_vehicles'],
            'vehicle_counts': analysis['vehicle_counts'],
            'congestion_level': analysis['congestion_level'],
            'risk_level': analysis['risk_level'],
            'detection_id': str(result.inserted_id),
            'timestamp': analysis['timestamp'],
        }, ttl=Config.CACHE_TTL_DETECTION_RESULT)

        # 5. 更新 Redis 路段车流量
        if road_id:
            for vtype, count in analysis['vehicle_counts'].items():
                redis_service.traffic_count_increment(road_id, vtype, count)

            # 拥堵排行
            redis_service.congestion_rank_update(
                road_id, analysis['total_vehicles']
            )

            # 更新 Neo4j 路网拥堵状态
            try:
                neo4j_db.update_road_congestion(
                    road_id, analysis['congestion_level'],
                    analysis['total_vehicles'], 0
                )
            except:
                pass

        # 6. 预警检查
        DetectionService._check_alert(analysis, camera_id)

        return mongo_doc

    @staticmethod
    def _check_alert(analysis, camera_id):
        """检查是否触发预警"""
        total = analysis['total_vehicles']
        road_id = analysis.get('road_id', '')
        congestion = analysis['congestion_level']

        # 严重拥堵预警
        if congestion in ('heavy', 'moderate') and road_id:
            if redis_service.alert_throttle_check(road_id, window_seconds=60):
                alert_data = {
                    'alert_type': 'congestion',
                    'camera_id': camera_id,
                    'road_id': road_id,
                    'congestion_level': congestion,
                    'vehicle_count': total,
                    'counts': analysis['vehicle_counts'],
                    'message': f'路段 {road_id} 出现{congestion}拥堵，当前车流量 {total} 辆'
                }
                redis_service.alert_push('congestion', alert_data)

    @staticmethod
    def process_video_frame(frame_data, camera_id, road_id=None):
        """
        处理视频帧（字典格式的检测结果）
        用于实时视频流处理
        """
        analysis = analyze_traffic_flow(frame_data, road_id, camera_id)

        mongo_doc = {
            'camera_id': camera_id,
            'road_id': road_id,
            'total_vehicles': analysis['total_vehicles'],
            'vehicle_counts': analysis['vehicle_counts'],
            'congestion_level': analysis['congestion_level'],
            'risk_level': analysis['risk_level'],
            'detections': analysis['detections'],
            'timestamp': datetime.utcnow(),
        }
        result = mongo.detections.insert_one(mongo_doc)

        redis_service.snapshot_set(camera_id, {
            'total_vehicles': analysis['total_vehicles'],
            'congestion_level': analysis['congestion_level'],
            'detection_id': str(result.inserted_id),
            'timestamp': datetime.utcnow().isoformat(),
        }, ttl=Config.CACHE_TTL_DETECTION_RESULT)

        if road_id:
            redis_service.congestion_rank_update(road_id, analysis['total_vehicles'])

        DetectionService._check_alert(analysis, camera_id)
        return str(result.inserted_id)

    @staticmethod
    def get_recent_detections(camera_id=None, road_id=None, page=1, per_page=20):
        """获取最近的检测记录"""
        filter_cond = {}
        if camera_id:
            filter_cond['camera_id'] = camera_id
        if road_id:
            filter_cond['road_id'] = road_id

        total = mongo.detections.count_documents(filter_cond)
        docs = list(
            mongo.detections.find(filter_cond)
            .sort([('timestamp', -1)])
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        for d in docs:
            d['_id'] = str(d['_id'])

        return {
            'detections': docs,
            'total': total,
            'page': page,
            'total_pages': (total + per_page - 1) // per_page
        }

    @staticmethod
    def get_detection_stats(hours=24):
        """获取检测统计（MongoDB 聚合）"""
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(hours=hours)

        pipeline = [
            {'$match': {'timestamp': {'$gte': since}}},
            {'$group': {
                '_id': '$congestion_level',
                'count': {'$sum': 1},
                'avg_vehicles': {'$avg': '$total_vehicles'},
                'max_vehicles': {'$max': '$total_vehicles'},
            }}
        ]
        return list(mongo.detections.aggregate(pipeline))

    @staticmethod
    def get_daily_trend(days=7):
        """获取每日车流量趋势"""
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(days=days)

        pipeline = [
            {'$match': {'timestamp': {'$gte': since}}},
            {'$group': {
                '_id': {
                    '$dateToString': {
                        'format': '%Y-%m-%d %H:00',
                        'date': '$timestamp'
                    }
                },
                'avg_vehicles': {'$avg': '$total_vehicles'},
                'total_detections': {'$sum': 1},
            }},
            {'$sort': {'_id': 1}},
            {'$limit': 168}  # 7天 * 24小时
        ]
        return list(mongo.detections.aggregate(pipeline))
