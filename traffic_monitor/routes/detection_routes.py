"""检测路由 — 图片上传检测 & 检测历史"""
import os
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from werkzeug.utils import secure_filename
from services.detection_service import DetectionService
from models.redis_models import redis_service
from config import Config

detection_bp = Blueprint('detection', __name__, url_prefix='/detection')


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


@detection_bp.route('/')
def detection_page():
    """检测页面"""
    # 获取预置摄像头列表
    from models.mongodb_models import mongo
    cameras = list(mongo.cameras.find())
    for c in cameras:
        c['_id'] = str(c['_id'])
    return render_template('detection.html', cameras=cameras)


@detection_bp.route('/upload', methods=['POST'])
def upload_and_detect():
    """上传图片并执行 YOLO 检测"""
    if 'image' not in request.files:
        flash('请选择图片文件', 'danger')
        return redirect(url_for('detection.detection_page'))

    file = request.files['image']
    if file.filename == '':
        flash('请选择图片文件', 'danger')
        return redirect(url_for('detection.detection_page'))

    if file and allowed_file(file.filename):
        # 保存上传文件
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        filename = secure_filename(f'{timestamp}_{file.filename}')
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(filepath)

        # 获取参数
        camera_id = request.form.get('camera_id', 'CAM_DEFAULT')
        road_id = request.form.get('road_id', 'R001')

        # 执行检测
        try:
            result = DetectionService.process_image(filepath, camera_id, road_id)
            flash(f'检测完成！共检测到 {result["total_vehicles"]} 辆车，'
                  f'拥堵等级: {result["congestion_level"]}', 'success')
            return redirect(url_for('detection.detection_result',
                                    detection_id=result['_id']))
        except Exception as e:
            flash(f'检测失败: {str(e)}', 'danger')
            return redirect(url_for('detection.detection_page'))
    else:
        flash('不支持的文件格式', 'danger')
        return redirect(url_for('detection.detection_page'))


@detection_bp.route('/api/detect', methods=['POST'])
def api_detect():
    """API: 上传图片并返回 JSON 检测结果"""
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': '请上传图片'}), 400

    file = request.files['image']
    if file and allowed_file(file.filename):
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        filename = secure_filename(f'{timestamp}_{file.filename}')
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(filepath)

        camera_id = request.form.get('camera_id', 'CAM_API')
        road_id = request.form.get('road_id', 'R001')

        result = DetectionService.process_image(filepath, camera_id, road_id)
        return jsonify({
            'success': True,
            'detection_id': result['_id'],
            'total_vehicles': result['total_vehicles'],
            'vehicle_counts': result['vehicle_counts'],
            'congestion_level': result['congestion_level'],
            'risk_level': result['risk_level'],
            'detections': result['detections'],
            'timestamp': result['timestamp'].isoformat() if result.get('timestamp') else '',
        })

    return jsonify({'success': False, 'error': '不支持的文件格式'}), 400


@detection_bp.route('/result/<detection_id>')
def detection_result(detection_id):
    """检测结果详情"""
    from models.mongodb_models import mongo
    from bson import ObjectId

    detection = mongo.detections.find_one({'_id': ObjectId(detection_id)})
    if not detection:
        flash('检测记录不存在', 'danger')
        return redirect(url_for('detection.detection_page'))

    detection['_id'] = str(detection['_id'])
    return render_template('detection_result.html', detection=detection)


@detection_bp.route('/history')
def detection_history():
    """检测历史"""
    camera_id = request.args.get('camera_id', '')
    road_id = request.args.get('road_id', '')
    page = request.args.get('page', 1, type=int)

    result = DetectionService.get_recent_detections(
        camera_id=camera_id or None,
        road_id=road_id or None,
        page=page
    )

    from models.mongodb_models import mongo
    cameras = list(mongo.cameras.find())
    for c in cameras:
        c['_id'] = str(c['_id'])

    return render_template('detection_history.html',
                           **result,
                           cameras=cameras,
                           current_camera=camera_id,
                           current_road=road_id)


