# 🚗 智能交通监测与事故预警系统

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0+-black?logo=flask)
![YOLOv8](https://img.shields.io/badge/YOLO-v8-00FFFF?logo=yolo)
![MongoDB](https://img.shields.io/badge/MongoDB-4.0+-green?logo=mongodb)
![Redis](https://img.shields.io/badge/Redis-6.0+-red?logo=redis)
![Neo4j](https://img.shields.io/badge/Neo4j-4.4+-blue?logo=neo4j)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-purple?logo=bootstrap)

**基于 YOLOv8 + MongoDB + Redis + Neo4j 的非关系型数据库综合实践项目**

</div>

---

## 📋 项目简介

本项目构建了一套完整的智能交通监测 Web 平台，利用 **YOLOv8** 深度学习模型实现车辆目标检测，并协同 **三种 NoSQL 数据库** 各司其职：

- **MongoDB**（文档数据库）— 持久化存储检测记录、事故报告、道路与摄像头元数据，利用聚合管道进行多维统计分析
- **Redis**（内存数据库）— 实时车流量计数、预警消息队列、拥堵排行榜、分布式锁限流、会话管理
- **Neo4j**（图数据库）— 道路网络拓扑建模、事故因果图谱构建、Cypher 图查询实现归因分析与绕行推荐

系统支持图片上传检测、视频流实时处理、摄像头抓拍、模拟数据演示等多种运行模式，覆盖检测→分析→预警→事故→统计→归因的完整业务闭环。

---

## 🛠️ 技术栈

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **AI 模型** | Ultralytics YOLOv8 | latest | 车辆目标检测（6 类 COCO 车型） |
| **图像处理** | OpenCV / Pillow / NumPy | 4.x+ | 视频帧采样、图片预处理 |
| **Web 框架** | Flask + Jinja2 | 3.0+ | 后端路由、模板渲染、蓝图模块化 |
| **前端** | Bootstrap 5 + Bootstrap Icons | 5.3 / 1.11 | 响应式 UI、图标库 |
| **文档数据库** | MongoDB + PyMongo | 4.0+ / 4.6 | 检测记录、事故报告、聚合统计 |
| **内存数据库** | Redis + redis-py | 6.0+ / 5.0 | 实时缓存、消息队列、排行榜 |
| **图数据库** | Neo4j + neo4j-driver | 4.4+ / 5.20 | 路网拓扑、因果图谱、路径规划 |
| **会话管理** | Flask-Session | 0.8 | Redis 后端分布式会话 |
| **地图服务** | 高德地图 JS API / Web Service | v2.0 | 前端地图展示、路线规划 API |
| **部署** | Gunicorn | 22.0 | 生产级 WSGI 服务器 |

---

## 🎯 功能特性

### 🚘 车辆检测
- 图片上传检测（YOLOv8 实时推理，含置信度阈值调节）
- 视频文件处理（帧采样 + 批量检测 + 统计分析）
- 摄像头实时检测（WebRTC / M3U8 HLS 直播流 + ffmpeg 抓拍降级）
- 模拟数据模式（无需 GPU，直接生成随机流量数据演示完整链路）

### 📊 实时监测
- Redis Hash 毫秒级车流量计数（HINCRBY 原子操作）
- Redis Sorted Set 路段拥堵实时排行（ZADD / ZREVRANGE）
- 交通快照缓存（60s TTL，支撑 Dashboard 高频刷新）
- 多级拥堵判定（畅通 / 轻度 / 中度 / 严重） + 风险等级评估

### 🔔 预警系统
- Redis List 实现生产者-消费者预警消息队列
- SETEX 滑动窗口限流（同一路段 60s 内不重复告警）
- SET NX 分布式锁防止并发重复处理
- 严重拥堵 / 中度拥堵 / 事故三类预警自动触发

### 🚨 事故管理
- 事故上报（路段、严重程度、天气、路况、车型、地理坐标、描述）
- 事故 CRUD（列表/详情/编辑/删除）+ 状态流转（已上报→处理中→已解决）
- Neo4j 因果图谱构建（事故←天气/路况/车型 多因子关联）
- 事故归因分析（Cypher `count(DISTINCT)` 聚合高频因子组合 Top 10）
- 事故统计（MongoDB 聚合 + Neo4j 图查询双向交叉校验）

### 🗺️ 路网与导航
- Neo4j 道路网络拓扑建模（12 路口 + 26 路段双向图）
- 拥堵状态实时同步（Redis → Neo4j 路段属性更新）
- 拥堵绕行推荐（加权最短路径，严重拥堵路段权重 ×100）
- 高德地图 API 集成（地图可视化 + 驾车路线规划）

### 📈 数据统计
- 24 小时检测统计（MongoDB Aggregation Pipeline 按拥堵等级分组）
- 路网摘要（路口数 / 路段数 / 平均长度 / 总长度）
- 事故严重程度分布 + 天气维度分析
- Neo4j 归因分析 Top 10 展示

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      浏览器 (Bootstrap 5 UI)                      │
│   Dashboard │ 实时大屏 │ 车辆检测 │ 事故管理 │ 路网图 │ 统计     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP / WebSocket
┌───────────────────────────▼─────────────────────────────────────┐
│                     Flask 3.0 (Blueprint 模块化)                  │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ Main BP  │  │ Detection BP │  │ Accident BP  │               │
│  │ 首页/大屏 │  │ 检测/上传/视频│  │ 事故CRUD/归因 │               │
│  └────┬─────┘  └──────┬───────┘  └──────┬───────┘               │
│       │               │                │                         │
│  ┌────▼───────────────▼────────────────▼─────────────┐          │
│  │               Service Layer (业务逻辑层)            │          │
│  │  DetectionService │ AccidentService │ RoadNetwork  │          │
│  └────┬──────────────┬─────────────────┬─────────────┘          │
└───────┼──────────────┼─────────────────┼────────────────────────┘
        │              │                 │
  ┌─────▼─────┐  ┌─────▼─────┐  ┌───────▼──────┐
  │  MongoDB  │  │   Redis   │  │    Neo4j     │
  │  文档存储  │  │  实时缓存  │  │   图数据库   │
  ├───────────┤  ├───────────┤  ├──────────────┤
  │ 检测记录   │  │ 车流量计数  │  │ 路网拓扑     │
  │ 事故报告   │  │ 消息队列   │  │ 事故因果图   │
  │ 摄像头元数据│  │ 拥堵排行   │  │ 路径规划     │
  │ 聚合统计   │  │ 分布式锁   │  │ 归因分析     │
  │ Geo索引   │  │ 限流/Session│  │              │
  └───────────┘  └───────────┘  └──────────────┘
        │              │                 │
        └──────────────┴─────────────────┘
               YOLOv8 模型 (yolov8n.pt / yolov8s.pt)
```

---

## 📁 项目结构

```
traffic_monitor/
├── app.py                      # Flask 应用入口（蓝图注册、过滤器、错误处理）
├── config.py                   # 集中配置（数据库/模型/阈值/TTL/分页）
├── requirements.txt            # Python 依赖清单
├── start.bat                   # Windows 一键启动脚本
│
├── models/                     # 数据模型层
│   ├── mongodb_models.py       # MongoDB 连接管理 + 6 个集合定义 + 索引
│   ├── redis_models.py         # Redis 服务（8 种数据结构应用场景）
│   └── neo4j_models.py         # Neo4j 图管理（路网 / 事故因果 / 约束）
│
├── services/                   # 业务逻辑层
│   ├── detection_service.py    # 检测流程编排（YOLO → MongoDB → Redis → Neo4j）
│   ├── accident_service.py     # 事故管理 + 归因分析 + 统计缓存
│   └── road_network_service.py # 路网初始化 + 拥堵查询 + 绕行推荐
│
├── routes/                     # 路由控制层（Blueprint）
│   ├── main_routes.py          # / 首页 /dashboard /stats /monitor-wall
│   ├── detection_routes.py     # /detection 检测上传/历史/视频/摄像头
│   └── accident_routes.py      # /accident 事故CRUD/统计/归因/预测
│
├── utils/                      # 工具模块
│   ├── yolo_utils.py           # YOLOv8 封装（加载/检测/车流分析）
│   └── helpers.py              # 通用辅助函数
│
├── templates/                  # Jinja2 模板（19 页面 + 3 局部）
│   ├── base.html               # 基础布局（导航栏/页脚）
│   ├── index.html              # 系统首页概览
│   ├── dashboard.html          # 实时监控大屏
│   ├── detection*.html         # 检测页/结果/历史
│   ├── accident*.html          # 事故列表/详情/编辑/上报/统计
│   ├── road_network.html       # 路网地图
│   ├── stats.html              # 数据统计分析
│   ├── monitor_wall.html       # 多路监控墙
│   ├── alerts.html             # 预警消息列表
│   ├── webcam.html             # 摄像头实时检测
│   ├── video_result.html       # 视频检测结果
│   ├── 404.html / 500.html     # 错误页面
│   └── partials/               # 局部模板（快照表/排行/预警列表）
│
└── static/                     # 静态资源
    ├── css/style.css            # 自定义样式
    ├── js/main.js               # 前端交互逻辑
    └── uploads/                 # 用户上传图片目录
```

---

## 🚀 快速开始

### 前置环境

| 组件 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.8+ | 推荐 3.10+ |
| MongoDB | 4.0+ | 本地安装或 Docker |
| Redis | 6.0+ | 本地安装或 Docker（Windows 可用 Memurai） |
| Neo4j | 4.4+ | 可选，不影响核心检测功能 |
| YOLO 模型 | — | 需自行下载（见下方注意事项） |

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/hanshan650/traffic-monitor.git
cd traffic-monitor

# 2. 创建虚拟环境（推荐）
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 3. 安装 Python 依赖
pip install -r requirements.txt

# 4. 下载 YOLO 模型文件（⚠️ 必须）
# 下载 yolov8n.pt（约 6MB，快速推理）或 yolov8s.pt（约 22MB，更高精度）
# 放到 traffic_monitor/ 根目录
# 下载地址：https://github.com/ultralytics/assets/releases
```

### 启动数据库服务

```bash
# MongoDB
mongod --dbpath=data

# Redis
redis-server

# Neo4j（可选）
neo4j start
# 默认用户名 neo4j，首次启动会要求修改密码
```

### 运行应用

```bash
# 开发模式
python app.py
# 或双击 start.bat（Windows）

# 浏览器访问
http://127.0.0.1:5000
```

---

## ⚠️ 注意事项

### 1. YOLO 模型文件
> 由于 GitHub 文件大小限制，仓库中**不包含** YOLO 权重文件（`yolov8n.pt` / `yolov8s.pt`）。
>
> 首次运行前需手动下载并放到 `traffic_monitor/` 目录下：
> - `yolov8n.pt`（约 6MB，快速）— [下载链接](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt)
> - `yolov8s.pt`（约 22MB，高精度）— [下载链接](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt)
>
> 若不想下载模型，可使用「模拟交通数据」功能体验完整系统链路。

### 2. 数据库连接配置
默认连接本地数据库，可在 `config.py` 中修改：

```python
# MongoDB（默认无密码）
MONGO_URI = 'mongodb://localhost:27017'

# Redis（默认无密码）
REDIS_HOST = 'localhost'
REDIS_PORT = 6379

# Neo4j（默认密码 12345678，请修改）
NEO4J_URI = 'bolt://localhost:7687'
NEO4J_PASSWORD = '12345678'
```

### 3. Neo4j 可选性
> Neo4j 连接失败不影响核心功能（检测、缓存、预警）。仅路网图、事故因果图谱、归因分析等功能不可用。系统启动时会自动检测并降级。

### 4. Windows 下的 Redis
- 官方不支持 Windows，推荐使用 [Memurai](https://www.memurai.com/)（兼容 Redis 协议）
- 或通过 WSL2 / Docker 运行

### 5. 高德地图 API Key
`config.py` 中的 Key 为测试 Key，有日调用量限制。生产环境请在 [高德开放平台](https://console.amap.com/) 申请自己的 Key。

### 6. Python 路径问题
启动脚本 `start.bat` 会自动检测 Python 路径，若失败请手动修改或直接运行 `python app.py`。

---

## 📊 数据库设计要点

### MongoDB 文档模型
```
detections: {
  camera_id, road_id, image_path,
  total_vehicles, vehicle_counts: {car, bus, truck, ...},
  congestion_level, risk_level,
  detections: [{class_id, class_name, confidence, bbox}],  // 嵌套检测框
  timestamp (TTL 索引 30 天自动过期)
}
accidents: {
  road_id, severity, weather, road_condition,
  vehicle_types: [car, truck, ...],
  location: {type: "Point", coordinates: [lng, lat]},  // GeoJSON
  status: "reported|processing|resolved"
}
```

### Redis 数据结构
| Key Pattern | 类型 | TTL | 用途 |
|-------------|------|-----|------|
| `traffic:snapshot:{cam}` | String(JSON) | 60s | 检测快照 |
| `traffic:road:{id}:vehicles` | Hash | 10s | 路段车流量 |
| `traffic:congestion_rank` | Sorted Set | — | 拥堵排行 |
| `traffic:mq:traffic_alert` | List | — | 预警队列 |
| `traffic:alert_throttle:{road}` | String | 60s | 告警限流 |
| `traffic:accident_stats` | String(JSON) | 300s | 事故统计缓存 |

### Neo4j 图模型
```
(:Intersection)-[:CONNECTS {id, length, speed_limit, congestion_level}]→(:Intersection)
(:Accident)-[:DURING_WEATHER]→(:Weather)
(:Accident)-[:ROAD_WAS]→(:RoadCondition)
(:Accident)-[:INVOLVED_VEHICLE]→(:VehicleType)
```

---

## 📝 关键算法

| 算法 / 技术 | 实现位置 | 说明 |
|------------|---------|------|
| YOLOv8 目标检测 | `utils/yolo_utils.py` | COCO 预训练模型，识别 6 类车辆 |
| 拥堵等级判定 | `config.py` | 三档阈值（15/30/50 辆） |
| MongoDB 聚合管道 | `services/detection_service.py` | 24h 检测统计 / 事故多维分析 |
| Cypher 归因分析 | `models/neo4j_models.py` | `count(DISTINCT)` 去重聚合因子组合 |
| 拥堵绕行推荐 | `models/neo4j_models.py` | 加权最短路径（拥堵段权重 ×100） |
| 预警限流算法 | `models/redis_models.py` | SETEX 滑动窗口（60s） |
| 事故统计缓存 | `services/accident_service.py` | Cache-Aside 模式（主动失效 + TTL） |

---

## 🎓 数据库选型对照

| 功能模块 | 数据库 | 选型理由 |
|---------|--------|---------|
| 检测记录存储 | **MongoDB** | 检测框坐标数量不固定，文档嵌套天然适配；GeoSpatial 索引支持地图查询 |
| 事故报告 | **MongoDB** | 车辆类型数组、地理坐标、灵活字段扩展 |
| 实时车流量 | **Redis Hash** | HINCRBY 原子计数，毫秒级响应，TTL 自动回收 |
| 预警消息队列 | **Redis List** | LPUSH/BRPOP 零配置消息队列，轻量无需 RabbitMQ |
| 拥堵排行榜 | **Redis Sorted Set** | 权重即车流量，ZREVRANGE 实时 Top N |
| 告警限流 | **Redis String** | SETEX 原子操作实现滑动窗口限流 |
| 分布式锁 | **Redis String** | SET NX EX 防并发重复处理 |
| 会话管理 | **Redis** | Flask-Session 后端，支持分布式部署 |
| 路网拓扑 | **Neo4j** | 道路天然图结构，Cypher 遍历效率远超 SQL 递归 CTE |
| 事故归因 | **Neo4j** | 天气/路况/车型多因子关联，图遍历天然支持归因分析 |
| 绕行推荐 | **Neo4j** | 加权最短路径查询，拥堵权重动态调整 |

---

## 📄 License

MIT License — 仅供学习与展示使用。
后续会继续优化与更新

---

<div align="center">

**非关系型数据库综合实践项目 © 2026**

</div>
