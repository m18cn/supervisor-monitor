import os
import re
import shlex
import subprocess
import time
import xmlrpc.client
from typing import Dict, List, Optional, Any, Tuple
from flask import current_app

from app.services.config_manager import (
    build_program_config,
    write_config,
    delete_config,
    validate_process_name,
    to_supervisor_name,
    get_config_file_path,
    parse_config_to_dict
)


_SUPERVISOR_SOCKET_PATHS = [
    '/var/run/supervisor.sock',
    '/var/run/supervisord.sock',
    '/tmp/supervisor.sock',
]


def _translate_supervisor_error(fault_string: str) -> str:
    s = str(fault_string)
    if 'CANT_REREAD' in s and ('Invalid name' in s or "because of character" in s or "':'" in s):
        return '配置加载失败：进程名不能包含冒号，请改为下划线'
    if 'BAD_NAME' in s and ("Invalid name" in s or "because of character" in s or "':'" in s):
        return '进程名不能包含冒号，请用下划线'
    if 'BAD_NAME' in s:
        return '进程未识别，请检查 supervisord.conf 的 include 及 sudoers'
    return s


def _get_socket_path():
    path = current_app.config.get('SUPERVISOR_SOCKET_PATH')
    if path:
        if path.startswith('unix://'):
            path = path[7:].lstrip('/')
        return path.strip() or None
    return None


def _try_unix_socket(socket_path):
    from app.utils.unix_xmlrpc import get_unix_socket_proxy
    return get_unix_socket_proxy(socket_path)


def get_supervisor_server():
    socket_path = _get_socket_path()
    if not socket_path and os.name != 'nt':
        for p in _SUPERVISOR_SOCKET_PATHS:
            if os.path.exists(p):
                socket_path = p
                break
    if socket_path:
        return _try_unix_socket(socket_path)
    url = current_app.config.get('SUPERVISOR_RPC_URL', 'http://127.0.0.1:9001/RPC2')
    return xmlrpc.client.ServerProxy(url)


def _safe_process_info(proc: Dict) -> Optional[Dict]:
    try:
        return {
            'name': proc.get('name', ''),
            'group': proc.get('group', ''),
            'description': proc.get('description', ''),
            'state': proc.get('state', 0),
            'statename': proc.get('statename', 'UNKNOWN'),
            'pid': proc.get('pid', 0),
            'start': proc.get('start', 0),
            'stop': proc.get('stop', 0),
            'now': proc.get('now', 0),
            'spawnerr': proc.get('spawnerr', ''),
            'exitstatus': proc.get('exitstatus', 0),
            'stdout_logfile': proc.get('stdout_logfile', ''),
            'stderr_logfile': proc.get('stderr_logfile', ''),
        }
    except Exception:
        return None


def _read_group_config(conf_dir: str, group_name: str) -> Dict:
    from app.services.config_manager import get_config_file_path
    result = {'user': '-', 'priority': 999}
    for ext in ('ini', 'conf'):
        path = get_config_file_path(conf_dir, group_name, ext)
        if path.exists():
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('user='):
                        result['user'] = line.split('=', 1)[1].strip()
                    elif line.startswith('priority='):
                        try:
                            result['priority'] = int(line.split('=', 1)[1].strip())
                        except (ValueError, IndexError):
                            pass
            except Exception:
                pass
            break
    return result


def _group_processes(processes: List[Dict], conf_dir: str) -> List[Dict]:
    groups = {}
    for p in processes:
        g = p.get('group', '') or p.get('name', '')
        if g not in groups:
            cfg = _read_group_config(conf_dir, g)
            groups[g] = {
                'group': g,
                'name': g,
                'processes': [],
                'user': cfg['user'],
                'priority': cfg['priority'],
            }
        groups[g]['processes'].append(p)
    result = []
    for g, data in groups.items():
        procs = data['processes']
        pids = [str(p['pid']) for p in procs if p.get('pid')]
        statuses = [p.get('statename', '') for p in procs]
        all_running = all(s == 'RUNNING' for s in statuses)
        any_running = any(s == 'RUNNING' for s in statuses)
        if all_running:
            statename = 'RUNNING'
        elif any_running:
            statename = 'RUNNING'
        else:
            statename = statuses[0] if statuses else 'STOPPED'
        proc_name = procs[0].get('name', g) if procs else g
        log_process_name = f'{g}:{proc_name}' if proc_name else g
        result.append({
            'group': g,
            'name': g,
            'log_process_name': log_process_name,
            'user': data['user'],
            'pid': ', '.join(pids) if pids else '-',
            'count': len(procs),
            'priority': data['priority'],
            'statename': statename,
            'stdout_logfile': procs[0].get('stdout_logfile', '') if procs else '',
            'processes': procs,
        })
    return result


