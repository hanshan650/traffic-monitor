# 🚗 智能交通监测与事故预警系统

> 基于 YOLOv8 + MongoDB + Redis + Neo4j 的非关系型数据库综合实践项目

## 📋 项目简介

利用 **YOLOv8** 目标检测模型对交通监控画面进行实时车辆检测，结合三种非关系型数据库实现完整的智能交通监测系统：

| 数据库 | 核心用途 | 数据结构 |
|--------|---------|---------|
| **MongoDB** | 检测记录存储、事故报告、用户数据 | 文档模型（灵活嵌套） |
| **Redis** | 实时车流量缓存、预警消息队列、拥堵排行榜、Session | KV/Hash/List/SortedSet |
| **Neo4j** | 道路网络拓扑图、事故因果图谱、绕行推荐 | 图模型（节点+关系） |

## 🎯 数据库选型对照表

| 功能模块 | 数据库 | 选型理由 | 替代方案 |
|---------|--------|---------|---------|
| 检测记录存储 | **MongoDB** | 不同路段检测结果字段差异大（嵌套检测框坐标、车型统计），文档模型无需固定 Schema | MySQL 需复杂表结构，JSON 列性能差 |
| 事故报告 | **MongoDB** | 事故信息灵活多变（车辆类型数组、图片附件、地理坐标），支持 GeoSpatial 索引按位置查询 | MySQL 地理查询功能弱 |
| 实时车流量 | **Redis Hash** | 毫秒级读写，HINCRBY 原子计数，TTL 自动过期释放内存 | MongoDB 写入性能无法满足高并发实时计数 |
| 预警消息队列 | **Redis List** | LPUSH/BRPOP 实现生产者-消费者，支持阻塞读取，轻量级无需额外中间件 | RabbitMQ/Kafka 部署运维复杂 |
| 拥堵排行榜 | **Redis Sorted Set** | ZADD 实时更新分数，ZREVRANGE 毫秒级 Top N 查询 | MySQL ORDER BY 全表扫描 |
| 路网拓扑 | **Neo4j** | 道路网络是天然图结构，Cypher 查询最短路径/绕行推荐效率远超 SQL 递归查询 | MySQL 递归 CTE 性能极差 |
| 事故因果图谱 | **Neo4j** | 事故←天气/路况/车辆多因素关联，图遍历实现归因分析 | MySQL 多表 JOIN 难以表达复杂因果 |

## 📊 Redis 应用全景

| 应用场景 | Redis 数据结构 | 具体实现 |
|---------|--------------|---------|
| 实时车流量缓存 | Hash (HINCRBY) | 每检测到一辆车就原子+1，5秒 TTL |
| 预警消息队列 | List (LPUSH/BRPOP) | 拥堵推送、事故通知，保留最近1000条 |
| 拥堵排行榜 | Sorted Set (ZADD/ZREVRANGE) | 按车流量实时排名 |
| 预警限流 | String (SETEX) | 同一路段60秒内不重复告警 |
| 分布式锁 | String (SET NX EX) | 防止并发处理同一帧 |
| Session 管理 | String (Flask-Session) | 分布式会话共享 |

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────┐
│                   Flask Web 前端                       │
│              Bootstrap 5 + Jinja2 模板                │
├──────────┬──────────────┬──────────────┬─────────────┤
│ YOLOv8   │   MongoDB    │    Redis     │    Neo4j    │
│ 车辆检测  │  检测记录     │  实时缓存     │  路网拓扑   │
│ (Python) │  事故报告     │  消息队列     │  因果图谱   │
│          │  用户数据     │  排行榜       │  绕行推荐   │
└──────────┴──────────────┴──────────────┴─────────────┘
```

## 🚀 快速开始

### 环境要求
- Python 3.8+
- MongoDB 4.0+
- Redis 6.0+
- Neo4j 4.4+（可选，不影响核心功能）

### 安装运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 确保服务已启动
mongod --dbpath=data    # MongoDB
redis-server            # Redis
neo4j start             # Neo4j (可选)

# 3. 启动应用
python app.py

# 4. 浏览器访问
http://127.0.0.1:5000
```

### 首次运行

1. 点击「模拟交通数据」生成演示数据（无需 YOLO 模型）
2. 或点击「上传图片检测」使用 YOLOv8 真实检测
3. 查看实时大屏观察 Redis 缓存更新
4. 上报事故查看 Neo4j 因果图谱

## 📁 项目结构

```
traffic_monitor/
├── app.py                     # Flask 主应用入口
├── config.py                  # 集中配置管理
├── requirements.txt
├── models/
│   ├── mongodb_models.py      # MongoDB 数据模型 + 索引
│   ├── neo4j_models.py        # Neo4j 图谱模型 + Cypher 查询
│   └── redis_models.py        # Redis 服务（8种应用场景）
├── services/
│   ├── detection_service.py   # YOLO检测 + MongoDB存储 + Redis更新
│   ├── accident_service.py    # 事故管理 + Neo4j因果链
│   └── road_network_service.py # 路网管理 + 绕行推荐
├── routes/
│   ├── main_routes.py         # 首页/大屏/统计
│   ├── detection_routes.py    # 检测/上传/模拟
│   └── accident_routes.py     # 事故/预警/预测
├── utils/
│   └── yolo_utils.py          # YOLOv8 封装工具
├── templates/                 # 15个 HTML 模板
├── static/                    # CSS/JS/上传文件
└── data/                      # 示例数据
```

## 📝 Neo4j Cypher 查询示例

```cypher
// 事故归因分析
MATCH (a:Accident)-[:DURING_WEATHER]->(w)
MATCH (a)-[:ROAD_WAS]->(rc)
MATCH (a)-[:INVOLVED_VEHICLE]->(v)
RETURN w.type, rc.type, v.type, count(a) AS cnt
ORDER BY cnt DESC

// 绕行推荐（避开严重拥堵）
MATCH path = (s:Intersection{id:'I001'})-[:CONNECTS*]->(e:Intersection{id:'I006'})
WHERE ALL(r IN relationships(path) WHERE r.congestion_level <> 'heavy')
RETURN [n IN nodes(path) | n.name] AS route
ORDER BY reduce(c=0, r IN relationships(path) | c+r.length) ASC
```

## 🎓 答辩要点

1. **数据库选型有理有据**：每个 NoSQL 都有明确的应用场景
2. **Redis 8种应用**：缓存/队列/排行/锁/限流/计数/Session/PubSub
3. **Neo4j 天然场景**：路网就是图，不是硬凑
4. **MongoDB 文档优势**：检测结果的灵活字段 + 嵌套检测框
5. **YOLOv8 真实 AI**：非玩具级 Demo，可实际运行

---

> 非关系型数据库综合实践项目 © 2026
