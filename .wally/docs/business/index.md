---
kind: workflow
scope: business-index
status: draft
origin: generated
source_paths: [cinder/volume/api.py, cinder/scheduler/filter_scheduler.py, cinder/backup/api.py, cinder/quota.py, cinder/volume/manager.py, cinder/group/api.py, cinder/message/defined_messages.py, cinder/objects/fields.py, cinder/api/v3/router.py]
symbols: [API.create, FilterScheduler._schedule, BackupAPI.create, QuotaEngine.reserve, VolumeManager.create_group, EventIds]
upstream: [INDEX.md, overview/business-architecture.md]
downstream: [business/domain-models/index.md, contracts/api-reference.md]
---

# 业务能力与核心流程总清单

本页全量归档 Cinder 的对外业务用例与后台自动化闭环流程（`WF-*`），建立「业务场景 ↔ 触发入口 ↔ 下游扇出 ↔ 数据模型」索引；每个流程的执行细节、精确条件与状态机见对应专页。

## 1. 全量业务流程路由总表（Complete Workflow Inventory）

| 流程 ID | 业务域 | 流程名称 | 触发入口（路由 / 定时器 / 命令 + `路径:行号`） | 串联模块与外部下游链 | 变更的核心实体/状态 | 专页路径 |
|---|---|---|---|---|---|---|
| `WF-01` | 卷生命周期 | 卷创建 | `POST /v3/{project_id}/volumes` (`cinder/api/v3/volumes.py:197`) | API → Taskflow → Scheduler RPC → Volume RPC → Driver → DB | `Volume: creating→available/error` | [volume-lifecycle](volume-lifecycle.md) |
| `WF-01b` | 卷生命周期 | 卷删除 | `DELETE /v3/{project_id}/volumes/{id}` (`cinder/api/v3/volumes.py:59`) | API → Volume RPC → `VolumeManager.delete_volume` (`cinder/volume/manager.py:685`) | `Volume: deleting→deleted/error_deleting` | [volume-lifecycle](volume-lifecycle.md) |
| `WF-01c` | 卷生命周期 | 挂载与连接 | `POST /v3/{project_id}/volumes/{id}/action` (`cinder/api/contrib/volume_actions.py:43`) | API → Volume RPC → `initialize_connection` (`cinder/volume/manager.py:1592`) → Nova | `VolumeAttachment: reserved→attaching→attached` | [volume-lifecycle](volume-lifecycle.md) |
| `WF-01d` | 卷生命周期 | 扩容 / retype / 迁移 | `cinder/volume/api.py:1401,1551,1412` | API → Scheduler RPC → Volume RPC → Driver | `Volume: extending/retyping/migrating` | [volume-lifecycle](volume-lifecycle.md) |
| `WF-02` | 调度 | 后端筛选与重调度 | `SchedulerAPI.create_volume` (`cinder/scheduler/rpcapi.py:94`) | SchedulerManager → `FilterScheduler._schedule` (`cinder/scheduler/filter_scheduler.py:507`) → HostManager | `RequestSpec`、`BackendState.consume_from_volume` | [scheduling](scheduling.md) |
| `WF-03` | 备份恢复 | 备份创建 / 恢复 / 删除 | `cinder/api/contrib/backups.py:36` | `BackupAPI.create` (`cinder/backup/api.py:68`) → RPC → Manager → brick → Swift/Ceph | `Backup: creating→available→restoring/deleting` | [backup-restore](backup-restore.md) |
| `WF-03b` | 备份恢复 | 备份导入导出 | `cinder/backup/manager.py:612-777` | `export_record` (`call`) / `import_record` (`cast`) | `Backup.service`、`Backup.backup_url` | [backup-restore](backup-restore.md) |
| `WF-04` | 配额 | 预留 / 提交 / 回滚 | Taskflow `QuotaReserveTask` (`cinder/volume/flows/api/create_volume.py:600`) | `QuotaEngine` (`cinder/quota.py:822`) → `DbQuotaDriver` → `quota_usages/reservations` | `reserved → committed / rolled back` | [quotas](quotas.md) |
| `WF-05` | 组与一致性 | 创建组与组快照 | `POST /v3/{project_id}/groups` (`cinder/api/v3/groups.py`) | `GroupAPI` (`cinder/group/api.py:91`) → `VolumeManager.create_group` (`cinder/volume/manager.py:2863`) → 驱动 group 接口 | `Group: creating→available/updating/deleting` | [groups-and-snapshots](groups-and-snapshots.md) |
| `WF-05b` | 组与一致性 | 一致性快照 | `POST /v3/{project_id}/group_snapshots` (`cinder/api/v3/group_snapshots.py`) | `VolumeManager.create_group_snapshot` (`cinder/volume/manager.py:3597`) | `GroupSnapshot: creating→available` | [groups-and-snapshots](groups-and-snapshots.md) |
| `WF-06` | 审计 | 异步错误消息 | `cinder/message/api.py:40`、`cinder/message/defined_messages.py:25` | Manager 异常 → `Message.create` → 调度器清理 | `Message` 过期删除 | [备份恢复](backup-restore.md) |