def _build_grouped_process_list_from_server(server, conf_dir: str, grouped: bool) -> List[Dict]:
    """从已连接的 XML-RPC server 拉取并可选按 conf 归组。"""
    raw_list = server.supervisor.getAllProcessInfo()
    result: List[Dict] = []
    for proc in raw_list:
        parsed = _safe_process_info(proc)
        if parsed:
            result.append(parsed)
    if grouped and result:
        result = _group_processes(result, conf_dir)
    return result


def _run_shell_command(cmd: str, timeout: int) -> Tuple[bool, str]:
    """
    执行系统命令（如 systemctl），供启停复用。
    成功返回 (True, ''); 失败返回 (False, 错误信息)。
    """
    if not (cmd and str(cmd).strip()):
        return False, '命令未配置'
    try:
        argv = shlex.split(cmd, posix=(os.name != 'nt'))
        subprocess.run(argv, check=True, capture_output=True, timeout=timeout)
        return True, ''
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or b'').decode('utf-8', errors='ignore').strip()
        return False, err or '命令执行失败'
    except FileNotFoundError:
        return False, '未找到要执行的程序（请检查 PATH 或命令路径）'
    except subprocess.TimeoutExpired:
        return False, '命令执行超时'
    except ValueError as e:
        return False, f'无法解析命令: {e}'
    except Exception as e:
        return False, str(e)


def _is_connection_like_error(err: Exception) -> bool:
    s = str(err)
    return (
        isinstance(err, PermissionError)
        or 'Permission denied' in s
        or 'Errno 13' in s
        or 'Connection refused' in s
        or '111' in s
    )


def _get_http_supervisor_server():
    url = current_app.config.get('SUPERVISOR_RPC_URL', 'http://127.0.0.1:9001/RPC2')
    return xmlrpc.client.ServerProxy(url)


def _build_include_diagnostic(conf_dir: str, conf_ext: str, process_name: str) -> str:
    """构造 include/扩展名排查信息，便于前端直接定位 conf/ini 不一致。"""
    cfg_path = get_config_file_path(conf_dir, process_name, conf_ext)
    include_files = 'unknown'
    main_conf = current_app.config.get('SUPERVISORD_CONF', '/etc/supervisor/supervisord.conf')
    try:
        with open(main_conf, 'r', encoding='utf-8', errors='ignore') as f:
            in_include = False
            for raw in f:
                line = raw.strip()
                if not line or line.startswith(('#', ';')):
                    continue
                if line.lower().startswith('[include]'):
                    in_include = True
                    continue
                if in_include and line.startswith('['):
                    break
                if in_include and line.lower().startswith('files'):
                    include_files = line.split('=', 1)[1].strip() if '=' in line else line
                    break
    except Exception:
        pass
    return (
        f"排查信息：SUPERVISOR_CONF_EXT={conf_ext}, "
        f"写入文件={cfg_path}, include files={include_files}"
    )


def get_all_process_info(grouped: bool = True) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    conf_dir = current_app.config.get('SUPERVISOR_CONF_DIR', '/etc/supervisor/conf.d')
    try:
        server = get_supervisor_server()
        result = _build_grouped_process_list_from_server(server, conf_dir, grouped)
        return {'success': True, 'message': 'ok', 'data': result}
    except xmlrpc.client.Fault as e:
        return {'success': False, 'message': _translate_supervisor_error(e.faultString), 'data': []}
    except Exception as e:
        last_error = e
        if _is_connection_like_error(e):
            for sock_path in _SUPERVISOR_SOCKET_PATHS:
                if os.path.exists(sock_path):
                    try:
                        server = _try_unix_socket(sock_path)
                        result = _build_grouped_process_list_from_server(server, conf_dir, grouped)
                        return {'success': True, 'message': 'ok', 'data': result}
                    except Exception:
                        continue
        if _is_connection_like_error(e):
            try:
                http_server = _get_http_supervisor_server()
                result = _build_grouped_process_list_from_server(http_server, conf_dir, grouped)
                return {'success': True, 'message': 'ok', 'data': result}
            except Exception as e2:
                last_error = e2
        return {
            'success': False,
            'message': f'连接失败: {str(last_error)}',
            'data': []
        }


