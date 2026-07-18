"""
Neo4j 图数据库模型 — 路网拓扑 & 事故因果图谱
Neo4j 在此项目中的核心价值：
1. 道路网络是天然的图结构（节点=路口/路段，边=连接关系）
2. 事故因果图谱（天气→路面状态→事故类型→伤亡）
3. 拥堵传播路径分析（Cypher 图遍历）
4. 最优绕行路线推荐（加权最短路径）
"""
from neo4j import GraphDatabase


class Neo4jDB:
    """Neo4j 管理类 - 单例"""
    _instance = None
    _driver = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init_app(self, app):
        self._driver = GraphDatabase.driver(
            app.config['NEO4J_URI'],
            auth=(app.config['NEO4J_USER'], app.config['NEO4J_PASSWORD'])
        )
        self._driver.verify_connectivity()
        self._setup_constraints()
        return self

    @property
    def driver(self):
        return self._driver

    def run(self, query, params=None):
        """执行 Cypher 查询"""
        with self._driver.session() as session:
            return list(session.run(query, params or {}))

    def run_single(self, query, params=None):
        """执行查询并返回单条记录"""
        records = self.run(query, params)
        return records[0] if records else None

    def _setup_constraints(self):
        """创建约束和索引"""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Intersection) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Road) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Accident) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Camera) REQUIRE c.id IS UNIQUE",
        ]
        for c in constraints:
            try:
                self.run(c)
            except:
                pass  # 约束已存在时忽略

    # ==================== 路网构建 ====================

    def create_intersection(self, intersection_id, name, lat, lng):
        """创建路口节点"""
        return self.run("""
            MERGE (i:Intersection {id: $id})
            SET i.name = $name, i.lat = $lat, i.lng = $lng, i.updated_at = datetime()
        """, {'id': intersection_id, 'name': name, 'lat': lat, 'lng': lng})

    def create_road(self, road_id, name, from_intersection, to_intersection,
                    length, speed_limit, lanes):
        """创建路段（边）连接两个路口"""
        return self.run("""
            MATCH (a:Intersection {id: $from_id})
            MATCH (b:Intersection {id: $to_id})
            MERGE (a)-[r:CONNECTS {id: $road_id}]->(b)
            SET r.name = $name, r.length = $length, 
                r.speed_limit = $speed_limit, r.lanes = $lanes,
                r.congestion_level = 'normal', r.avg_speed = $speed_limit,
                r.updated_at = datetime()
            MERGE (b)-[r2:CONNECTS {id: $road_id + '_rev'}]->(a)
            SET r2.name = $name + '(反向)', r2.length = $length,
                r2.speed_limit = $speed_limit, r2.lanes = $lanes,
                r2.congestion_level = 'normal', r2.avg_speed = $speed_limit,
                r2.updated_at = datetime()
        """, {
            'road_id': road_id, 'name': name,
            'from_id': from_intersection, 'to_id': to_intersection,
            'length': length, 'speed_limit': speed_limit, 'lanes': lanes
        })

    def update_road_congestion(self, road_id, congestion_level, vehicle_count, avg_speed):
        """更新路段拥堵状态（Redis 触发）"""
        return self.run("""
            MATCH ()-[r:CONNECTS {id: $road_id}]->()
            SET r.congestion_level = $level,
                r.vehicle_count = $count,
                r.avg_speed = $speed,
                r.updated_at = datetime()
            RETURN r
        """, {'road_id': road_id, 'level': congestion_level,
              'count': vehicle_count, 'speed': avg_speed})

    def get_congested_roads(self, level='heavy'):
        """查询拥堵路段"""
        return self.run("""
            MATCH (a:Intersection)-[r:CONNECTS]->(b:Intersection)
            WHERE r.congestion_level = $level
            RETURN a.name AS from_name, b.name AS to_name,
                   r.name AS road_name, r.vehicle_count AS vehicles,
                   r.avg_speed AS speed, r.length AS length
            ORDER BY r.vehicle_count DESC
            LIMIT 10
        """, {'level': level})

    # ==================== 最短路径（绕行推荐） ====================

    def find_shortest_path(self, from_id, to_id):
        """Dijkstra 最短路径查询（避开拥堵路段）"""
        return self.run("""
            MATCH (start:Intersection {id: $from_id})
            MATCH (end:Intersection {id: $to_id})
            CALL gds.shortestPath.dijkstra.stream('road_graph', {
                sourceNode: start,
                targetNode: end,
                relationshipWeightProperty: 'length'
            })
            YIELD index, sourceNode, targetNode, totalCost, nodeIds, costs
            RETURN index, totalCost, nodeIds
        """, {'from_id': from_id, 'to_id': to_id})

    def find_avoid_congestion_path(self, from_id, to_id):
        """绕行推荐：加权最短路径（拥堵路段权重翻倍）"""
        return self.run("""
            MATCH (start:Intersection {id: $from_id})
            MATCH (end:Intersection {id: $to_id})
            MATCH path = (start)-[:CONNECTS*]->(end)
            WHERE all(r IN relationships(path) WHERE r.congestion_level <> 'heavy')
            WITH path,
                 reduce(cost = 0, r IN relationships(path) |
                    cost + CASE r.congestion_level
                        WHEN 'heavy' THEN r.length * 100
                        WHEN 'moderate' THEN r.length * 3
                        WHEN 'light' THEN r.length * 1.5
                        ELSE r.length
                    END
                 ) AS total_cost
            RETURN 
                [node IN nodes(path) | node.name] AS route,
                [rel IN relationships(path) | rel.name] AS roads,
                total_cost
            ORDER BY total_cost ASC
            LIMIT 3
        """, {'from_id': from_id, 'to_id': to_id})

    # ==================== 事故因果图谱 ====================

    def create_accident_node(self, accident_id, severity, description):
        """创建事故节点"""
        return self.run("""
            MERGE (a:Accident {id: $id})
            SET a.severity = $severity, a.description = $description,
                a.timestamp = datetime()
        """, {'id': accident_id, 'severity': severity, 'description': description})

    def link_accident_to_road(self, accident_id, road_id):
        """关联事故到路段（通过路段属性而非关系指向关系）"""
        return self.run("""
            MATCH (a:Accident {id: $accident_id})
            MATCH ()-[r:CONNECTS {id: $road_id}]->()
            SET r.has_accident = true,
                r.last_accident_id = $accident_id,
                r.last_accident_time = datetime()
            WITH a, r
            MERGE (a)-[:OCCURRED_ON_ROAD {road_id: $road_id}]->(a)
        """, {'accident_id': accident_id, 'road_id': road_id})

    def link_accident_to_factors(self, accident_id, weather, road_condition, vehicle_type):
        """关联事故因果因素（天气、路况、车辆类型）"""
        # 创建/合并因素节点
        self.run("MERGE (w:Weather {type: $weather})", {'weather': weather})
        self.run("MERGE (rc:RoadCondition {type: $condition})", {'condition': road_condition})
        self.run("MERGE (v:VehicleType {type: $vtype})", {'vtype': vehicle_type})
        # 关联
        return self.run("""
            MATCH (a:Accident {id: $id})
            MATCH (w:Weather {type: $weather})
            MATCH (rc:RoadCondition {type: $condition})
            MATCH (v:VehicleType {type: $vtype})
            MERGE (a)-[:DURING_WEATHER]->(w)
            MERGE (a)-[:ROAD_WAS]->(rc)
            MERGE (a)-[:INVOLVED_VEHICLE]->(v)
        """, {'id': accident_id, 'weather': weather,
              'condition': road_condition, 'vtype': vehicle_type})

    def analyze_accident_causes(self):
        """事故归因分析 — 找出高频事故因素组合（含严重程度）"""
        return self.run("""
            MATCH (a:Accident)-[:DURING_WEATHER]->(w:Weather)
            MATCH (a)-[:ROAD_WAS]->(rc:RoadCondition)
            MATCH (a)-[:INVOLVED_VEHICLE]->(v:VehicleType)
            RETURN w.type AS weather, rc.type AS road_condition,
                   v.type AS vehicle_type, a.severity AS severity,
                   count(DISTINCT a) AS accident_count
            ORDER BY accident_count DESC
            LIMIT 10
        """)

    def get_accident_chain(self, accident_id):
        """获取事故完整因果链，返回包含属性值的字典"""
        records = self.run("""
            MATCH (a:Accident {id: $id})
            OPTIONAL MATCH (a)-[:DURING_WEATHER]->(w)
            OPTIONAL MATCH (a)-[:ROAD_WAS]->(rc)
            OPTIONAL MATCH (a)-[:INVOLVED_VEHICLE]->(v)
            RETURN a.severity AS severity,
                   a.description AS description,
                   w.type AS weather,
                   rc.type AS road_condition,
                   v.type AS vehicle_type
        """, {'id': accident_id})
        
        if records and records[0]:
            r = records[0]
            return {
                'severity': r.get('severity'),
                'weather': r.get('weather'),
                'road_condition': r.get('road_condition'),
                'vehicle_type': r.get('vehicle_type'),
            }
        return None


neo4j_db = Neo4jDB()
