---
kind: panorama
scope: glossary
status: draft
origin: generated
source_paths: [cinder/common/constants.py, cinder/objects/fields.py, cinder/objects/base.py, cinder/db/sqlalchemy/models.py, cinder/quota.py, cinder/volume/volume_types.py, cinder/api/openstack/api_version_request.py]
symbols: [CinderObject, CinderObjectRegistry, Volume, VolumeTypeQuotaEngine, APIVersionRequest, BackupStatus, SnapshotStatus]
upstream: [INDEX.md]
downstream: [business/domain-models/index.md, contracts/api-reference.md]
---

# 领域术语与代码符号精确映射表

本表消除「云硬盘/卷/后端/池/配额」等需求话术与 Cinder 源码类名、ORM 表、状态字面量之间的命名鸿沟；Agent 写需求前应先把自然语言术语落到本表右列的精确符号，再按 `路径:行号` 回读源码。状态字面量的权威来源是 `cinder/objects/fields.py:31-166` 的枚举类，服务名与 RPC Topic 的权威来源是 `cinder/common/constants.py:21-27`。

## 1. 自然语言术语 ↔ 源码符号映射字典

| 需求/业务常见叫法（含别名/缩写） | 精确技术与业务定义 | 源码对应类 / 表 / 字段 / 枚举 | 权威定义位置（`路径:行号`） |
|---|---|---|---|
| 云硬盘 / 磁盘 / 卷 | 可被挂载到虚机的块设备，持久化为 `volumes` 表一行；`name` 不是列而是模板派生属性 | `Volume`、`volumes`、`Volume.name` | `cinder/db/sqlalchemy/models.py:240-312`、`cinder/objects/volume.py:52` |
| 卷类型 / Type / 服务等级 | 带 extra_specs 的策略对象，决定后端筛选与 QoS；改名需走 `volume_types_diff` | `VolumeTypes`、`volume_types`、`VolumeType` | `cinder/db/sqlalchemy/models.py:362-378`、`cinder/volume/volume_types.py:43-99` |
| 后端 / Backend / 存储后端 | `host@backend` 标识的一个 cinder-volume 驱动实例；多后端由 `enabled_backends` 逐段启动 | `Configuration`、`Service.create(host=...)` | `cinder/volume/configuration.py:49-138`、`cinder/cmd/volume.py:84-108` |
| 存储池 / Pool | 后端内部再细分的资源池，调度时表现为 `host@backend#pool` | `PoolState` | `cinder/scheduler/host_manager.py:316` |
| 快照 / Snapshot | 某时刻卷的只读时间点副本，独立 `snapshots` 表 | `Snapshot`、`snapshots`、`SnapshotStatus` | `cinder/db/sqlalchemy/models.py:656-704`、`cinder/objects/fields.py:119-135` |
| 备份 / Backup | 导出到远端备份后端的卷数据副本（区别于快照），`backups` 表 | `Backup`、`backups`、`BackupStatus` | `cinder/db/sqlalchemy/models.py:722-759`、`cinder/objects/fields.py:31-44` |
| 一致性组 / CG / Group | 需要同一时刻快照的卷集合；旧 `consistencygroups` 与新 `groups` 并存 | `ConsistencyGroup`、`Group`、`GroupStatus` | `cinder/db/sqlalchemy/models.py:159-238`、`cinder/objects/fields.py:48-96` |
| 挂载 / attach | 在卷与实例间建立 `volume_attachment` 行并下发 `connection_info` 给 nova | `VolumeAttachment`、`volume_attachment` | `cinder/db/sqlalchemy/models.py:341-360`、`cinder/volume/api.py:728-768` |
| 配额 / Quota | 按项目限制卷数、容量与快照数；预留→提交→回滚三段式 | `Quota`、`quotas`、`QuotaEngine`、`QUOTAS` | `cinder/quota.py:822-1127`、`cinder/db/sqlalchemy/models.py:571-655` |
| 调度 / schedule | 由 cinder-scheduler 过滤+权重选出承载后端，再 cast 给 cinder-volume | `FilterScheduler._schedule`、`SchedulerAPI.create_volume` | `cinder/scheduler/filter_scheduler.py:507-546`、`cinder/scheduler/rpcapi.py:94-101` |
|  RPC 主题 / Topic | 三类服务的消息 Topic，常量值等于二进制名 | `SCHEDULER_TOPIC`、`VOLUME_TOPIC`、`BACKUP_TOPIC` | `cinder/common/constants.py:21-27` |
| 微版本 / microversion | API 请求头 `OpenStack-API-Version` 中的版本，决定字段是否下发 | `APIVersionRequest`、`_MIN_API_VERSION`、`_MAX_API_VERSION` | `cinder/api/openstack/api_version_request.py:116-141` |
| OVO / 对象 | 带版本与字段校验的领域对象，RPC 与 DB 之间传输的载体 | `CinderObject`、`CinderObjectRegistry`、`CinderPersistentObject` | `cinder/objects/base.py:140-240` |
| 驱动 / Driver | 卷或备份后端插件，由 `get_volume_drivers` / `get_backup_drivers` 动态装载 | `VolumeDriver`、`BackupDriver`、`DriverInfo` | `cinder/volume/driver.py:2114-2464`、`cinder/interface/util.py:42-60` |