def add_process(config_dict: Dict) -> Dict[str, Any]:
    raw_name = config_dict.get('process_name', '').strip()
    is_valid, err_msg = validate_process_name(raw_name)
    if not is_valid:
        return {'success': False, 'message': err_msg, 'data': None}

    name = to_supervisor_name(raw_name)
    conf_dir = current_app.config.get('SUPERVISOR_CONF_DIR', '/etc/supervisor/conf.d')
    conf_ext = current_app.config.get('SUPERVISOR_CONF_EXT', 'conf')
    use_sudo_write = current_app.config.get('SUPERVISOR_USE_SUDO_WRITE', False)

    try:
        config_content = build_program_config(config_dict)
        write_config(conf_dir, name, config_content, use_sudo=use_sudo_write, ext=conf_ext)
        
        server = get_supervisor_server()
        result = server.supervisor.reloadConfig()
        added, changed, removed = result[0]
        if name in added:
            group_name = name
        elif name in changed:
            group_name = name
        else:
            cfg_path = get_config_file_path(conf_dir, name, conf_ext)
            if not cfg_path.exists():
                return {'success': False, 'message': '配置写入失败，请检查 SUPERVISOR_USE_SUDO_WRITE 及 sudoers', 'data': None}
            try:
                server.supervisor.addProcessGroup(name)
                group_name = name
            except xmlrpc.client.Fault as e:
                diag = _build_include_diagnostic(conf_dir, conf_ext, name)
                return {
                    'success': False,
                    'message': f'Supervisor 未加载，请检查 include 并执行 supervisorctl reread。{diag}',
                    'data': None
                }
        time.sleep(1)
        try:
            _start_process_group(server, group_name)
        except xmlrpc.client.Fault as e:
            if 'BAD_NAME' not in str(e.faultString):
                raise
            ok, msg = _restart_supervisord_via_cmd()
            if ok:
                return {'success': True, 'message': '添加成功，已重启 SuperVisord', 'data': {'name': group_name}}
            if msg == 'NEED_MANUAL':
                return {'success': True, 'message': '添加成功，请手动重启 SuperVisord', 'data': {'name': group_name}}
            return {'success': False, 'message': f'启动失败，请手动重启 SuperVisord：{msg}', 'data': None}

        return {'success': True, 'message': '添加成功', 'data': {'name': group_name}}
        
    except xmlrpc.client.Fault as e:
        return {'success': False, 'message': _translate_supervisor_error(e.faultString), 'data': None}
    except ValueError as e:
        return {'success': False, 'message': str(e), 'data': None}
    except Exception as e:
        try:
            use_sudo_rm = current_app.config.get('SUPERVISOR_USE_SUDO_RM', False)
            delete_config(conf_dir, name, use_sudo=use_sudo_rm)
        except Exception:
            pass
        return {'success': False, 'message': f'添加失败: {str(e)}', 'data': None}


