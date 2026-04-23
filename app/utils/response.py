from flask import jsonify
from typing import Any, Optional


def api_response(
    success: bool,
    message: str = '',
    data: Any = None,
    status_code: Optional[int] = None
) -> tuple:
    payload = {
        'success': success,
        'message': message or ('ok' if success else '失败'),
        'data': data
    }
    if status_code is None:
        status_code = 200 if success else 400
    return jsonify(payload), status_code


def api_success(data: Any = None, message: str = 'ok', status_code: int = 200) -> tuple:
    return api_response(True, message, data, status_code)


def api_error(message: str, status_code: int = 400, data: Any = None) -> tuple:
    return api_response(False, message, data, status_code)


def from_service_result(result: dict, success_status: int = 200, error_status: int = 400) -> tuple:
    success = result.get('success', False)
    status = success_status if success else error_status
    return api_response(
        success,
        result.get('message', ''),
        result.get('data'),
        status
    )
