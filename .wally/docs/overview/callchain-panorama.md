---
kind: panorama
scope: callchain-panorama
status: draft
origin: generated
source_paths: [cinder/api/v3/volumes.py, cinder/volume/api.py, cinder/volume/flows/api/create_volume.py, cinder/scheduler/rpcapi.py, cinder/scheduler/manager.py, cinder/scheduler/flows/create_volume.py, cinder/scheduler/filter_scheduler.py, cinder/volume/rpcapi.py, cinder/volume/manager.py, cinder/volume/flows/manager/create_volume.py, cinder/backup/rpcapi.py, cinder/backup/manager.py]
symbols: [VolumeController.create, API.create, ExtractVolumeRequestTask.execute, VolumeCastTask._cast_create_volume, SchedulerAPI.create_volume, SchedulerManager.create_volume, ScheduleCreateVolumeTask.execute, FilterScheduler._schedule, VolumeManager.create_volume, BackupManager.create_backup]
upstream: [INDEX.md]
downstream: [integrations/topology-and-mapping.md, contracts/error-codes.md]
---

# 主干调用链全景

Cinder 的关键执行流跨越 REST 进程、调度进程与卷/备份进程，静态 Grep 在 RPC `cast/call`、Taskflow 任务图与事件回调处会断链。本页固化四条主干链路：`CC-01` 同步 REST 建卷、`CC-02` 异步调度后驱动落盘、`CC-03` 备份创建、`CC-04` 周期能力上报，供 Agent 直接按符号跳转。

## 1. 主干链路索引

| 链路 ID | 链路名称 | 模式 | 起点符号（`路径:行号`） | 终点落点（存储 / 下游 / 产物） | 对应业务页 |
|---|---|---|---|---|---|
| `CC-01` | REST 建卷 API 编排 | 同步请求 | `VolumeController.create` (`cinder/api/v3/volumes.py:197`) | Taskflow 图执行 + `volumes` 行 | [卷生命周期](../business/volume-lifecycle.md) |
| `CC-02` | 调度选后端与卷落盘 | 异步 RPC + 任务图 | `SchedulerAPI.create_volume` (`cinder/scheduler/rpcapi.py:94`) | `VolumeManager.create_volume` → 驱动 | [调度流程](../business/scheduling.md) |
| `CC-03` | 备份创建 | 异步 RPC + brick | `BackupAPI.create_backup` (`cinder/backup/rpcapi.py:56`) | Swift/Ceph 对象 + `backups` 行 | [备份恢复](../business/backup-restore.md) |
| `CC-04` | 后端能力上报 | 周期任务 | `_report_driver_status` (`cinder/volume/manager.py:2343`) | `SchedulerManager.update_service_capabilities` (`cinder/scheduler/manager.py:108`) | [调度流程](../business/scheduling.md) |

---

## 2. 符号级条件调用树（Hop-by-Hop Symbolic Traces）

### `CC-01`：REST 建卷 API 编排

```text
POST /v3/{project_id}/volumes -> cinder/api/v3/volumes.py:197 VolumeController.create(req, body)
  ├─ [guard: body] :205 assert_valid_body(body, 'volume')
  ├─ [guard: 微版本 <= 3.12] :212-225 剥离 group_id，否则 HTTP 400
  ├─ [transform] :240-249 name→display_name、description→display_description、image_id→imageRef
  ├─ [transform] :259-290 snapshot_id/source_volid/consistencygroup_id 必须是 UUID，取 OVO
  ├─ [outbound] cinder/volume/api.py:218 API.create(context, size, ...)
  │    ├─ [guard: 准入] :226 check_policy('create'|'create_from_image')
  │    ├─ [guard: 已废弃] :229-233 source_replica -> InvalidInput
  │    ├─ [guard: 阈值] :244-249 size 非整数或 <= 0 -> InvalidInput
  │    ├─ [guard: 类型兼容] :251-294 组/源卷/快照的 volume_type 必须兼容
  │    ├─ [transform] :306-326 组装 create_what 字典（18 个 Key）
  │    └─ [engine] :336-352 create_volume.get_flow(...).run() -> vref
  └─ [return] :353-361 flow_engine.storage.fetch('volume') -> Volume 视图
```

### `CC-02`：调度选后端与卷落盘

```text
VolumeCastTask._cast_create_volume (cinder/volume/flows/api/create_volume.py:730-789)
  ├─ [outbound RPC] SchedulerAPI.create_volume (cinder/scheduler/rpcapi.py:94-101)
  │    └─ cctxt.cast(SCHEDULER_TOPIC, snapshot_id, image_id, request_spec, filter_properties, volume)
  │         -> SchedulerManager.create_volume (cinder/scheduler/manager.py:175-193)
  │              └─ cinder/scheduler/flows/create_volume.py:141 get_flow().run()
  │                   ├─ ExtractSchedulerSpecTask.execute (:64-73) 填充 request_spec
  │                   └─ ScheduleCreateVolumeTask.execute (:119-139)
  │                        └─ FilterScheduler._schedule (cinder/scheduler/filter_scheduler.py:507-546)
  │                             ├─ _get_weighted_candidates (:269-334) -> 过滤 + 权重
  │                             ├─ [if group_backend] :512-519 剔除不属于该组的后端
  │                             └─ _choose_top_backend (:540-546) -> consume_from_volume
  └─ [outbound RPC] VolumeAPI.create_volume (cinder/volume/rpcapi.py)
       -> VolumeManager.create_volume (cinder/volume/manager.py:583-670)
            ├─ [lock] :624-650 COORDINATOR.get_lock(源标识加 -delete_ 后缀)（仅快照/源卷场景）
            └─ [engine] :602-615 cinder/volume/flows/manager/create_volume.py get_flow().run()
                 ├─ [if 失败] OnFailureRescheduleTask -> 重新投递 cinder-scheduler
                 └─ [finally] :651-667 未重调度则 _update_allocated_capacity
```