def remove_process(name: str) -> Dict[str, Any]:
    if not name or not name.strip():
        return {'success': False, 'message': '进程名不能为空', 'data': None}

    group_name = to_supervisor_name(name.strip())
    conf_dir = current_app.config.get('SUPERVISOR_CONF_DIR', '/etc/supervisor/conf.d')

    try:
        server = get_supervisor_server()
        stop_target = f'{group_name}:*'
        stopped = False
        for target in (stop_target, group_name):
            try:
                server.supervisor.stopProcess(target, True)
                stopped = True
                break
            except xmlrpc.client.Fault as e:
                if 'NOT_RUNNING' in str(e.faultString) or 'BAD_NAME' in str(e.faultString):
                    stopped = True
                    break
                continue
        if not stopped:
            return {'success': False, 'message': '停止进程失败', 'data': None}
        use_sudo_rm = current_app.config.get('SUPERVISOR_USE_SUDO_RM', False)
        try:
            deleted = delete_config(conf_dir, group_name, use_sudo=use_sudo_rm)
            if not deleted:
                from pathlib import Path
                from app.services.config_manager import _sudo_rm
                for pattern in ('*.ini', '*.conf'):
                    for f in Path(conf_dir).glob(pattern):
                        try:
                            content = f.read_text(encoding='utf-8', errors='ignore')
                            pattern = rf'^\[program:{re.escape(group_name)}\]\s*$'
                            if re.search(pattern, content, flags=re.MULTILINE):
                                try:
                                    f.unlink()
                                except PermissionError:
                                    if use_sudo_rm:
                                        deleted = _sudo_rm(str(f), conf_dir)
                                    else:
                                        raise
                                else:
                                    deleted = True
                                break
                        except PermissionError:
                            return {
                                'success': False,
                                'message': '删除失败：权限不足，请配置 sudoers',
                                'data': None
                            }
                        except Exception:
                            continue
                    if deleted:
                        break
        except PermissionError:
            return {
                'success': False,
                'message': f'删除失败: 权限不足。请设置环境变量 SUPERVISOR_USE_SUDO_RM=1 并配置 sudoers，或执行 sudo chown -R www:www {conf_dir}',
                'data': None
            }
        result = server.supervisor.reloadConfig()
        added, changed, removed = result[0]
        try:
            server.supervisor.removeProcessGroup(group_name)
        except xmlrpc.client.Fault as e:
            if 'BAD_NAME' not in str(e.faultString):
                return {'success': False, 'message': _translate_supervisor_error(e.faultString), 'data': None}
        
        return {'success': True, 'message': '删除成功', 'data': {'name': group_name}}
        
    except PermissionError as e:
        return {
            'success': False,
            'message': '删除失败：权限不足',
            'data': None
        }
    except xmlrpc.client.Fault as e:
        return {'success': False, 'message': _translate_supervisor_error(e.faultString), 'data': None}
    except Exception as e:
        err_msg = str(e)
        if 'Permission denied' in err_msg or 'Errno 13' in err_msg:
            return {
                'success': False,
                'message': '删除失败：权限不足',
                'data': None
            }
        return {'success': False, 'message': f'删除失败: {err_msg}', 'data': None}


def update_process(name: str, config_dict: Dict) -> Dict[str, Any]:
    group_name = to_supervisor_name(name.strip())
    if not group_name:
        return {'success': False, 'message': '进程名不能为空', 'data': None}
    config_dict = dict(config_dict)
    config_dict['process_name'] = group_name
    raw_name = config_dict.get('process_name', '').strip()
    is_valid, err_msg = validate_process_name(raw_name)
    if not is_valid:
        return {'success': False, 'message': err_msg, 'data': None}
    conf_dir = current_app.config.get('SUPERVISOR_CONF_DIR', '/etc/supervisor/conf.d')
    conf_ext = current_app.config.get('SUPERVISOR_CONF_EXT', 'conf')
    use_sudo_write = current_app.config.get('SUPERVISOR_USE_SUDO_WRITE', False)
    new_numprocs = int(config_dict.get('numprocs', 1)) if config_dict.get('numprocs') else 1
    old_numprocs = 1
    cfg_path = get_config_file_path(conf_dir, group_name, conf_ext)
    if cfg_path.exists():
        try:
            old_content = cfg_path.read_text(encoding='utf-8', errors='ignore')
            old_numprocs = int(parse_config_to_dict(old_content, group_name).get('numprocs', 1)) or 1
        except Exception:
            pass
    numprocs_changed = old_numprocs != new_numprocs

    try:
        server = get_supervisor_server()
        try:
            server.supervisor.stopProcessGroup(group_name, True)
        except xmlrpc.client.Fault as e:
            if 'NOT_RUNNING' not in str(e.faultString) and 'BAD_NAME' not in str(e.faultString):
                return {'success': False, 'message': _translate_supervisor_error(e.faultString), 'data': None}
        config_content = build_program_config(config_dict)
        write_config(conf_dir, group_name, config_content, use_sudo=use_sudo_write, ext=conf_ext)

        if numprocs_changed:
            ok, msg = _restart_supervisord_via_cmd()
            if ok:
                return {'success': True, 'message': '更新成功，已重启 SuperVisord', 'data': {'name': group_name}}
            if msg == 'NEED_MANUAL':
                return {'success': True, 'message': '更新成功，请手动重启 SuperVisord', 'data': {'name': group_name}}
            return {'success': False, 'message': f'进程数量已变更，重启失败：{msg}', 'data': None}

        result = server.supervisor.reloadConfig()
        added, changed, removed = result[0]
        time.sleep(1)
        try:
            _start_process_group(server, group_name)
        except xmlrpc.client.Fault as e:
            if 'BAD_NAME' not in str(e.faultString):
                raise
            diag = _build_include_diagnostic(conf_dir, conf_ext, group_name)
            ok, msg = _restart_supervisord_via_cmd()
            if ok:
                return {'success': True, 'message': '更新成功，已重启 SuperVisord', 'data': {'name': group_name}}
            if msg == 'NEED_MANUAL':
                return {
                    'success': True,
                    'message': f'更新成功，请手动重启 SuperVisord。{diag}',
                    'data': {'name': group_name}
                }
            return {
                'success': False,
                'message': f'启动失败，请手动重启：{msg}。{diag}',
                'data': None
            }
        return {'success': True, 'message': '更新成功', 'data': {'name': group_name}}
    except xmlrpc.client.Fault as e:
        return {'success': False, 'message': _translate_supervisor_error(e.faultString), 'data': None}
    except ValueError as e:
        return {'success': False, 'message': str(e), 'data': None}
    except Exception as e:
        return {'success': False, 'message': f'更新失败: {str(e)}', 'data': None}