## 2. 业务域 ↔ 接口组 ↔ 错误码 ↔ 配置键交叉速查

| 业务域 | 入向接口前缀 | 调用的外部下游封装 | 专属错误码 / 降级标识前缀 | 核心控制配置键 |
|---|---|---|---|---|
| 卷生命周期 | `/v3/{project_id}/volumes/*`（见 [API 参考](../contracts/api-reference.md)） | [Glance](../integrations/downstream/glance.md)、[Nova](../integrations/downstream/nova.md)、[存储驱动](../integrations/downstream/storage-drivers.md) | `InvalidInput`、`InvalidVolume`、`VolumeMigrationFailed`（见 [错误码字典](../contracts/error-codes.md)） | `enabled_backends`、`volume_name_template` |
| 调度 | `/v3/{project_id}/scheduler-stats/*` | [RPC 消息](../integrations/downstream/rpc-messaging.md) | `ServiceTooOld`、`NoValidBackend` | `scheduler_max_attempts`、`scheduler_driver` |
| 备份恢复 | `/v3/{project_id}/backups/*` | [Swift 备份](../integrations/downstream/swift-backup.md) | `InvalidBackup`、`SwiftConnectionFailed`、`BackupDriverException` | `backup_driver`、`backup_swift_container` |
| 配额 | `/v3/{project_id}/quotas/*` | [SQLAlchemy](../integrations/downstream/sqlalchemy-db.md) | `OverQuota`、`QuotaError` | `quota_driver`、`use_nested_quota` |
| 组与一致性 | `/v3/{project_id}/groups/*` | [存储驱动](../integrations/downstream/storage-drivers.md) | `InvalidGroup`、`InvalidGroupType` | `group_type` |

## 3. 领域模型与状态字面量索引

| 聚合实体 | 权威表 / 对象 | 状态枚举来源 | 领域模型专页 |
|---|---|---|---|
| `Volume` / `VolumeAttachment` | `volumes` / `volume_attachment`，`cinder/objects/volume.py:52` | `cinder/objects/fields.py:151-166` | [volume](domain-models/volume.md) |
| `Backup` / `Snapshot` / `Group` | `backups` / `snapshots` / `groups`，`cinder/objects/backup.py:33` | `cinder/objects/fields.py:31-166` | [backup](domain-models/backup.md) |
| 全量 ORM 表与 OVO 归属 | `cinder/db/sqlalchemy/models.py:63-919` | `cinder/objects/base.py:157` | [领域模型总览](domain-models/index.md) |

## 4. 共变耦合与修改清单（Co-Change Playbook）

1. 新增流程：在 `cinder/api/v3/router.py:50` 注册路由 → 在 [API 参考](../contracts/api-reference.md) 补全入参字典 → 在 `business/<workflow>.md` 写符号调用树与状态机 → 在 [领域模型总览](domain-models/index.md) 登记实体 → 更新本表 `WF-*` 编号。
2. 改流程状态机：必须同步 `cinder/objects/fields.py` 的枚举 `ALL` 元组与 `cinder/tests/unit/objects/` 的字段校验用例，避免 API 返回未声明状态。
3. 改流程扇出顺序：同步 [主干调用链](../overview/callchain-panorama.md)、[字段映射矩阵](../integrations/topology-and-mapping.md) 与 [构建与单测](../operations/dev-and-test.md) 中对应模块的必跑套件。
