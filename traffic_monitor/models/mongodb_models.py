"""
MongoDB 数据模型 — 核心业务数据存储
展示文档模型优势：灵活字段、嵌套结构、聚合查询、地理空间索引
"""
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT, GEOSPHERE


class MongoDB:
    """MongoDB 管理类 - 单例"""
    _instance = None
    _client = None
    _db = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init_app(self, app):
        self._client = MongoClient(app.config['MONGO_URI'])
        self._db = self._client[app.config['MONGO_DB_NAME']]
        self._setup_indexes()
        return self

    @property
    def db(self):
        return self._db

    @property
    def detections(self):
        """检测记录集合 - YOLO 每帧检测结果"""
        return self._db.detections

    @property
    def accidents(self):
        """事故报告集合"""
        return self._db.accidents

    @property
    def roads(self):
        """道路信息集合"""
        return self._db.roads

    @property
    def cameras(self):
        """摄像头/监测点集合"""
        return self._db.cameras

    @property
    def users(self):
        return self._db.users

    @property
    def traffic_snapshots(self):
        """交通快照集合 - 定时聚合"""
        return self._db.traffic_snapshots

    def _setup_indexes(self):
        """创建索引"""
        # 检测记录索引 — 按时间、路段、摄像头查询
        self.detections.create_index([('timestamp', DESCENDING)])
        self.detections.create_index([('camera_id', ASCENDING)])
        self.detections.create_index([('road_id', ASCENDING)])
        self.detections.create_index([('vehicle_type', ASCENDING)])
        self.detections.create_index([
            ('camera_id', ASCENDING),
            ('timestamp', DESCENDING)
        ])
        # TTL 索引：30 天后自动清理旧检测记录（节省存储）
        self.detections.create_index([('timestamp', ASCENDING)], expireAfterSeconds=2592000)

        # 事故记录索引
        self.accidents.create_index([('timestamp', DESCENDING)])
        self.accidents.create_index([('severity', ASCENDING)])
        self.accidents.create_index([('road_id', ASCENDING)])
        self.accidents.create_index([('location', GEOSPHERE)])

        # 道路索引
        self.roads.create_index([('road_id', ASCENDING)], unique=True)
        self.roads.create_index([('name', TEXT)])

        # 摄像头索引
        self.cameras.create_index([('camera_id', ASCENDING)], unique=True)
        self.cameras.create_index([('road_id', ASCENDING)])

        # 用户索引
        self.users.create_index([('username', ASCENDING)], unique=True)

        # 交通快照索引
        self.traffic_snapshots.create_index([('timestamp', DESCENDING)])
        self.traffic_snapshots.create_index([('road_id', ASCENDING)])


mongo = MongoDB()
