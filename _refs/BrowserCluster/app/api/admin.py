"""
配置管理 API 路由模块

提供系统配置的增删改查功能
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse
import time
import sys
import os
import asyncio
from app.models.config import ConfigModel
from app.db.sqlite import sqlite_db
from app.core.config import settings
from app.services.node_manager import node_manager
from app.core.auth import get_current_admin

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/configs", tags=["Configs"])


@router.get("/logs")
async def get_system_logs(
    lines: int = Query(100, ge=1, le=1000),
    stream: bool = Query(False),
    current_admin: dict = Depends(get_current_admin)
):
    """
    获取系统主日志
    
    Args:
        lines: 返回最后多少行日志
        stream: 是否实时流式输出
    """
    log_file = settings.log_file
    
    if not os.path.exists(log_file):
        return StreamingResponse(iter(["Waiting for system logs..."]), media_type="text/plain")

    def read_last_lines(file_path, n):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                return all_lines[-n:]
        except Exception as e:
            return [f"Error reading log file: {str(e)}"]

    if not stream:
        content = "".join(read_last_lines(log_file, lines))
        return StreamingResponse(iter([content]), media_type="text/plain")

    # 流式输出实现 (类似 tail -f)
    async def log_generator():
        # 先发送最后 N 行
        last_lines = read_last_lines(log_file, lines)
        for line in last_lines:
            yield line
            
        # 持续监听新内容
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                # 移动到文件末尾
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(0.5)
                        continue
                    yield line
        except Exception as e:
            yield f"\n[Log Stream Error: {str(e)}]"

    return StreamingResponse(log_generator(), media_type="text/plain")


@router.get("/schema")
async def get_config_schema(current_admin: dict = Depends(get_current_admin)):
    """
    获取配置 schema，包含所有可配置项及其默认值
    """
    # 获取 Settings 类的 JSON Schema
    schema = settings.model_json_schema()
    
    # 提取属性及其默认值
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    
    result = []
    for key, prop in properties.items():
        # 获取当前值（如果已加载）
        current_value = getattr(settings, key, None)
        
        result.append({
            "key": key,
            "title": prop.get("title", key),
            "type": prop.get("type", "string"),
            "default": prop.get("default"),
            "description": prop.get("description", ""),
            "required": key in required,
            "current_value": current_value
        })
    
    return result


@router.post("/restart")
async def restart_system(background_tasks: BackgroundTasks, current_admin: dict = Depends(get_current_admin)):
    """
    强制重启系统
    """
    # 在重启前停止所有正在运行的节点
    await node_manager.stop_all_nodes()
    
    def restart():
        # 给一点时间让响应返回
        time.sleep(1.0)
        logger.info("系统正在重启...")
        try:
            # 1. 如果是调试模式（uvicorn reload），通过 touch main.py 触发重启
            if settings.debug:
                main_py = os.path.join(os.getcwd(), "app", "main.py")
                if os.path.exists(main_py):
                    os.utime(main_py, None)
                    logger.info("已触发 uvicorn 热重载")
                    return

            # 2. 如果是非调试模式，或者 touch 无效，尝试直接重启进程
            # 获取当前运行的命令行参数
            args = sys.argv[:]
            if not args[0].endswith('.exe') and not args[0].endswith('python'):
                args.insert(0, sys.executable)
            
            logger.info(f"直接重启进程: {' '.join(args)}")
            if sys.platform == 'win32':
                # Windows 下使用 subprocess 启动新进程并退出旧进程
                import subprocess
                subprocess.Popen(args, close_fds=True)
                os._exit(0)
            else:
                # Unix/Linux 下使用 os.execv 替换当前进程
                os.execv(sys.executable, args)
        except Exception as e:
            logger.error(f"重启失败: {e}")
            os._exit(1)

    background_tasks.add_task(restart)
    return {"message": "System restart initiated"}


@router.get("/export")
async def export_configs_env(current_admin: dict = Depends(get_current_admin)):
    """
    导出配置为 .env 格式文件
    """
    # 1. 获取所有配置
    # 获取数据库中的配置
    db_configs = sqlite_db.get_all_configs()
    db_map = {c["key"]: c for c in db_configs}
    
    # 获取 Settings 类的 JSON Schema 以便按顺序导出并获取描述
    schema = settings.model_json_schema()
    properties = schema.get("properties", {})
    
    env_content = []
    env_content.append(f"# Browser Cluster Configuration - Exported at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    env_content.append("# Format compatible with .env files\n")
    
    # 2. 遍历 schema 中的键，优先导出
    for key in properties.keys():
        # 获取值：优先从数据库获取，如果没有则从 settings 获取（即默认值）
        value = None
        description = properties[key].get("description", "")
        
        if key in db_map:
            value = db_map[key]["value"]
            # 如果数据库中有描述，使用数据库的
            if db_map[key].get("description"):
                description = db_map[key]["description"]
        else:
            value = getattr(settings, key, None)
            
        if value is None:
            value = ""
            
        # 写入描述注释
        if description:
            env_content.append(f"# {description}")
        
        # 转换值为字符串，布尔值转为小写
        if isinstance(value, bool):
            val_str = str(value).lower()
        else:
            val_str = str(value)
            
        env_content.append(f"{key.upper()}={val_str}\n")
        
    # 3. 导出数据库中存在但不在 schema 中的键（自定义动态配置）
    custom_keys = [k for k in db_map.keys() if k not in properties]
    if custom_keys:
        env_content.append("# Custom/Dynamic Configurations")
        for key in custom_keys:
            value = db_map[key]["value"]
            description = db_map[key].get("description", "Custom configuration")
            env_content.append(f"# {description}")
            env_content.append(f"{key.upper()}={value}\n")
            
    content = "\n".join(env_content)
    
    return StreamingResponse(
        iter([content]), 
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=browser_cluster_{time.strftime('%Y%m%d_%H%M%S')}.env"}
    )


@router.get("/")
async def list_configs(current_admin: dict = Depends(get_current_admin)):
    """
    获取所有配置

    Returns:
        list: 配置列表
    """
    configs = sqlite_db.get_all_configs()
    return configs


@router.post("/")
async def create_config(config: ConfigModel, current_admin: dict = Depends(get_current_admin)):
    """
    创建新配置

    Args:
        config: 配置数据

    Returns:
        dict: 创建结果

    Raises:
        HTTPException: 配置键已存在时返回 400
    """
    # 检查配置键是否已存在
    existing = sqlite_db.get_config(config.key)
    if existing:
        raise HTTPException(status_code=400, detail="Config key already exists")

    # 插入新配置
    sqlite_db.set_config(config.key, config.value, config.description)

    # 立即从数据库重载配置到内存中的 settings 对象
    settings.load_from_db()

    return {"message": "Config created", "key": config.key}


@router.put("/{key}")
async def update_config(key: str, value: dict, current_admin: dict = Depends(get_current_admin)):
    """
    更新配置

    Args:
        key: 配置键
        value: 新值

    Returns:
        dict: 更新结果

    Raises:
        HTTPException: 配置不存在时返回 404
    """
    # 检查配置是否存在
    existing = sqlite_db.get_config(key)
    if not existing:
        raise HTTPException(status_code=404, detail="Config not found")

    # 更新配置
    sqlite_db.set_config(key, value.get("value"), existing.get("description"))

    # 立即从数据库重载配置到内存中的 settings 对象
    settings.load_from_db()

    return {"message": "Config updated"}


@router.delete("/{key}")
async def delete_config(key: str, current_admin: dict = Depends(get_current_admin)):
    """
    删除配置

    Args:
        key: 配置键

    Returns:
        dict: 删除结果

    Raises:
        HTTPException: 配置不存在时返回 404
    """
    success = sqlite_db.delete_config(key)

    if not success:
        raise HTTPException(status_code=404, detail="Config not found")

    # 立即从数据库重载配置到内存中的 settings 对象
    settings.load_from_db()

    return {"message": "Config deleted"}