@detection_bp.route('/simulate', methods=['POST'])
def simulate_traffic():
    """
    模拟交通数据（不依赖真实图片）
    用于演示 Redis 实时缓存 + 预警机制
    """
    import random
    road_id = request.form.get('road_id', 'R001')
    camera_id = request.form.get('camera_id', 'CAM_SIM')

    # 随机生成车流量
    total = random.randint(5, 60)
    counts = {
        'car': random.randint(total // 2, total),
        'bus': random.randint(0, max(1, total // 10)),
        'truck': random.randint(0, max(1, total // 15)),
        'motorcycle': random.randint(0, max(1, total // 20)),
    }
    # 修正总数
    counts['car'] = total - sum(v for k, v in counts.items() if k != 'car')

    # 判定拥堵
    if total >= 50:
        congestion = 'heavy'
    elif total >= 30:
        congestion = 'moderate'
    elif total >= 15:
        congestion = 'light'
    else:
        congestion = 'normal'

    # 存入 Redis 实时缓存
    import time
    snapshot = {
        'total_vehicles': total,
        'vehicle_counts': counts,
        'congestion_level': congestion,
        'risk_level': 'high' if congestion == 'heavy' else 'medium' if congestion == 'moderate' else 'low',
        'timestamp': datetime.utcnow().isoformat(),
        'simulated': True,
    }
    redis_service.snapshot_set(camera_id, snapshot)

    # 更新拥堵排行
    redis_service.congestion_rank_update(road_id, total)

    # 更新车流量计数
    for vtype, count in counts.items():
        redis_service.traffic_count_increment(road_id, vtype, count)

    # 高拥堵时推送预警
    if congestion in ('heavy', 'moderate'):
        if redis_service.alert_throttle_check(road_id, window_seconds=60):
            redis_service.alert_push('congestion', {
                'road_id': road_id,
                'camera_id': camera_id,
                'congestion_level': congestion,
                'vehicle_count': total,
                'message': f'[模拟] 路段 {road_id} 拥堵 ({congestion}): {total}辆车'
            })

    # 存入 MongoDB
    from models.mongodb_models import mongo
    mongo_doc = {
        'camera_id': camera_id,
        'road_id': road_id,
        'total_vehicles': total,
        'vehicle_counts': counts,
        'congestion_level': congestion,
        'risk_level': snapshot['risk_level'],
        'detections': [],
        'timestamp': datetime.utcnow(),
        'simulated': True,
    }
    mongo.detections.insert_one(mongo_doc)

    return jsonify({
        'success': True,
        'total_vehicles': total,
        'congestion_level': congestion,
        'snapshot': snapshot,
    })


@detection_bp.route('/upload-video', methods=['POST'])
def upload_video_and_detect():
    """上传视频文件并逐帧检测"""
    if 'video' not in request.files:
        flash('请选择视频文件', 'danger')
        return redirect(url_for('detection.detection_page'))

    file = request.files['video']
    if file.filename == '':
        flash('请选择视频文件', 'danger')
        return redirect(url_for('detection.detection_page'))

    if file and allowed_file(file.filename):
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        filename = secure_filename(f'{timestamp}_{file.filename}')
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(filepath)

        camera_id = request.form.get('camera_id', 'CAM_VIDEO')
        road_id = request.form.get('road_id', 'R001')
        sample_interval = int(request.form.get('sample_interval', 30))

        from utils.yolo_utils import process_video_file
        try:
            result = process_video_file(filepath, camera_id, road_id, sample_interval)
            if result is None:
                flash('视频处理失败，请检查文件格式', 'danger')
                return redirect(url_for('detection.detection_page'))

            # 将关键帧检测结果存入 MongoDB + Redis
            from models.mongodb_models import mongo
            for frame_data in result['sampled_frames']:
                mongo_doc = {
                    'camera_id': camera_id,
                    'road_id': road_id,
                    'total_vehicles': frame_data['total_vehicles'],
                    'vehicle_counts': frame_data['vehicle_counts'],
                    'congestion_level': frame_data['congestion_level'],
                    'risk_level': frame_data['risk_level'],
                    'video_frame': frame_data['frame'],
                    'detections': [],
                    'timestamp': datetime.utcnow(),
                    'video_source': filename,
                }
                mongo.detections.insert_one(mongo_doc)

                # 更新 Redis
                redis_service.snapshot_set(camera_id, {
                    'total_vehicles': frame_data['total_vehicles'],
                    'congestion_level': frame_data['congestion_level'],
                    'risk_level': frame_data['risk_level'],
                })
                redis_service.congestion_rank_update(road_id, frame_data['total_vehicles'])

                # 拥堵预警
                if frame_data['congestion_level'] in ('heavy', 'moderate'):
                    if redis_service.alert_throttle_check(road_id, window_seconds=60):
                        redis_service.alert_push('congestion', {
                            'road_id': road_id,
                            'camera_id': camera_id,
                            'congestion_level': frame_data['congestion_level'],
                            'vehicle_count': frame_data['total_vehicles'],
                            'message': f'[视频检测] 路段 {road_id} 拥堵: {frame_data["total_vehicles"]}辆车(帧{frame_data["frame"]})'
                        })

            flash(f'视频检测完成！总帧数 {result["total_frames"]}，'
                  f'采样 {len(result["sampled_frames"])} 帧，'
                  f'峰值车流量 {result["peak_vehicles"]} 辆', 'success')
            return render_template('video_result.html', result=result)
        except Exception as e:
            flash(f'视频处理失败: {str(e)}', 'danger')
            return redirect(url_for('detection.detection_page'))
    else:
        flash('不支持的视频格式（支持 mp4/avi/mov）', 'danger')
        return redirect(url_for('detection.detection_page'))


@detection_bp.route('/webcam')
def webcam_page():
    """摄像头实时检测页面"""
    from models.mongodb_models import mongo
    cameras = list(mongo.cameras.find())
    for c in cameras:
        c['_id'] = str(c['_id'])
    return render_template('webcam.html', cameras=cameras)


@detection_bp.route('/api/webcam-capture', methods=['POST'])
def api_webcam_capture():
    """API: 从本地摄像头捕获一帧并检测"""
    data = request.get_json() or {}
    camera_src = data.get('camera_src', 0)  # 0=默认摄像头, 或 RTSP URL

    from utils.yolo_utils import capture_webcam_frame
    result, error = capture_webcam_frame(camera_src)

    if error:
        return jsonify({'success': False, 'error': error}), 400

    road_id = data.get('road_id', 'R001')
    camera_id = data.get('camera_id', 'CAM_WEBCAM')

    from services.detection_service import DetectionService
    mongo_doc = DetectionService.process_video_frame(result, camera_id, road_id)

    return jsonify({
        'success': True,
        'detection_id': str(mongo_doc) if mongo_doc else '',
        'total_vehicles': result['total'],
        'vehicle_counts': result['counts'],
        'timestamp': result['timestamp'],
    })


@detection_bp.route('/api/hngs-camera-url')
def api_hngs_camera_url():
    """
    获取河南高速摄像头 M3U8 流地址
    调用河南高速云平台 API: /camera/playUrl
    返回的 M3U8 含时效性 token（约几小时有效）
    """
    import requests as req
    camera_num = request.args.get('cameraNum', '1324629868805103618')
    video_type = request.args.get('videoType', '2')

    try:
        resp = req.get(
            'https://weixin.hngscloud.com/camera/playUrl',
            params={
                'cameraNUm': camera_num,
                'videoType': video_type,
                'videoRate': '0',
            },
            headers={
                'Referer': 'https://weixin.hngscloud.com/',
                'User-Agent': 'Mozilla/5.0',
            },
            timeout=10
        )
        data = resp.json()
        if data.get('code') == 200:
            return jsonify({
                'success': True,
                'cameraNum': camera_num,
                'm3u8_url': data['data']['playUrl'],
            })
        return jsonify({'success': False, 'error': data.get('msg', 'API error')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@detection_bp.route('/api/hngs-camera-snapshot')
def api_hngs_camera_snapshot():
    """
    从 M3U8 流中截取一帧并执行 YOLO 检测
    先用 ffmpeg 拉流截帧，再检测
    """
    import requests as req
    import subprocess
    import tempfile

    camera_num = request.args.get('cameraNum', '1324629868805103618')
    
    # 1. 获取 M3U8 地址
    try:
        resp = req.get(
            'https://weixin.hngscloud.com/camera/playUrl',
            params={'cameraNUm': camera_num, 'videoType': '2', 'videoRate': '0'},
            headers={'Referer': 'https://weixin.hngscloud.com/', 'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        data = resp.json()
        if data.get('code') != 200:
            return jsonify({'success': False, 'error': '获取流地址失败'}), 500
        m3u8_url = data['data']['playUrl']
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    # 2. 用 ffmpeg 截取一帧
    import os, shutil, glob
    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        # 尝试常见安装路径 + 自动扫描
        candidates = [
            os.path.expandvars(r'%ProgramFiles%\ffmpeg\bin\ffmpeg.exe'),
            os.path.expandvars(r'%USERPROFILE%\ffmpeg\bin\ffmpeg.exe'),
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'D:\ffmpeg\bin\ffmpeg.exe',
        ]
        # 扫描 D:\University 下所有 ffmpeg 目录
        for root in ['D:\\University', 'C:\\', 'D:\\']:
            try:
                candidates.extend(glob.glob(os.path.join(root, 'ffmpeg*', '**', 'ffmpeg.exe'), recursive=True))
            except Exception:
                pass
        for c in candidates:
            if os.path.isfile(c):
                ffmpeg_path = c
                break
    if not ffmpeg_path:
        ffmpeg_path = 'ffmpeg'
    output_path = os.path.join(Config.UPLOAD_FOLDER, f'hngs_{camera_num}_{datetime.utcnow().strftime("%H%M%S")}.jpg')
    try:
        subprocess.run([
            ffmpeg_path, '-y', '-i', m3u8_url,
            '-vframes', '1', '-f', 'image2',
            '-timeout', '5000000',  # 5秒超时（微秒）
            output_path
        ], capture_output=True, timeout=15)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # ffmpeg 不可用时回退：用 requests 下载 M3U8 第一帧
        return jsonify({
            'success': False, 
            'error': 'ffmpeg 不可用。请安装 ffmpeg 后重试，或手动将 M3U8 地址粘贴到摄像头页面播放后捕获检测。',
            'm3u8_url': m3u8_url,
        }), 500

    # 3. YOLO 检测
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        from services.detection_service import DetectionService
        road_id = request.args.get('road_id', 'R001')
        camera_id = f'HNGS_{camera_num}'
        result = DetectionService.process_image(output_path, camera_id, road_id)
        return jsonify({
            'success': True,
            'cameraNum': camera_num,
            'm3u8_url': m3u8_url,
            'total_vehicles': result['total_vehicles'],
            'vehicle_counts': result['vehicle_counts'],
            'congestion_level': result['congestion_level'],
            'risk_level': result['risk_level'],
            'detection_id': result['_id'],
            'snapshot': f'/static/uploads/{os.path.basename(output_path)}',
        })
    else:
        return jsonify({'success': False, 'error': '截帧失败，流可能已过期', 'm3u8_url': m3u8_url}), 500


@detection_bp.route('/api/hngs-camera-list')
def api_hngs_camera_list():
    """
    获取河南高速摄像头列表
    支持 exclude 参数（逗号分隔的已添加 ID），避免重复
    返回 count 个未添加的摄像头
    """
    import requests as req
    exclude_str = request.args.get('exclude', '')
    exclude_ids = set(exclude_str.split(',')) if exclude_str else set()
    count = int(request.args.get('count', 8))

    try:
        resp = req.get(
            'https://weixin.hngscloud.com/camera/search',
            params={
                'zoomLevel': '8', 'sbMapLevel': '8',
                'northEast': '116.5,36.5', 'southWest': '110.5,31.0',
            },
            headers={'Referer': 'https://weixin.hngscloud.com/', 'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        data = resp.json()
        all_cams = data.get('data', [])
        
        # 过滤掉已添加的
        available = [c for c in all_cams if c['cameraNum'] not in exclude_ids]
        
        # 随机选取 count 个
        import random
        selected = random.sample(available, min(count, len(available)))
        
        result = [{
            'cameraNum': c['cameraNum'],
            'cameraName': c.get('cameraName', ''),
            'road': c.get('road', ''),
            'pileNum': c.get('pileNum', ''),
            'regionName': c.get('regionName', ''),
            'latitude': float(c.get('latitude', 0)),
            'longitude': float(c.get('longitude', 0)),
            'online': c.get('online', 1),
        } for c in selected]
        
        return jsonify({
            'success': True,
            'cameras': result,
            'total_available': len(available),
            'total_all': len(all_cams),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
