"""RESTful API 路由"""
from flask import Blueprint, request

from app.utils.decorators import login_required_api
from app.utils.response import api_error, from_service_result
from app.utils.api_helpers import (
    get_current_username,
    handle_service_call,
    handle_process_action
)
from app.services import supervisor_service

api_bp = Blueprint('api', __name__)


@api_bp.route('/current-user', methods=['GET'])
@login_required_api
def get_current_user():
    """获取当前运行用户（用于添加进程时自查询启动用户）"""
    try:
        import getpass
        import os
        user = getpass.getuser()
        uid = os.getuid() if hasattr(os, 'getuid') else None
        return from_service_result({
            'success': True,
            'message': 'ok',
            'data': {'user': user, 'uid': uid}
        })
    except Exception as e:
        return api_error(str(e), 500)


@api_bp.route('/status', methods=['GET'])
@login_required_api
def get_status():
    """获取所有进程状态"""
    result = supervisor_service.get_all_process_info()
    return from_service_result(result)


@api_bp.route('/process', methods=['POST'])
@login_required_api
def add_process():
    """添加守护进程"""
    data = request.get_json()
    if not data:
        return api_error('请求体不能为空', 400)

    return handle_service_call(
        lambda: supervisor_service.add_process(data),
        log_type='ADD_PROCESS',
        log_success_detail_fn=lambda r: f"添加进程: {r.get('data', {}).get('name', '')}",
        log_fail_detail_fn=lambda r: f"添加失败: {r.get('message', '')}",
        success_status=201,
        error_status=400
    )


@api_bp.route('/process/<path:name>', methods=['PUT'])
@login_required_api
def update_process(name):
    """更新守护进程配置"""
    data = request.get_json()
    if not data:
        return api_error('请求体不能为空', 400)
    return handle_service_call(
        lambda: supervisor_service.update_process(name, data),
        log_type='UPDATE_PROCESS',
        log_success_detail_fn=lambda r: f"更新进程: {r.get('data', {}).get('name', '')}",
        log_fail_detail_fn=lambda r: f"更新失败: {r.get('message', '')}",
        success_status=200,
        error_status=400
    )


@api_bp.route('/process/<path:name>', methods=['DELETE'])
@login_required_api
def delete_process(name):
    """删除守护进程"""
    return handle_process_action(
        supervisor_service.remove_process,
        name,
        'DELETE_PROCESS',
        success_detail=f'删除进程: {name}',
        log_on_fail=True,
        fail_detail_template='删除失败 {name}: {message}'
    )


@api_bp.route('/process/<path:name>/start', methods=['POST'])
@login_required_api
def start_process(name):
    """启动进程"""
    return handle_process_action(
        supervisor_service.start_process,
        name,
        'START_PROCESS',
        success_detail=f'启动进程: {name}'
    )


@api_bp.route('/process/<path:name>/stop', methods=['POST'])
@login_required_api
def stop_process(name):
    """停止进程"""
    return handle_process_action(
        supervisor_service.stop_process,
        name,
        'STOP_PROCESS',
        success_detail=f'停止进程: {name}'
    )


@api_bp.route('/process/<path:name>/restart', methods=['POST'])
@login_required_api
def restart_process(name):
    """重启进程"""
    return handle_process_action(
        supervisor_service.restart_process,
        name,
        'RESTART_PROCESS',
        success_detail=f'重启进程: {name}'
    )


@api_bp.route('/supervisor/state', methods=['GET'])
@login_required_api
def get_supervisor_state():
    """获取 SuperVisord 服务状态"""
    result = supervisor_service.get_supervisor_state()
    return from_service_result(result)


@api_bp.route('/supervisor/restart', methods=['POST'])
@login_required_api
def supervisor_restart():
    """重启 SuperVisord 服务（通过 systemctl，与启动/停止一致，见 SUPERVISOR_RESTART_CMD）"""
    result = supervisor_service.supervisor_restart()
    return from_service_result(result, 200, 400)


@api_bp.route('/supervisor/shutdown', methods=['POST'])
@login_required_api
def supervisor_shutdown():
    """停止 SuperVisord 服务（通过 systemctl，与启动一致，见 SUPERVISOR_STOP_CMD）"""
    result = supervisor_service.supervisor_shutdown()
    return from_service_result(result, 200, 400)


@api_bp.route('/supervisor/start', methods=['POST'])
@login_required_api
def supervisor_start():
    """启动 SuperVisord 服务（通过 systemctl）"""
    result = supervisor_service.supervisor_start()
    return from_service_result(result, 200, 400)


@api_bp.route('/logs/main', methods=['GET'])
@login_required_api
def get_main_log():
    """获取 SuperVisord 主日志（服务日志）"""
    offset = request.args.get('offset', -4096, type=int)
    result = supervisor_service.read_main_log(offset=offset)
    return from_service_result(result)


@api_bp.route('/logs/process/<path:name>', methods=['GET'])
@login_required_api
def get_process_log(name):
    """获取进程运行日志"""
    log_type = request.args.get('type', 'stdout')
    offset = request.args.get('offset', -8192, type=int)
    result = supervisor_service.read_process_log(name, log_type=log_type, offset=offset)
    return from_service_result(result)


@api_bp.route('/process/<path:name>/config', methods=['GET'])
@login_required_api
def get_process_config(name):
    """获取进程配置文件内容"""
    result = supervisor_service.get_config_content(name)
    return from_service_result(result)


@api_bp.route('/process/<path:name>/edit-config', methods=['GET'])
@login_required_api
def get_process_edit_config(name):
    """获取进程配置（解析为表单可编辑格式）"""
    result = supervisor_service.get_config_content(name)
    if not result.get('success') or not result.get('data'):
        return from_service_result(result)
    from app.services.config_manager import parse_config_to_dict
    parsed = parse_config_to_dict(result['data'], name)
    return from_service_result({'success': True, 'message': 'ok', 'data': parsed})
