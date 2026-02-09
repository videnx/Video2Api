#!/usr/bin/env python3
"""
数据库初始化脚本

连接到数据库并创建必要的索引
"""
import os
import sys
# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.mongo import mongo
from app.db.redis import redis_client
from app.core.config import settings

if __name__ == "__main__":
    print("Initializing database...")

    # 连接到 MongoDB 和 Redis
    print(f"Connecting to MongoDB with URI: {settings.mongo_uri}")
    print(f"Connecting to Redis (Queue) with URL: {settings.redis_url}")
    print(f"Connecting to Redis (Cache) with URL: {settings.redis_cache_url}")
    print(f"Connecting to RabbitMQ with URL: {settings.rabbitmq_url}")
    mongo.connect()
    redis_client.connect_cache()
    redis_client.connect_queue()

    print(f"Connected to MongoDB: {settings.mongo_uri}")
    print(f"Connected to Redis: {settings.redis_url}")

    # 创建索引的辅助函数
    def create_safe_index(collection, *args, **kwargs):
        try:
            collection.create_index(*args, **kwargs)
            # 获取索引名称用于显示
            index_name = kwargs.get('name') or args[0]
            print(f"Index created: {collection.name}.{index_name}")
        except Exception as e:
            # 如果是权限错误 (Code 13)，则跳过并警告
            if hasattr(e, 'code') and e.code == 13:
                print(f"Warning: Not authorized to create index on '{collection.name}'. Please ensure the DB user has 'createIndex' permission.")
            else:
                print(f"Error creating index on '{collection.name}': {e}")

    # 创建 tasks 集合索引
    create_safe_index(mongo.tasks, "task_id", unique=True)
    create_safe_index(mongo.tasks, "status")
    create_safe_index(mongo.tasks, "created_at")
    create_safe_index(mongo.tasks, "cache_key")

    # 创建 task_stats 集合索引
    create_safe_index(mongo.task_stats, "date", unique=True)

    # 创建 configs 集合索引
    create_safe_index(mongo.configs, "key", unique=True)

    # 创建 nodes 集合索引
    create_safe_index(mongo.nodes, "node_id", unique=True)

    # 创建 parsing_rules 集合索引
    try:
        mongo.parsing_rules.drop_indexes()
    except Exception:
        pass
    create_safe_index(mongo.parsing_rules, "domain", unique=True)

    print("Database indexes created successfully!")

    # 关闭数据库连接
    mongo.close()
    redis_client.close_all()

    print("Database initialization completed!")