def _start_process_group(server, group_name: str) -> None:
    def _try_start() -> bool:
        for fn in [
            lambda: server.supervisor.startProcessGroup(group_name, True),
            lambda: server.supervisor.startProcess(f'{group_name}:*', True),
            lambda: server.supervisor.startProcess(group_name, True),
        ]:
            try:
                fn()
                return True
            except xmlrpc.client.Fault as e:
                if 'BAD_NAME' not in str(e.faultString):
                    raise
        return False

    if _try_start():
        return
    for _ in range(2):
        time.sleep(1.5)
        if _try_start():
            return
    raise xmlrpc.client.Fault(10, f'BAD_NAME: {group_name}')


def _restart_supervisord_via_cmd() -> tuple[bool, str]:
    if not current_app.config.get('SUPERVISOR_AUTO_RESTART_ON_FAIL', True):
        return False, 'NEED_MANUAL'
    cmd = current_app.config.get('SUPERVISOR_RESTART_CMD', 'sudo systemctl restart supervisord')
    ok, err = _run_shell_command(cmd, timeout=15)
    if ok:
        time.sleep(2)
        return True, '已重启 SuperVisord'
    return False, err or '重启失败'


def _get_process_target(name: str) -> str:
    return to_supervisor_name(name.strip())


def start_process(name: str) -> Dict[str, Any]:
    if not name or not name.strip():
        return {'success': False, 'message': '进程名不能为空', 'data': None}
    target = _get_process_target(name)
    api_target = f'{target}:*'
    try:
        server = get_supervisor_server()
        try:
            server.supervisor.startProcess(api_target, True)
        except xmlrpc.client.Fault as e:
            if 'BAD_NAME' in str(e.faultString):
                server.supervisor.startProcess(target, True)
            else:
                raise
        return {'success': True, 'message': '启动成功', 'data': {'name': name}}
    except xmlrpc.client.Fault as e:
        return {'success': False, 'message': _translate_supervisor_error(e.faultString), 'data': None}
    except Exception as e:
        return {'success': False, 'message': f'启动失败: {str(e)}', 'data': None}


def stop_process(name: str) -> Dict[str, Any]:
    if not name or not name.strip():
        return {'success': False, 'message': '进程名不能为空', 'data': None}
    target = _get_process_target(name)
    api_target = f'{target}:*'
    try:
        server = get_supervisor_server()
        try:
            server.supervisor.stopProcess(api_target, True)
        except xmlrpc.client.Fault as e:
            if 'BAD_NAME' in str(e.faultString):
                server.supervisor.stopProcess(target, True)
            else:
                raise
        return {'success': True, 'message': '停止成功', 'data': {'name': name}}
    except xmlrpc.client.Fault as e:
        return {'success': False, 'message': _translate_supervisor_error(e.faultString), 'data': None}
    except Exception as e:
        return {'success': False, 'message': f'停止失败: {str(e)}', 'data': None}


def restart_process(name: str) -> Dict[str, Any]:
    if not name or not name.strip():
        return {'success': False, 'message': '进程名不能为空', 'data': None}
    target = _get_process_target(name)
    api_target = f'{target}:*'
    try:
        server = get_supervisor_server()
        try:
            server.supervisor.stopProcess(api_target, True)
        except xmlrpc.client.Fault as e:
            if 'BAD_NAME' in str(e.faultString):
                server.supervisor.stopProcess(target, True)
            else:
                raise
        try:
            server.supervisor.startProcess(api_target, True)
        except xmlrpc.client.Fault as e:
            if 'BAD_NAME' in str(e.faultString):
                server.supervisor.startProcess(target, True)
            else:
                raise
        return {'success': True, 'message': '重启成功', 'data': {'name': name}}
    except xmlrpc.client.Fault as e:
        return {'success': False, 'message': _translate_supervisor_error(e.faultString), 'data': None}
    except Exception as e:
        return {'success': False, 'message': f'重启失败: {str(e)}', 'data': None}


