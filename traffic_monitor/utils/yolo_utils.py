"""
YOLO 检测工具 — 封装 YOLOv8 模型加载与推理
支持图片和视频的车辆检测，返回结构化检测结果
"""
import os
import cv2
import numpy as np
from ultralytics import YOLO
from datetime import datetime

# 全局模型实例（懒加载）
_model = None
_model_path = None

# 模型文件的绝对路径（优先使用项目根目录下的，避免从 GitHub 下载）
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_MODEL = os.path.join(_BASE_DIR, 'yolov8s.pt')
_FALLBACK_MODEL = os.path.join(_BASE_DIR, 'yolov8n.pt')

# COCO 车辆类别映射
VEHICLE_CLASSES = {
    2: {'name': 'car', 'name_cn': '小汽车', 'color': '#00FF00'},
    3: {'name': 'motorcycle', 'name_cn': '摩托车', 'color': '#FFA500'},
    5: {'name': 'bus', 'name_cn': '公交车', 'color': '#0000FF'},
    7: {'name': 'truck', 'name_cn': '卡车', 'color': '#FF0000'},
    1: {'name': 'bicycle', 'name_cn': '自行车', 'color': '#00FFFF'},
}


def get_model(model_path=None):
    """获取 YOLO 模型（单例懒加载），优先使用 yolov8s，回退 yolov8n"""
    global _model, _model_path
    if model_path is None:
        if os.path.exists(_DEFAULT_MODEL):
            model_path = _DEFAULT_MODEL
        elif os.path.exists(_FALLBACK_MODEL):
            model_path = _FALLBACK_MODEL
        else:
            model_path = _DEFAULT_MODEL  # 让它报错提示下载
    
    if _model is None or _model_path != model_path:
        print(f"  ⏳ 加载 YOLO 模型: {model_path}")
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"YOLO 模型文件不存在: {model_path}\n"
                f"请下载 yolov8s.pt 或 yolov8n.pt 到项目根目录"
            )
        _model = YOLO(model_path)
        _model_path = model_path
        print(f"  ✓ YOLO 模型加载完成")
    return _model


def detect_vehicles(image_path, confidence_threshold=0.3):
    """
    对单张图片执行车辆检测
    返回: {
        'detections': [...],
        'counts': {'car': 5, 'bus': 1, ...},
        'total': 6,
        'image_with_boxes': base64 or path,
        'timestamp': '...'
    }
    """
    model = get_model()
    results = model(image_path, conf=confidence_threshold)

    detections = []
    counts = {}
    total = 0

    for result in results:
        if result.boxes is None:
            continue
        for box in result.boxes:
            cls_id = int(box.cls[0])
            if cls_id not in VEHICLE_CLASSES:
                continue

            vehicle_info = VEHICLE_CLASSES[cls_id]
            conf = float(box.conf[0])
            xyxy = box.xyxy[0].tolist()

            detection = {
                'bbox': [round(x, 1) for x in xyxy],
                'confidence': round(conf, 3),
                'class_id': cls_id,
                'class_name': vehicle_info['name'],
                'class_name_cn': vehicle_info['name_cn'],
                'color': vehicle_info['color'],
                'center_x': round((xyxy[0] + xyxy[2]) / 2, 1),
                'center_y': round((xyxy[1] + xyxy[3]) / 2, 1),
                'width': round(xyxy[2] - xyxy[0], 1),
                'height': round(xyxy[3] - xyxy[1], 1),
            }
            detections.append(detection)

            vname = vehicle_info['name']
            counts[vname] = counts.get(vname, 0) + 1
            total += 1

    return {
        'detections': detections,
        'counts': counts,
        'total': total,
        'timestamp': datetime.utcnow().isoformat(),
    }


def detect_video_frame(frame, model=None, confidence_threshold=0.3):
    """
    对视频单帧执行检测（返回与 detect_vehicles 相同结构）
    """
    if model is None:
        model = get_model()
    
    results = model(frame, conf=confidence_threshold, verbose=False)
    
    detections = []
    counts = {}
    total = 0
    
    for result in results:
        if result.boxes is None:
            continue
        for box in result.boxes:
            cls_id = int(box.cls[0])
            if cls_id not in VEHICLE_CLASSES:
                continue
            
            vehicle_info = VEHICLE_CLASSES[cls_id]
            conf = float(box.conf[0])
            xyxy = box.xyxy[0].tolist()
            
            detections.append({
                'bbox': [round(x, 1) for x in xyxy],
                'confidence': round(conf, 3),
                'class_id': cls_id,
                'class_name': vehicle_info['name'],
                'class_name_cn': vehicle_info['name_cn'],
            })
            
            vname = vehicle_info['name']
            counts[vname] = counts.get(vname, 0) + 1
            total += 1
    
    return {
        'detections': detections,
        'counts': counts,
        'total': total,
        'timestamp': datetime.utcnow().isoformat(),
    }


