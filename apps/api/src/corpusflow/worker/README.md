# Worker 边界

Celery 已锁定依赖；P0-D 才注册任务、建立 Outbox、幂等与恢复。P0-A 不启动空 Worker、不返回假任务 ID。
