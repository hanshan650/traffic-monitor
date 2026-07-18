"""
事故服务 — 管理交通事故记录、关联 Neo4j 因果图谱
"""
from datetime import datetime
from bson import ObjectId
from models.mongodb_models import mongo
from models.neo4j_models import neo4j_db
from models.redis_models import redis_service


class AccidentService:

    @staticmethod
    def create_accident(road_id, severity, description, weather,
                        road_condition, vehicle_types, lat=None, lng=None,
                        image_path=None):
        """
        创建事故记录
        1. 存入 MongoDB（灵活文档）
        2. 在 Neo4j 中建立因果图谱
        3. 推送 Redis 预警
        """
        accident_doc = {
            'road_id': road_id,
            'severity': severity,      # minor, moderate, severe, fatal
            'description': description,
            'weather': weather,        # sunny, rain, snow, fog
            'road_condition': road_condition,  # dry, wet, icy, damaged
            'vehicle_types': vehicle_types,    # ['car', 'truck']
            'status': 'reported',
            'image_path': image_path,
            'timestamp': datetime.utcnow(),
        }
        if lat and lng:
            accident_doc['location'] = {
                'type': 'Point',
                'coordinates': [float(lng), float(lat)]
            }

        result = mongo.accidents.insert_one(accident_doc)
        accident_id = str(result.inserted_id)
        accident_doc['_id'] = accident_id

        # Neo4j 因果图谱构建
        try:
            neo4j_db.create_accident_node(accident_id, severity, description)
            neo4j_db.link_accident_to_road(accident_id, road_id)
            for vt in vehicle_types:
                neo4j_db.link_accident_to_factors(
                    accident_id, weather, road_condition, vt
                )
        except Exception as e:
            print(f"Neo4j 事故图谱构建失败: {e}")

        # Redis 事故预警推送
        redis_service.alert_push('accident', {
            'accident_id': accident_id,
            'road_id': road_id,
            'severity': severity,
            'weather': weather,
            'message': f'路段 {road_id} 发生事故！严重程度: {severity}',
            'timestamp': datetime.utcnow().isoformat()
        })

        # 清除事故统计缓存
        redis_service.accident_stats_cache({}, ttl=1)  # 标记失效

        return accident_doc

    @staticmethod
    def get_recent_accidents(page=1, per_page=10):
        """获取最近事故列表"""
        filter_cond = {}
        total = mongo.accidents.count_documents(filter_cond)
        docs = list(
            mongo.accidents.find(filter_cond)
            .sort([('timestamp', -1)])
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        for d in docs:
            d['_id'] = str(d['_id'])
        return {
            'accidents': docs,
            'total': total,
            'page': page,
            'total_pages': (total + per_page - 1) // per_page
        }

    @staticmethod
    def get_accident_stats():
        """获取事故统计（优先 Redis 缓存）"""
        cached = redis_service.accident_stats_get()
        if cached:
            return cached

        # MongoDB 聚合统计
        pipeline = [
            {'$group': {
                '_id': None,
                'total': {'$sum': 1},
                'by_severity': {'$push': '$severity'},
                'by_weather': {'$push': '$weather'},
            }}
        ]
        result = list(mongo.accidents.aggregate(pipeline))

        # Neo4j 因果分析（含严重程度维度，使用 count(DISTINCT a) 避免多车型重复计数）
        try:
            cause_analysis = neo4j_db.analyze_accident_causes()
            # 从 Neo4j 归因结果中聚合严重程度分布
            neo4j_severity = {}
            for r in cause_analysis:
                sev = r.get('severity', 'unknown')
                neo4j_severity[sev] = neo4j_severity.get(sev, 0) + r.get('accident_count', 0)
        except:
            cause_analysis = []
            neo4j_severity = {}

        # MongoDB 严重程度分布
        mongo_severity = AccidentService._count_by_field('severity')

        stats = {
            'total': mongo.accidents.count_documents({}),
            'by_severity': mongo_severity,
            'by_weather': AccidentService._count_by_field('weather'),
            'neo4j_severity': neo4j_severity,  # Neo4j 侧严重程度，用于交叉校验
            'cause_analysis': [
                {
                    'weather': r.get('weather', ''),
                    'road_condition': r.get('road_condition', ''),
                    'vehicle_type': r.get('vehicle_type', ''),
                    'severity': r.get('severity', ''),
                    'count': r.get('accident_count', 0)
                }
                for r in cause_analysis
            ] if cause_analysis else [],
        }
        redis_service.accident_stats_cache(stats)
        return stats

    @staticmethod
    def _count_by_field(field):
        """按字段聚合计数"""
        pipeline = [
            {'$group': {'_id': f'${field}', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        result = list(mongo.accidents.aggregate(pipeline))
        return {r['_id'] or 'unknown': r['count'] for r in result}

    @staticmethod
    def get_accident_detail(accident_id):
        """获取事故详情（含 Neo4j 因果链）"""
        accident = mongo.accidents.find_one({'_id': ObjectId(accident_id)})
        if accident:
            accident['_id'] = str(accident['_id'])

        # Neo4j 因果链 — 返回包含属性值的字典
        causal_chain = None
        try:
            causal_chain = neo4j_db.get_accident_chain(accident_id)
        except:
            pass

        return {
            'accident': accident,
            'causal_chain': causal_chain
        }

    @staticmethod
    def update_accident(accident_id, updates):
        """更新事故信息，并同步 Neo4j"""
        try:
            oid = ObjectId(accident_id)
        except:
            return False, '无效的 ID'

        existing = mongo.accidents.find_one({'_id': oid})
        if not existing:
            return False, '事故不存在'

        allowed = ['road_id', 'severity', 'description', 'weather',
                   'road_condition', 'vehicle_types', 'status']
        set_fields = {k: updates[k] for k in allowed if k in updates}
        if not set_fields:
            return False, '无更新内容'

        set_fields['updated_at'] = datetime.utcnow()
        mongo.accidents.update_one({'_id': oid}, {'$set': set_fields})

        # 同步 Neo4j 因果图谱
        try:
            neo4j_db.create_accident_node(
                accident_id, set_fields.get('severity', existing.get('severity')),
                set_fields.get('description', existing.get('description', ''))
            )
            if 'road_id' in set_fields:
                neo4j_db.link_accident_to_road(accident_id, set_fields['road_id'])
            if any(k in set_fields for k in ['weather', 'road_condition', 'vehicle_types']):
                weather = set_fields.get('weather', existing.get('weather', 'sunny'))
                road_cond = set_fields.get('road_condition', existing.get('road_condition', 'dry'))
                vtypes = set_fields.get('vehicle_types', existing.get('vehicle_types', ['car']))
                for vt in vtypes:
                    neo4j_db.link_accident_to_factors(accident_id, weather, road_cond, vt)
        except:
            pass

        return True, '更新成功'

    @staticmethod
    def delete_accident(accident_id):
        """删除事故（MongoDB + Neo4j）"""
        try:
            oid = ObjectId(accident_id)
        except:
            return False, '无效的 ID'

        result = mongo.accidents.delete_one({'_id': oid})
        if result.deleted_count == 0:
            return False, '事故不存在'

        # 删除 Neo4j 对应节点
        try:
            neo4j_db.run("MATCH (a:Accident {id: $id}) DETACH DELETE a",
                         {'id': accident_id})
        except:
            pass

        # 清除缓存
        redis_service.accident_stats_cache({}, ttl=1)
        return True, '已删除'
