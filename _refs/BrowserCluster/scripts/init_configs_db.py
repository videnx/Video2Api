import os
import sys
from datetime import datetime

# 将项目根目录添加到 python 路径
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from app.core.config import settings
from app.db.sqlite import sqlite_db
from app.core.logger import setup_logging
import logging

def init_configs():
    """
    将当前 settings (从 .env 加载) 中的配置项写入 SQLite 数据库
    """
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("开始初始化系统配置到 SQLite 数据库...")
    
    # 获取 settings 中的所有配置项
    # 我们排除一些敏感或不需要在数据库中动态修改的内部字段
    exclude_keys = {'env_file', 'env_file_encoding', 'case_sensitive'}
    
    # 获取 Settings 类中定义的字段
    fields = settings.__class__.model_fields.keys()
    
    count = 0
    for key in fields:
        if key in exclude_keys:
            continue
            
        value = getattr(settings, key)
        
        # 检查数据库中是否已存在该配置
        existing = sqlite_db.get_config(key)
        
        # 预定义一些常见配置的友好描述
        descriptions = {
            "app_name": "应用名称，用于标识系统",
            "app_version": "系统当前版本号",
            "debug": "调试模式开关，开启后会输出详细日志",
            "host": "服务监听的主机地址",
            "port": "服务监听的端口号",
            "mongo_uri": "MongoDB 数据库连接 URI",
            "mongo_db": "MongoDB 数据库名称",
            "redis_url": "Redis 连接 URL，用于任务队列等",
            "redis_cache_url": "Redis 缓存连接 URL，用于存储抓取结果缓存",
            "rabbitmq_url": "RabbitMQ 消息队列连接 URL",
            "rabbitmq_queue": "RabbitMQ 默认任务队列名称",
            "rabbitmq_exchange": "RabbitMQ 交换机名称",
            "browser_type": "默认浏览器类型 (chromium, firefox, webkit)",
            "browser_engine": "浏览器驱动引擎 (playwright, drissionpage)",
            "headless": "是否以无头模式运行浏览器",
            "block_images": "是否拦截图片加载",
            "block_media": "是否拦截媒体资源加载 (视频/音频)",
            "default_wait_for": "默认页面等待策略 (networkidle, load, domcontentloaded)",
            "default_timeout": "默认任务超时时间 (毫秒)",
            "default_viewport_width": "默认浏览器视口宽度",
            "default_viewport_height": "默认浏览器视口高度",
            "user_agent": "默认浏览器 User-Agent",
            "browser_idle_timeout": "浏览器实例空闲超时时间 (秒)",
            "stealth_mode": "是否默认开启反爬虫隐身模式",
            "cache_enabled": "是否全局启用结果缓存",
            "default_cache_ttl": "默认缓存过期时间 (秒)",
            "node_id": "当前工作节点的唯一标识符",
            "node_type": "当前节点类型 (master/worker)",
            "worker_concurrency": "单个 Worker 节点的并发任务数",
            "heartbeat_interval": "节点心跳上报间隔 (秒)",
            "max_node_auto_retries": "节点异常自动重启最大尝试次数",
            "max_retries": "任务失败最大重试次数",
            "retry_delay": "任务重试延迟时间 (秒)",
            "llm_api_base": "大语言模型 API 基础地址",
            "llm_api_key": "大语言模型 API 密钥",
            "llm_model": "大语言模型模型名称",
            "oss_enabled": "是否启用 OSS 存储 (开启后可选将 HTML 和截图存至 OSS)",
            "oss_endpoint": "OSS 访问域名 (如 oss-cn-hangzhou.aliyuncs.com)",
            "oss_access_key_id": "OSS AccessKey ID",
            "oss_access_key_secret": "OSS AccessKey Secret",
            "oss_bucket_name": "OSS Bucket 名称",
            "oss_bucket_domain": "OSS 自定义域名或默认域名 (用于生成访问 URL)",
            "log_level": "系统日志打印级别 (DEBUG, INFO, WARNING, ERROR)",
            "log_file": "系统日志文件保存路径",
            "secret_key": "系统安全密钥，用于 Token 签名等",
            "algorithm": "Token 签名加密算法",
            "access_token_expire_minutes": "Token 有效期时长 (分钟)"
        }
        
        description = descriptions.get(key, f"系统配置项: {key}")

        if not existing:
            # 写入数据库
            sqlite_db.set_config(key, value, description)
            logger.info(f"已导入配置: {key} = {value}")
            count += 1
        else:
            # 即使存在，我们也更新一下描述，确保 OSS 相关的描述被写入
            sqlite_db.set_config(key, value, description)
            logger.info(f"更新配置: {key}")
            count += 1
            
    logger.info(f"初始化完成，共导入 {count} 条配置。")

if __name__ == "__main__":
    init_configs()