def draw_boxes_on_image(image_path, detections, output_path):
    """在图片上绘制检测框"""
    img = cv2.imread(image_path)
    if img is None:
        return None
    
    for det in detections:
        bbox = det['bbox']
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        color_hex = det.get('color', '#00FF00')
        # 转换颜色
        r, g, b = int(color_hex[1:3], 16), int(color_hex[3:5], 16), int(color_hex[5:7], 16)
        cv2.rectangle(img, (x1, y1), (x2, y2), (b, g, r), 2)
        label = f"{det['class_name_cn']} {det['confidence']:.2f}"
        cv2.putText(img, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (b, g, r), 2)
    
    cv2.imwrite(output_path, img)
    return output_path


def analyze_traffic_flow(detection_result, road_id, camera_id):
    """
    分析交通流量并返回结构化数据
    用于存入 MongoDB 和更新 Redis
    """
    total = detection_result['total']
    counts = detection_result['counts']
    
    # 判定拥堵等级
    if total >= 50:
        congestion = 'heavy'
    elif total >= 30:
        congestion = 'moderate'
    elif total >= 15:
        congestion = 'light'
    else:
        congestion = 'normal'
    
    # 估算风险等级
    risk_level = 'low'
    if congestion == 'heavy':
        risk_level = 'high'
    elif congestion == 'moderate':
        risk_level = 'medium'
    
    return {
        'road_id': road_id,
        'camera_id': camera_id,
        'total_vehicles': total,
        'vehicle_counts': counts,
        'congestion_level': congestion,
        'risk_level': risk_level,
        'detections': detection_result['detections'],
        'timestamp': detection_result['timestamp'],
    }


def process_video_file(video_path, camera_id, road_id, sample_interval=30):
    """
    处理视频文件：每隔 sample_interval 帧采样检测一次
    返回所有采样帧的检测结果汇总
    """
    model = get_model()
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        return None
    
    results_summary = {
        'video_path': video_path,
        'camera_id': camera_id,
        'road_id': road_id,
        'total_frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        'fps': round(cap.get(cv2.CAP_PROP_FPS), 1),
        'sampled_frames': [],
        'peak_vehicles': 0,
        'peak_frame': 0,
        'avg_vehicles': 0,
        'congestion_duration': 0,  # 拥堵帧数
    }
    
    frame_idx = 0
    total_vehicles_sum = 0
    sampled_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_idx % sample_interval == 0:
            result = detect_video_frame(frame, model)
            analysis = analyze_traffic_flow(result, road_id, camera_id)
            
            results_summary['sampled_frames'].append({
                'frame': frame_idx,
                'total_vehicles': analysis['total_vehicles'],
                'vehicle_counts': analysis['vehicle_counts'],
                'congestion_level': analysis['congestion_level'],
                'risk_level': analysis['risk_level'],
                'detections_count': len(analysis['detections']),
                'timestamp': analysis['timestamp'],
            })
            
            total_vehicles_sum += analysis['total_vehicles']
            sampled_count += 1
            
            if analysis['total_vehicles'] > results_summary['peak_vehicles']:
                results_summary['peak_vehicles'] = analysis['total_vehicles']
                results_summary['peak_frame'] = frame_idx
            
            if analysis['congestion_level'] in ('heavy', 'moderate'):
                results_summary['congestion_duration'] += sample_interval
        
        frame_idx += 1
    
    cap.release()
    
    if sampled_count > 0:
        results_summary['avg_vehicles'] = round(total_vehicles_sum / sampled_count, 1)
    
    return results_summary


def capture_webcam_frame(camera_id=0):
    """
    从本地摄像头或 RTSP 流捕获一帧并检测
    camera_id 可以是数字(本地摄像头索引)或 RTSP URL 字符串
    """
    try:
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            return None, '无法打开摄像头'
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return None, '读取帧失败'
        
        result = detect_video_frame(frame)
        return result, None
    except Exception as e:
        return None, str(e)
