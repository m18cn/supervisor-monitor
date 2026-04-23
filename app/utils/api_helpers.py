"""API 路由辅助函数"""
from flask import current_app
from typing import Callable, Any, Optional

from app.utils.response import from_service_result
from app.utils.logger import log_operation


def get_current_username() -> str:
    """获取当前登录用户名"""
    from flask_login import current_user
    return current_user.username if current_user.is_authenticated else 'anonymous'


def handle_service_call(
    service_func: Callable,
    *args,
    log_type: Optional[str] = None,
    log_success_detail: Optional[str] = None,
    log_fail_detail: Optional[str] = None,
    log_success_detail_fn: Optional[Callable[[dict], str]] = None,
    log_fail_detail_fn: Optional[Callable[[dict], str]] = None,
    success_status: int = 200,
    error_status: int = 400,
    **kwargs
) -> tuple:
    """统一处理 service 调用、操作日志与 API 响应

    Args:
        service_func: 要调用的 service 函数
        *args, **kwargs: 传递给 service_func 的参数
        log_type: 操作类型（如 ADD_PROCESS）
        log_success_detail: 成功时的日志详情（静态）
        log_fail_detail: 失败时的日志详情（静态）
        log_success_detail_fn: 成功时的日志详情函数 result -> str，优先于 log_success_detail
        log_fail_detail_fn: 失败时的日志详情函数 result -> str，优先于 log_fail_detail
        success_status: 成功时的 HTTP 状态码
        error_status: 失败时的 HTTP 状态码

    Returns:
        (Response, status_code)
    """
    result = service_func(*args, **kwargs)
    success = result.get('success', False)

    if log_type and current_app.operations_logger:
        username = get_current_username()
        if success:
            detail = (log_success_detail_fn(result) if log_success_detail_fn
                     else log_success_detail or str(result.get('data', '')))
            log_operation(current_app.operations_logger, log_type, username, detail, '成功')
        else:
            detail = (log_fail_detail_fn(result) if log_fail_detail_fn
                     else log_fail_detail or result.get('message', ''))
            log_operation(current_app.operations_logger, log_type, username, detail, '失败')

    return from_service_result(result, success_status, error_status)


def handle_process_action(
    service_func: Callable,
    name: str,
    log_type: str,
    success_detail: Optional[str] = None,
    log_on_fail: bool = False,
    fail_detail_template: str = '{name}: {message}'
) -> tuple:
    """处理进程相关操作（启动/停止/重启/删除）

    Args:
        service_func: service 函数，接收 name 参数
        name: 进程名
        log_type: 操作类型（START_PROCESS, STOP_PROCESS 等）
        success_detail: 成功时的日志详情，None 时不记录
        log_on_fail: 是否在失败时也记录日志
        fail_detail_template: 失败详情模板，{name} 和 {message} 会被替换
    """
    result = service_func(name)
    success = result.get('success', False)

    if current_app.operations_logger:
        username = get_current_username()
        if success and success_detail:
            log_operation(current_app.operations_logger, log_type, username, success_detail, '成功')
        elif not success and log_on_fail:
            detail = fail_detail_template.format(
                name=name,
                message=result.get('message', '')
            )
            log_operation(current_app.operations_logger, log_type, username, detail, '失败')

    return from_service_result(result, 200, 400)