## 2. 易混概念严格辨析（Disambiguation）

| 概念 A（`源码符号`） | 概念 B（`源码符号`） | 关键差异（粒度 / 读写时机 / 存储位置 / 混用后果） | 对照源码锚点 |
|---|---|---|---|
| 快照 `Snapshot` | 备份 `Backup` | 快照留在同一后端、依赖源卷；备份导出到独立备份驱动（Swift/Ceph/NFS 等）。把备份当快照会误判跨后端恢复能力 | `cinder/volume/manager.py:1001-1058` vs `cinder/backup/manager.py:279-424` |
| 一致性组 `Group` | 旧一致性组 `ConsistencyGroup` | 两套 ORM/对象并存，旧 CG 驱动通过 `_convert_group_to_cg` 适配；不带转换直接调用会写到错误表 | `cinder/db/sqlalchemy/models.py:178-238` vs `cinder/volume/manager.py:3385-3427` |
| 卷状态 `Volume.status` | 挂载状态 `VolumeAttachStatus` | 前者描述卷生命周期，后者描述单个 attachment；`in-use` 卷可存在多个 attachment，`attach_status` 不能替代 `status` | `cinder/db/sqlalchemy/models.py:268-269`、`cinder/objects/fields.py:151-166` |
| 配额 `quota` | 预留 `reservation` + 用量 `quota_usage` | `quotas` 存上限，`reservations` 存未提交增量，`quota_usages` 存 in_use/reserved；只改上限不回滚预留会双重计数 | `cinder/db/sqlalchemy/models.py:571-655`、`cinder/quota.py:331-416` |
| RPC `cast` | RPC `call` | `cast` 异步投递无返回值（创建/删除）；`call` 同步等结果（能力查询、`export_record`）。错用会让接口拿不到必要字段 | `cinder/scheduler/rpcapi.py:94-101` vs `cinder/backup/rpcapi.py:72-78` |
| API 微版本 | RPC API 版本 | 前者面向外部客户端（`api_version_request.py:116-117`），后者面向服务间兼容（`volume/rpcapi.py:138-139`）；两者独立演进 | `cinder/api/openstack/api_version_request.py:116-117` vs `cinder/volume/rpcapi.py:138-139` |

## 3. 代码命名与枚举惯例

- **模块/文件前缀约定**：`cinder/api/v3/*` 为对外 REST 控制器，`cinder/api/contrib/*` 为扩展 Action，`cinder/volume/flows/*` 为 Taskflow 任务图；`cinder/objects/*` 为 OVO；下划线开头函数一律视为内部实现。
- **状态值字面量约定**：`creating` / `available` / `deleting` / `error` 等来自 `BaseCinderEnum` 子类（`cinder/objects/fields.py:25-166`），`BACKING_UP = 'backing-up'`、`FAILOVER_ERROR = 'failover-error'` 带连字符，禁止凭直觉改成下划线。
- **迁移态字面量约定**：`migration_status` 使用 `starting` / `migrating` / `success` / `error` / `target:后接目标卷 UUID`，目标卷专属态由 `cinder/volume/manager.py:2027` 写入，与 `status` 正交。
- **卷名派生约定**：`Volume.name` 由 `CONF.volume_name_template % name_id` 计算（`cinder/db/sqlalchemy/models.py:254-256`），不带 `volume_name_template` 配置变化时不要假设 `name` 等于 UUID。

## 4. 共变耦合与修改清单（Co-Change Playbook）

1. 新增或改名状态字面量：先改 `cinder/objects/fields.py` 对应 `ALL` 元组，再同步 `cinder/api/views/*` 的展示映射与 `cinder/tests/unit/objects/` 字段校验用例，并核对 [领域模型总览](../business/domain-models/index.md) 的状态列。
2. 新增业务术语：在 [领域模型总览](../business/domain-models/index.md) 补实体字段字典，并回到本页第 1 节补一行术语映射，避免 Agent 翻译时落到裸表名；对外字段还需同步 [入向接口参考](../contracts/api-reference.md)。
3. 修改服务名或 Topic：必须同时改 `cinder/common/constants.py:21-27`、`setup.cfg` 的 `console_scripts`、以及 [异步组件](../architecture/async-job-worker.md) 的进程清单；单改常量会导致 RPC 找不到订阅者。