def get_supervisor_state() -> Dict[str, Any]:
    try:
        server = get_supervisor_server()
        state = server.supervisor.getState()
        return {'success': True, 'message': 'ok', 'data': state}
    except Exception as e:
        if _is_connection_like_error(e):
            for sock_path in _SUPERVISOR_SOCKET_PATHS:
                if os.path.exists(sock_path):
                    try:
                        server = _try_unix_socket(sock_path)
                        state = server.supervisor.getState()
                        return {'success': True, 'message': 'ok', 'data': state}
                    except Exception:
                        continue
            try:
                http_server = _get_http_supervisor_server()
                state = http_server.supervisor.getState()
                return {'success': True, 'message': 'ok', 'data': state}
            except Exception as e2:
                return {'success': False, 'message': f'连接失败: {str(e2)}', 'data': None}
        return {'success': False, 'message': str(e), 'data': None}


def supervisor_restart() -> Dict[str, Any]:
    """通过 systemctl 重启服务，与启动/停止路径一致。"""
    cmd = current_app.config.get('SUPERVISOR_RESTART_CMD', 'sudo systemctl restart supervisord')
    ok, err = _run_shell_command(cmd, timeout=20)
    if ok:
        return {'success': True, 'message': '重启成功', 'data': None}
    return {'success': False, 'message': err or '重启失败', 'data': None}


def supervisor_shutdown() -> Dict[str, Any]:
    """通过 systemctl 停止服务，与「启动」一致，避免仅 RPC shutdown 与 systemd 状态不同步。"""
    cmd = current_app.config.get('SUPERVISOR_STOP_CMD', 'sudo systemctl stop supervisord')
    ok, err = _run_shell_command(cmd, timeout=30)
    if ok:
        return {'success': True, 'message': '已停止', 'data': None}
    return {'success': False, 'message': err or '停止失败', 'data': None}


def supervisor_start() -> Dict[str, Any]:
    cmd = current_app.config.get('SUPERVISOR_START_CMD', 'sudo systemctl start supervisord')
    ok, err = _run_shell_command(cmd, timeout=10)
    if ok:
        return {'success': True, 'message': '启动成功', 'data': None}
    return {'success': False, 'message': err or '启动失败', 'data': None}


def read_main_log(offset: int = -4096, length: int = 0) -> Dict[str, Any]:
    try:
        server = get_supervisor_server()
        content = server.supervisor.readLog(offset, length)
        return {'success': True, 'message': 'ok', 'data': content}
    except Exception as e:
        return {'success': False, 'message': str(e), 'data': ''}


def read_process_log(name: str, log_type: str = 'stdout', offset: int = -8192, length: int = 0) -> Dict[str, Any]:
    name = name.strip()
    length = length or 8192

    def _read(server, n):
        if log_type == 'stderr':
            return server.supervisor.tailProcessStderrLog(n, offset, length)
        return server.supervisor.tailProcessStdoutLog(n, offset, length)

    try:
        server = get_supervisor_server()
        try:
            content = _read(server, name)
        except xmlrpc.client.Fault as e:
            if 'BAD_NAME' in str(e.faultString) and ':' in name:
                content = _read(server, name.split(':', 1)[1])
            else:
                raise
        if isinstance(content, (list, tuple)):
            content = content[0] if content else ''
        return {'success': True, 'message': 'ok', 'data': content}
    except Exception as e:
        return {'success': False, 'message': str(e), 'data': ''}


def get_config_content(group_name: str) -> Dict[str, Any]:
    from app.services.config_manager import get_config_file_path
    conf_dir = current_app.config.get('SUPERVISOR_CONF_DIR', '/etc/supervisor/conf.d')
    for ext in ('ini', 'conf'):
        path = get_config_file_path(conf_dir, group_name, ext)
        if path.exists():
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                return {'success': True, 'message': 'ok', 'data': content}
            except Exception as e:
                return {'success': False, 'message': str(e), 'data': ''}
    return {'success': False, 'message': '配置不存在', 'data': ''}
