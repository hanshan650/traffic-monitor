"""
Redis 数据服务 — 实时交通数据缓存 & 消息队列 & 预警机制
Redis 在此项目中的核心价值：
1. 实时车流量计数（Hash）— 毫秒级更新
2. 预警消息队列（List）— 高并发场景下的削峰
3. 拥堵排行榜（Sorted Set）— 实时路段拥堵排名
4. 路段热力图缓存（String JSON）— 降低 MongoDB 读取压力
5. 分布式锁（SET NX）— 防止重复处理同一帧
6. 预警限流（计数器）— 避免重复告警风暴
7. 实时订阅推送（Pub/Sub）— WebSocket 替代方案
"""
import json
import time
from datetime import datetime
import redis


class RedisService:
    """Redis 服务类"""
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init_app(self, app):
        self._client = redis.Redis(
            host=app.config['REDIS_HOST'],
            port=app.config['REDIS_PORT'],
            db=app.config['REDIS_DB'],
            password=app.config['REDIS_PASSWORD'],
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        self._client.ping()
        self._prefix = app.config['REDIS_KEY_PREFIX']
        return self

    @property
    def client(self):
        return self._client

    def _k(self, name):
        return f"{self._prefix}{name}"

    # ==================== 1. 实时车流量计数（Hash） ====================

    def traffic_count_increment(self, road_id, vehicle_type, delta=1):
        """增加某路段某车型计数"""
        key = self._k(f'road:{road_id}:vehicles')
        self._client.hincrby(key, vehicle_type, delta)
        self._client.hincrby(key, 'total', delta)
        self._client.expire(key, 10)  # 10秒过期

    def traffic_count_get(self, road_id):
        """获取某路段当前车流量"""
        data = self._client.hgetall(self._k(f'road:{road_id}:vehicles'))
        return {k: int(v) for k, v in data.items()} if data else {}

    def traffic_count_get_all(self):
        """获取所有路段车流量"""
        result = {}
        keys = self._client.keys(self._k('road:*:vehicles'))
        for key in keys:
            road_id = key.decode() if isinstance(key, bytes) else key
            road_id = road_id.replace(self._k('road:'), '').replace(':vehicles', '')
            result[road_id] = {
                k: int(v) for k, v in self._client.hgetall(key).items()
            }
        return result

    # ==================== 2. 实时交通快照缓存（String JSON） ====================

    def snapshot_set(self, camera_id, data, ttl=60):
        """缓存最新检测快照（默认 60 秒，与 CACHE_TTL_DETECTION_RESULT 一致）"""
        self._client.setex(
            self._k(f'snapshot:{camera_id}'),
            ttl,
            json.dumps(data, default=str)
        )

    def snapshot_get(self, camera_id):
        """获取最新检测快照"""
        data = self._client.get(self._k(f'snapshot:{camera_id}'))
        return json.loads(data) if data else None

    def snapshot_get_all(self):
        """获取所有摄像头最新快照"""
        keys = self._client.keys(self._k('snapshot:*'))
        snapshots = {}
        for key in keys:
            camera_id = (key.decode() if isinstance(key, bytes) else key).replace(self._k('snapshot:'), '')
            data = self._client.get(key)
            if data:
                snapshots[camera_id] = json.loads(data)
        return snapshots

    # ==================== 3. 拥堵排行榜（Sorted Set） ====================

    def congestion_rank_update(self, road_id, vehicle_count):
        """更新拥堵排行"""
        self._client.zadd(self._k('congestion_rank'), {road_id: vehicle_count})

    def congestion_rank_top(self, n=10):
        """Top N 拥堵路段"""
        return self._client.zrevrange(
            self._k('congestion_rank'), 0, n - 1, withscores=True
        )

    def congestion_rank_get(self, road_id):
        """获取某路段拥堵排名"""
        rank = self._client.zrevrank(self._k('congestion_rank'), road_id)
        return rank + 1 if rank is not None else None

    # ==================== 4. 消息队列 — 预警推送（List） ====================

    def alert_push(self, alert_type, data):
        """推送预警消息到队列"""
        payload = json.dumps({
            'type': alert_type,
            'data': data,
            'timestamp': datetime.utcnow().isoformat()
        }, default=str)
        self._client.lpush(self._k('mq:traffic_alert'), payload)
        # 保留最近 1000 条
        self._client.ltrim(self._k('mq:traffic_alert'), 0, 999)

    def alert_pop(self, timeout=0):
        """阻塞获取预警消息"""
        result = self._client.brpop(self._k('mq:traffic_alert'), timeout=timeout)
        if result:
            return json.loads(result[1])
        return None

    def alert_range(self, start=0, end=19):
        """获取最近 N 条预警"""
        items = self._client.lrange(self._k('mq:traffic_alert'), start, end)
        return [json.loads(i) for i in items]

    def alert_count(self):
        """预警队列长度"""
        return self._client.llen(self._k('mq:traffic_alert'))

    # ==================== 5. 预警限流（防止告警风暴） ====================

    def alert_throttle_check(self, road_id, window_seconds=60):
        """检查某路段是否在限流窗口内已告警"""
        key = self._k(f'alert_throttle:{road_id}')
        if self._client.exists(key):
            return False  # 已告警，限流中
        self._client.setex(key, window_seconds, '1')
        return True

    # ==================== 6. 分布式锁 ====================

    def lock_acquire(self, name, ttl=5):
        """获取分布式锁"""
        return self._client.set(self._k(f'lock:{name}'), '1', nx=True, ex=ttl)

    def lock_release(self, name):
        """释放锁"""
        self._client.delete(self._k(f'lock:{name}'))

    # ==================== 7. 平均速度追踪（Hash） ====================

    def speed_record(self, road_id, speed):
        """记录车辆速度"""
        key = self._k(f'road:{road_id}:speeds')
        self._client.lpush(key, speed)
        self._client.ltrim(key, 0, 99)  # 保留最近100条

    def speed_avg(self, road_id):
        """计算平均速度"""
        key = self._k(f'road:{road_id}:speeds')
        speeds = self._client.lrange(key, 0, -1)
        if not speeds:
            return 0
        return sum(float(s) for s in speeds) / len(speeds)

    # ==================== 8. 事故统计缓存 ====================

    def accident_stats_cache(self, stats, ttl=300):
        """缓存事故统计"""
        self._client.setex(self._k('accident_stats'), ttl, json.dumps(stats, default=str))

    def accident_stats_get(self):
        """获取缓存的事故统计"""
        data = self._client.get(self._k('accident_stats'))
        return json.loads(data) if data else None


redis_service = RedisService()
