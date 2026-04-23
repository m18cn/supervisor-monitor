"""操作日志模块"""
import logging
from pathlib import Path
from datetime import datetime


def setup_logger(log_dir: Path, log_file: str) -> logging.Logger:
    """配置并返回操作日志 logger"""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file
    
    logger = logging.getLogger('operations')
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding='utf-8')
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    
    return logger


def log_operation(logger: logging.Logger, op_type: str, user: str, detail: str, result: str):
    """记录操作日志
    
    格式: 时间 | 操作类型 | 用户 | 详情 | 结果
    """
    if logger:
        logger.info(f"{op_type} | {user} | {detail} | {result}")
