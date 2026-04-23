import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional


INVALID_NAME_CHARS = re.compile(r'[\s\[\]\(\):]')
ALLOWED_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+$')


def to_supervisor_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[:\s\[\]\(\)]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name or 'unknown'


def validate_process_name(name: str) -> tuple[bool, str]:
    if not name or not name.strip():
        return False, '进程名称不能为空'
    name = name.strip()
    if ':' in name:
        return False, '进程名称不能包含冒号。Supervisor 不支持冒号，请使用下划线代替（如 sora_video）'
    if INVALID_NAME_CHARS.search(name):
        return False, '进程名不能包含空格或特殊字符'
    if not ALLOWED_NAME_PATTERN.match(name):
        return False, '进程名仅支持字母、数字、下划线、连字符'
    if len(name) > 100:
        return False, '进程名称过长'
    return True, ''


def _normalize_command(command: str) -> str:
    s = command.strip()
    s = re.sub(r'(bin/php\d*)(/[a-zA-Z])', r'\1 \2', s)
    return s


def build_program_config(config_dict: Dict) -> str:
    raw = config_dict.get('process_name', '').strip()
    name = to_supervisor_name(raw)
    command = _normalize_command(config_dict.get('command', ''))
    
    if not name or not command:
        raise ValueError('进程名称和启动命令为必填项')
    
    lines = [f'[program:{name}]', f'command={command}']
    if config_dict.get('directory'):
        lines.append(f"directory={config_dict['directory'].strip()}")
    
    if config_dict.get('user'):
        user = config_dict['user'].strip()
        if user:
            lines.append(f'user={user}')
    
    numprocs = config_dict.get('numprocs', 1)
    try:
        numprocs = int(numprocs)
        if numprocs > 1:
            lines.append(f'numprocs={numprocs}')
            lines.append(f'process_name=%(program_name)s_%(process_num)02d')
    except (TypeError, ValueError):
        pass
    
    autostart = config_dict.get('autostart', True)
    if isinstance(autostart, str):
        autostart = autostart.lower() in ('true', '1', 'yes')
    lines.append(f'autostart={str(autostart).lower()}')
    
    autorestart = config_dict.get('autorestart', 'unexpected')
    if autorestart not in ('true', 'false', 'unexpected'):
        autorestart = 'unexpected'
    lines.append(f'autorestart={autorestart}')
    
    lines.append(f'stdout_logfile=/var/log/supervisor/{name}.out.log')
    lines.append(f'stderr_logfile=/var/log/supervisor/{name}.err.log')
    
    if config_dict.get('environment'):
        env = config_dict['environment'].strip()
        if env:
            lines.append(f'environment={env}')
    
    priority = config_dict.get('priority', 999)
    try:
        priority = int(priority)
    except (TypeError, ValueError):
        priority = 999
    lines.append(f'priority={priority}')
    
    return '\n'.join(lines)


def parse_config_to_dict(content: str, process_name: str) -> Dict:
    result = {'process_name': process_name, 'command': '', 'directory': '', 'user': '', 'numprocs': 1,
              'autostart': 'true', 'autorestart': 'unexpected', 'environment': '', 'priority': 999}
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('[') or line.startswith(';') or line.startswith('#'):
            continue
        if '=' in line:
            k, _, v = line.partition('=')
            k, v = k.strip().lower(), v.strip()
            if k == 'command':
                result['command'] = v
            elif k == 'directory':
                result['directory'] = v
            elif k == 'user':
                result['user'] = v
            elif k == 'numprocs':
                try:
                    result['numprocs'] = int(v)
                except ValueError:
                    pass
            elif k == 'autostart':
                result['autostart'] = 'true' if v.lower() in ('true', '1', 'yes') else 'false'
            elif k == 'autorestart':
                result['autorestart'] = v if v in ('true', 'false', 'unexpected') else 'unexpected'
            elif k == 'environment':
                result['environment'] = v
            elif k == 'priority':
                try:
                    result['priority'] = int(v)
                except ValueError:
                    pass
    return result


def get_config_file_path(conf_dir: str, process_name: str, ext: str = 'conf') -> Path:
    safe_name = to_supervisor_name(process_name)
    return Path(conf_dir) / f'{safe_name}.{ext}'


def _sudo_tee(path_str: str, conf_dir: str, content: str) -> bool:
    path_str = str(Path(path_str).resolve())
    conf_dir_resolved = str(Path(conf_dir).resolve())
    if not path_str.startswith(conf_dir_resolved):
        return False
    try:
        subprocess.run(
            ['sudo', 'tee', path_str],
            input=content.encode('utf-8'),
            check=True,
            capture_output=True,
            timeout=10
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def write_config(conf_dir: str, process_name: str, config_content: str, use_sudo: bool = False, ext: str = 'conf') -> str:
    path = get_config_file_path(conf_dir, process_name, ext)
    Path(conf_dir).mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(config_content, encoding='utf-8')
        return str(path)
    except PermissionError:
        if use_sudo:
            if _sudo_tee(str(path), conf_dir, config_content):
                if path.exists():
                    return str(path)
                raise PermissionError('配置写入失败，请检查 sudoers')
            raise PermissionError('配置写入失败，请检查 SUPERVISOR_USE_SUDO_WRITE 及 sudoers')
        raise


def _sudo_rm(path_str: str, conf_dir: str) -> bool:
    """通过 sudo rm 删除文件，仅允许删除 conf_dir 下的文件"""
    path_str = str(Path(path_str).resolve())
    conf_dir_resolved = str(Path(conf_dir).resolve())
    if not path_str.startswith(conf_dir_resolved):
        return False
    try:
        subprocess.run(
            ['sudo', 'rm', '-f', path_str],
            check=True,
            capture_output=True,
            timeout=5
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def delete_config(conf_dir: str, process_name: str, use_sudo: bool = False) -> bool:
    deleted = False
    for ext in ('conf', 'ini'):
        path = get_config_file_path(conf_dir, process_name, ext)
        if not path.exists():
            continue
        path_str = str(path.resolve())
        conf_dir_resolved = str(Path(conf_dir).resolve())
        if not path_str.startswith(conf_dir_resolved):
            continue
        try:
            path.unlink()
            deleted = True
        except PermissionError:
            if use_sudo and _sudo_rm(path_str, conf_dir):
                deleted = True
    return deleted


def config_exists(conf_dir: str, process_name: str) -> bool:
    return get_config_file_path(conf_dir, process_name).exists()
