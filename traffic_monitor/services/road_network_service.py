"""
路网服务 — Neo4j 路网拓扑管理和绕行推荐
"""
from models.neo4j_models import neo4j_db
from models.redis_models import redis_service


class RoadNetworkService:

    @staticmethod
    def init_demo_network():
        """
        初始化上海路网数据
        基于上海真实主要道路拓扑：内环、中环、延安高架、南北高架等
        """
        # 清除旧路网数据
        try:
            neo4j_db.run("MATCH (i:Intersection) DETACH DELETE i")
            neo4j_db.run("MATCH ()-[r:CONNECTS]->() DELETE r")
        except:
            pass

        # 上海主要路口/立交节点
        intersections = [
            ('I001', '人民广场', 31.2304, 121.4737),
            ('I002', '外滩', 31.2400, 121.4900),
            ('I003', '陆家嘴', 31.2400, 121.5000),
            ('I004', '静安寺', 31.2250, 121.4480),
            ('I005', '徐家汇', 31.1950, 121.4370),
            ('I006', '虹桥枢纽', 31.1970, 121.3200),
            ('I007', '上海南站', 31.1550, 121.4300),
            ('I008', '五角场', 31.3000, 121.5150),
            ('I009', '世纪大道', 31.2300, 121.5300),
            ('I010', '内环沪闵立交', 31.1700, 121.4200),
            ('I011', '中环北翟路', 31.2200, 121.3600),
            ('I012', '南北高架天目路', 31.2500, 121.4650),
        ]
        for iid, name, lat, lng in intersections:
            neo4j_db.create_intersection(iid, name, lat, lng)

        # 上海主要道路
        roads = [
            # 延安高架（东西大动脉）
            ('R001', '延安高架西段', 'I006', 'I004', 8.5, 80, 6),
            ('R002', '延安高架东段', 'I004', 'I001', 2.8, 80, 6),
            ('R003', '延安东路隧道', 'I001', 'I003', 2.2, 60, 4),

            # 南北高架（南北大动脉）
            ('R004', '南北高架北段', 'I008', 'I012', 5.5, 80, 6),
            ('R005', '南北高架中段', 'I012', 'I001', 2.0, 70, 4),
            ('R006', '南北高架南段', 'I001', 'I010', 3.5, 70, 4),

            # 内环高架
            ('R007', '内环西段', 'I010', 'I004', 6.0, 80, 6),
            ('R008', '内环北段', 'I004', 'I008', 7.5, 80, 6),
            ('R009', '内环东段', 'I008', 'I009', 5.0, 70, 4),
            ('R010', '内环南段', 'I009', 'I010', 8.0, 80, 6),

            # 中环
            ('R011', '中环西段', 'I007', 'I011', 9.5, 100, 8),
            ('R012', '中环北段', 'I011', 'I008', 8.0, 100, 8),

            # 沪闵高架
            ('R013', '沪闵高架', 'I010', 'I007', 4.5, 80, 6),
        ]
        for rid, name, from_i, to_i, length, speed, lanes in roads:
            neo4j_db.create_road(rid, name, from_i, to_i, length, speed, lanes)

        print(f"  ✓ 初始化上海路网: {len(intersections)} 个路口, {len(roads)} 条路段")
        return len(intersections), len(roads)

    @staticmethod
    def get_network_summary():
        """获取路网摘要"""
        try:
            result = neo4j_db.run("""
                MATCH (i:Intersection)
                WITH count(i) AS intersections
                MATCH ()-[r:CONNECTS]->()
                RETURN intersections, count(DISTINCT r.id) AS roads,
                       avg(r.length) AS avg_length,
                       sum(r.length) AS total_length
            """)
            if result:
                r = result[0]
                return {
                    'intersections': r['intersections'],
                    'roads': r['roads'],
                    'avg_length_km': round(r['avg_length'], 2),
                    'total_length_km': round(r['total_length'], 2),
                }
        except:
            pass
        return {'intersections': 0, 'roads': 0}

    @staticmethod
    def get_congested_roads():
        """获取拥堵路段"""
        try:
            return neo4j_db.get_congested_roads()
        except:
            return []

    @staticmethod
    def get_avoid_congestion_route(from_id, to_id):
        """绕行推荐"""
        try:
            return neo4j_db.find_avoid_congestion_path(from_id, to_id)
        except:
            return []

    @staticmethod
    def get_intersections():
        """获取所有路口"""
        try:
            return neo4j_db.run("""
                MATCH (i:Intersection)
                RETURN i.id AS id, i.name AS name, i.lat AS lat, i.lng AS lng
                ORDER BY i.name
            """)
        except:
            return []

    @staticmethod
    def _check_congestion_and_push_alert(road_id):
        """检查拥堵并推送预警（Redis）"""
        traffic = redis_service.traffic_count_get(road_id)
        total = traffic.get('total', 0)

        if total >= 50:
            congestion = 'heavy'
        elif total >= 30:
            congestion = 'moderate'
        elif total >= 15:
            congestion = 'light'
        else:
            congestion = 'normal'

        if congestion in ('heavy', 'moderate'):
            if redis_service.alert_throttle_check(road_id, window_seconds=60):
                redis_service.alert_push('congestion', {
                    'road_id': road_id,
                    'congestion_level': congestion,
                    'vehicle_count': total,
                    'message': f'路段拥堵预警: {road_id} ({congestion})'
                })