### `CC-03`：备份创建

```text
BackupAPI.create_backup (cinder/backup/rpcapi.py:56-59) cctxt.cast(BACKUP_TOPIC, backup=backup)
  -> BackupManager.create_backup (cinder/backup/manager.py:279-424)
       ├─ [guard: 源状态] :308-340 volume/snapshot.status != 'backing-up' -> InvalidVolume/InvalidSnapshot/InvalidBackup
       ├─ [guard: 服务可用] :343-346 not is_working() -> InvalidBackup
       ├─ [outbound] _run_backup (:385-424)
       │    ├─ volume_rpcapi.get_backup_device -> 临时卷或快照
       │    ├─ _attach_device -> brick connection_info 的 device.path
       │    └─ backup_service.backup(backup, device_file) -> Swift/Ceph/NFS 驱动
       ├─ [rollback] :348-358 异常时恢复 volume.previous_status 并 _update_backup_error
       └─ [commit] :360-383 恢复源状态，backup.status=available，父备份 num_dependent_backups += 1
```

### `CC-04`：后端能力上报

```text
VolumeManager._report_driver_status (cinder/volume/manager.py:2343-2413)
  ├─ driver.get_volume_stats(refresh=True) -> 能力字典
  ├─ _append_filter_goodness_functions (:2442-2456) -> filter 与 goodness 函数路径
  └─ publish_service_capabilities (:2457)
       -> SchedulerAPI.notify_service_capabilities -> SchedulerManager.update_service_capabilities
            (cinder/scheduler/manager.py:108-126) -> HostManager 更新 BackendState
```

---

## 3. 跨线程 / 队列 / 子进程 / 协议桥接表（Static-Jump Bridges）

| 投递方符号（`路径:行号`） | 桥接机制 | 实际接收执行入口（`路径:行号`） | 载荷结构 |
|---|---|---|---|
| `cctxt.cast` in `cinder/scheduler/rpcapi.py:101` | oslo.messaging `SCHEDULER_TOPIC` | `cinder/scheduler/manager.py:175` | `request_spec` + `filter_properties` + `volume` OVO |
| `cctxt.cast` in `cinder/volume/rpcapi.py` | oslo.messaging `VOLUME_TOPIC` / `VOLUME_TOPIC.host` | `cinder/volume/manager.py:583` | `volume` OVO + `request_spec` |
| `cctxt.cast` in `cinder/backup/rpcapi.py:59` | oslo.messaging `BACKUP_TOPIC`，server 定向到 `backup.host` | `cinder/backup/manager.py:279` | `backup` OVO |
| `flow_engine.run()` (`cinder/volume/api.py:352`) | Taskflow 任务图 + `flow_utils.DynamicLogListener` | `cinder/volume/flows/api/create_volume.py:818` `get_flow` 注册的各 Task.execute | `create_what` 字典 + `flow_engine.storage` |
| `@periodic_task` (`cinder/manager.py:77`) | eventlet 周期协程 | `cinder/volume/manager.py:2343`、`cinder/scheduler/manager.py:100-126` | 无入参，直接读 DB/驱动状态 |
| `priv_context.init` (`cinder/cmd/volume.py:77`) | oslo.privsep 子进程提权 | `cinder/utils.py:459` `get_root_helper` → rootwrap | 固定 argv，禁 `shell=True` |

## 4. 共变耦合与修改清单（Co-Change Playbook）

1. 修改 `create_what` 字典键：同步 [字段映射矩阵](../integrations/topology-and-mapping.md)、Taskflow `ExtractVolumeRequestTask.execute` (`cinder/volume/flows/api/create_volume.py:416-499`) 与 `cinder/tests/unit/volume/flows/` 的断言。
2. 修改 RPC 方法签名：必须同时更新 `cinder/volume/rpcapi.py` / `cinder/scheduler/rpcapi.py` / `cinder/backup/rpcapi.py` 三侧的 `msg_args` 与对应 Manager 方法，并推进 `RPC_API_VERSION`（见 [RPC 下游契约](../integrations/downstream/rpc-messaging.md)）。
3. 新增周期任务：在 `cinder/manager.py:77` 的 `PeriodicTasks` 中声明，按 [配置手册](../contracts/configuration.md) 注册间隔配置键，并补 [排障 Runbook](../operations/runbook-and-observability.md) 的诊断信号。
