---
kind: api-contract
scope: api-extensions-and-actions
status: draft
origin: generated
source_paths: [cinder/api/contrib/volume_actions.py, cinder/api/contrib/admin_actions.py, cinder/api/contrib/snapshot_actions.py, cinder/api/contrib/snapshot_unmanage.py, cinder/api/contrib/volume_unmanage.py, cinder/api/contrib/types_manage.py, cinder/api/contrib/volume_image_metadata.py, cinder/api/contrib/volume_type_access.py, cinder/api/v3/volumes.py, cinder/api/v3/attachments.py, cinder/api/v3/groups.py, cinder/api/v3/group_snapshots.py]
symbols: [VolumeActions.get_controller_extensions, Admin_actions.get_controller_extensions, VolumeActionsController._attach, GroupsController.reset_status, AttachmentsController.complete]
upstream: [contracts/api-reference.md]
downstream: [contracts/api/v3-volumes.md, contracts/api/v3-other.md, contracts/error-codes.md]
---

# 扩展 Action 逐条清单（cinder/api/contrib 全集）

本页逐条列出 `cinder/api/contrib/*` 全部 `ExtensionDescriptor` 以及它们注入的 Action，**不使用「其余类似」省略**。全仓 Action 共 40 个：contrib 注入 30 个（下表第 3 节）、v3 控制器内置 10 个（第 4 节）。Action 经 `mapper` 的 `member={'action':'POST'}` 进入 `Controller._action`，由 `@wsgi.action('字面量')` 分发；鉴权键来自 `etc/cinder/policy.json`，错误语义见 [错误码字典](../error-codes.md)，路由归属见 [入向接口总表](../api-reference.md)。

## 1. 扩展框架与分发机制

| 环节 | 实现 | 源码锚点（`路径:行号`） |
|---|---|---|
| 扩展描述 | 每个文件定义一个继承 `extensions.ExtensionDescriptor` 的类，声明 `name`/`alias`/`updated`（如 `Volume_actions`） | `cinder/api/contrib/volume_actions.py:397-407` |
| 控制器扩展 | `get_controller_extensions()` 返回 `extensions.ControllerExtension(self, 'volumes', controller)` | `cinder/api/contrib/volume_actions.py:404-407` |
| 资源扩展 | `get_resources()` 返回 `extensions.ResourceExtension(alias, controller)` 注入顶层资源 | `cinder/api/contrib/backups.py:268-276`、`cinder/api/contrib/services.py:291-294` |
| Action 分发 | 用 `@wsgi.action` 装饰方法并传入源码中的 action 字面量（如 `os-attach`），`member={'action':'POST'}` 触发控制器 `_action` | `cinder/api/v3/router.py:58-62`、`cinder/api/contrib/volume_actions.py:57-58` |
| 扩展鉴权 | `authorize(context, action_name)` 拼 `volume_actions:%s` 交 `extension_authorizer` | `cinder/api/contrib/volume_actions.py:38-40` |

```text
POST /{project_id}/volumes/{id}/action -> VolumeActionsController._action
  ├─ [body 键 "os-attach"] cinder/api/contrib/volume_actions.py:57-105 _attach -> volume_api.attach (202)
  ├─ [body 键 "os-extend"] cinder/api/contrib/volume_actions.py:308-329 _extend -> extend/extend_attached_volume (202)
  └─ [body 键 "os-retype"] cinder/api/contrib/volume_actions.py:355-368 _retype -> volume_api.retype (202)
POST /{project_id}/volumes/{id}/action -> VolumeAdminController (os-admin-actions 注入)
  └─ [body 键 "os-migrate_volume"] cinder/api/contrib/admin_actions.py:239-253 _migrate_volume
```

## 2. 33 个 ExtensionDescriptor 全集

| 文件（`路径:行号`） | 类名 | alias | 贡献形态 |
|---|---|---|---|
| `cinder/api/contrib/admin_actions.py:333` | `Admin_actions` | `os-admin-actions` | 控制器扩展（volumes/snapshots/backups） |
| `cinder/api/contrib/availability_zones.py:37` | `Availability_zones` | `os-availability-zone` | 顶层资源 |
| `cinder/api/contrib/backups.py:261` | `Backups` | `backups` | 顶层资源 |
| `cinder/api/contrib/capabilities.py:61` | `Capabilities` | `capabilities` | 顶层资源 |
| `cinder/api/contrib/cgsnapshots.py:152` | `Cgsnapshots` | `cgsnapshots` | 顶层资源 |
| `cinder/api/contrib/consistencygroups.py:293` | `Consistencygroups` | `consistencygroups` | 顶层资源 |
| `cinder/api/contrib/extended_services.py:18` | `Extended_services` | `os-extended-services` | 服务视图属性扩展 |
| `cinder/api/contrib/extended_snapshot_attributes.py:50` | `Extended_snapshot_attributes` | `os-extended-snapshot-attributes` | 快照视图属性扩展 |
| `cinder/api/contrib/hosts.py:191` | `Hosts` | `os-hosts` | 顶层资源 |
| `cinder/api/contrib/image_create.py:23` | `Image_create` | `os-image-create` | 卷创建扩展（imageRef 解析） |
| `cinder/api/contrib/qos_specs_manage.py:382` | `Qos_specs_manage` | `qos-specs` | 顶层资源 |
| `cinder/api/contrib/quota_classes.py:86` | `Quota_classes` | `os-quota-class-sets` | 顶层资源 |
| `cinder/api/contrib/quotas.py:455` | `Quotas` | `os-quota-sets` | 顶层资源 |
| `cinder/api/contrib/scheduler_hints.py:47` | `Scheduler_hints` | `OS-SCH-HNT` | 请求体扩展 |
| `cinder/api/contrib/scheduler_stats.py:71` | `Scheduler_stats` | `scheduler-stats` | 顶层资源 |
| `cinder/api/contrib/services.py:284` | `Services` | `os-services` | 顶层资源 |
| `cinder/api/contrib/snapshot_actions.py:105` | `Snapshot_actions` | `os-snapshot-actions` | 控制器扩展（snapshots） |
| `cinder/api/contrib/snapshot_manage.py:148` | `Snapshot_manage` | `os-snapshot-manage` | 顶层资源 |
| `cinder/api/contrib/snapshot_unmanage.py:63` | `Snapshot_unmanage` | `os-snapshot-unmanage` | 控制器扩展（snapshots） |
| `cinder/api/contrib/types_extra_specs.py:189` | `Types_extra_specs` | `os-types-extra-specs` | 顶层资源（extra_specs） |
| `cinder/api/contrib/types_manage.py:188` | `Types_manage` | `os-types-manage` | 控制器扩展（types） |
| `cinder/api/contrib/used_limits.py:59` | `Used_limits` | `os-used-limits` | limits 视图扩展 |
| `cinder/api/contrib/volume_actions.py:397` | `Volume_actions` | `os-volume-actions` | 控制器扩展（volumes） |
| `cinder/api/contrib/volume_encryption_metadata.py:44` | `Volume_encryption_metadata` | `os-volume-encryption-metadata` | 顶层资源 |
| `cinder/api/contrib/volume_host_attribute.py:44` | `Volume_host_attribute` | `os-vol-host-attr` | 卷视图属性扩展 |
| `cinder/api/contrib/volume_image_metadata.py:155` | `Volume_image_metadata` | `os-vol-image-meta` | 控制器扩展（volumes） |
| `cinder/api/contrib/volume_manage.py:171` | `Volume_manage` | `os-volume-manage` | 顶层资源 |
| `cinder/api/contrib/volume_mig_status_attribute.py:44` | `Volume_mig_status_attribute` | `os-vol-mig-status-attr` | 卷视图属性扩展 |
| `cinder/api/contrib/volume_tenant_attribute.py:44` | `Volume_tenant_attribute` | `os-vol-tenant-attr` | 卷视图属性扩展 |
| `cinder/api/contrib/volume_transfer.py:154` | `Volume_transfer` | `os-volume-transfer` | 顶层资源 |
| `cinder/api/contrib/volume_type_access.py:136` | `Volume_type_access` | `os-volume-type-access` | 顶层资源 + 控制器扩展 |
| `cinder/api/contrib/volume_type_encryption.py:174` | `Volume_type_encryption` | `encryption` | 顶层资源 |
| `cinder/api/contrib/volume_unmanage.py:60` | `Volume_unmanage` | `os-volume-unmanage` | 控制器扩展（volumes） |

另有 2 个无 `ExtensionDescriptor` 的辅助文件：`cinder/api/contrib/__init__.py` 与 `cinder/api/contrib/resource_common_manage.py`（提供 manage 公共基类，被 `volume_manage`/`snapshot_manage` 复用）。

## 3. contrib 注入的 30 个 Action 逐条清单

### 3.1 `os-volume-actions`（`cinder/api/contrib/volume_actions.py`）

| Action 字面量 | 方法（`路径:行号`） | 必填 body 字段 | 可选字段 / 默认值 | 响应 |
|---|---|---|---|---|
| `os-attach` | `_attach` (`cinder/api/contrib/volume_actions.py:57-105`) | `mountpoint` | `instance_uuid`、`host_name`（二者至少其一）、`mode` 默认 `rw`（枚举 `rw\|ro`） | 202 |
| `os-detach` | `_detach` (`cinder/api/contrib/volume_actions.py:107-132`) | 无 | `attachment_id` | 202 |
| `os-reserve` | `_reserve` (`cinder/api/contrib/volume_actions.py:134-142`) | 无 | 无 | 202 |
| `os-unreserve` | `_unreserve` (`cinder/api/contrib/volume_actions.py:144-152`) | 无 | 无 | 202 |
| `os-begin_detaching` | `_begin_detaching` (`cinder/api/contrib/volume_actions.py:154-162`) | 无 | 无 | 202 |
| `os-roll_detaching` | `_roll_detaching` (`cinder/api/contrib/volume_actions.py:164-172`) | 无 | 无 | 202 |
| `os-initialize_connection` | `_initialize_connection` (`cinder/api/contrib/volume_actions.py:174-200`) | `connector` | 无 | `{"connection_info": ...}` |
| `os-terminate_connection` | `_terminate_connection` (`cinder/api/contrib/volume_actions.py:202-218`) | `connector` | 无 | 202 |
| `os-volume_upload_image` | `_volume_upload_image` (`cinder/api/contrib/volume_actions.py:220-306`) | `image_name` | `force` 默认 `False`、`disk_format` 默认 `raw`（`parallels`→`ploop`）、`container_format` 默认 `bare`、3.1+ `visibility` 默认 `private`、`protected` 默认 `False` | 202 |
| `os-extend` | `_extend` (`cinder/api/contrib/volume_actions.py:308-329`) | `new_size`（int） | 3.42+ 且 in-use 时走 `extend_attached_volume` | 202 |
| `os-update_readonly_flag` | `_volume_readonly_update` (`cinder/api/contrib/volume_actions.py:331-353`) | `readonly`（bool） | 无 | 202 |
| `os-retype` | `_retype` (`cinder/api/contrib/volume_actions.py:355-368`) | `new_type` | `migration_policy` | 202 |
| `os-set_bootable` | `_set_bootable` (`cinder/api/contrib/volume_actions.py:370-394`) | `bootable`（bool） | 无 | 200 |

### 3.2 `os-admin-actions`（`cinder/api/contrib/admin_actions.py`）

| Action 字面量 | 方法（`路径:行号`） | 必填 body 字段 | 可选字段 / 约束 | 响应 |
|---|---|---|---|---|
| `os-reset_status`（volumes/snapshots 基类） | `_reset_status` (`cinder/api/contrib/admin_actions.py:94-127`) | `status` | `valid_status` 集合校验；volume 另接受 `attach_status`/`migration_status` (`cinder/api/contrib/admin_actions.py:168-199`) | 202 |
| `os-force_delete` | `_force_delete` (`cinder/api/contrib/admin_actions.py:129-137`) | 无 | 绕过 available 检查 | 202 |
| `os-force_detach` | `_force_detach` (`cinder/api/contrib/admin_actions.py:201-237`) | 无 | `connector`、`attachment_id` | 202 |
| `os-migrate_volume` | `_migrate_volume` (`cinder/api/contrib/admin_actions.py:239-253`) | 无 | `host`/`cluster_name`(3.16+)、`force_host_copy`、`lock_volume` | 202 |
| `os-migrate_volume_completion` | `_migrate_volume_completion` (`cinder/api/contrib/admin_actions.py:255-273`) | `new_volume` | `error` 默认 False | `{"save_volume_id": ...}` |
| `os-reset_status`（backups 覆写） | `_reset_status` (`cinder/api/contrib/admin_actions.py:312-330`) | `status` | `valid_status` = `{available, error}` (`cinder/api/contrib/admin_actions.py:302-304`) | 202 |

### 3.3 其余 contrib Action（11 条）

| Action 字面量 | 方法（`路径:行号`） | 必填 body 字段 | 可选字段 / 约束 | 响应 |
|---|---|---|---|---|
| `os-update_snapshot_status` | `_update_snapshot_status` (`cinder/api/contrib/snapshot_actions.py:38-102`) | `status` | `progress`（形如 `73%`，0–100）；状态迁移白名单 `creating→creating/available/error`、`deleting→deleting/error_deleting` | 202 |
| `os-unmanage`（volume） | `unmanage` (`cinder/api/contrib/volume_unmanage.py:32-57`) | 无 | 调 `delete(unmanage_only=True)`；仍挂载→400 | 202 |
| `os-unmanage`（snapshot） | `unmanage` (`cinder/api/contrib/snapshot_unmanage.py:34-60`) | 无 | `InvalidSnapshot`→400 | 202 |
| `create`（types） | `_create` (`cinder/api/contrib/types_manage.py:52-100`) | `name`（非空，1–255） | `description`(0–255)、`extra_specs`、`is_public` 默认 True；重名→409 | 卷类型视图 |
| `update`（types） | `_update` (`cinder/api/contrib/types_manage.py:102-161`) | `name`/`description`/`is_public` 至少其一 | 各字段长度校验；`VolumeTypeExists`→409，`VolumeTypeUpdateFailed`→500 | 卷类型视图 |
| `delete`（types） | `_delete` (`cinder/api/contrib/types_manage.py:163-183`) | 无 | `VolumeTypeInUse`→400 | 202 |
| `os-set_image_metadata` | `create` (`cinder/api/contrib/volume_image_metadata.py:87-101`) | `metadata` | `InvalidVolumeMetadataSize`→413 | `{"metadata": ...}` |
| `os-show_image_metadata` | `index` (`cinder/api/contrib/volume_image_metadata.py:124-127`) | 无 | 无 | `{"metadata": ...}` |
| `os-unset_image_metadata` | `delete` (`cinder/api/contrib/volume_image_metadata.py:129-152`) | `key` | `key` 为空→400；不存在→`GlanceMetadataNotFound` | 200 |
| `addProjectAccess` | `_addProjectAccess` (`cinder/api/contrib/volume_type_access.py:110-122`) | `project` | 已存在→409 | 202 |
| `removeProjectAccess` | `_removeProjectAccess` (`cinder/api/contrib/volume_type_access.py:124-133`) | `project` | 无 | 202 |

## 4. v3 控制器内置 10 个 Action

| Action 字面量 | 资源 | 方法（`路径:行号`） | 必填 body / 参数 | 响应 |
|---|---|---|---|---|
| `revert` | volumes | `revert` (`cinder/api/v3/volumes.py:165-194`) | `revert.snapshot_id` 须等于最新快照 | 202 |
| `os-complete` | attachments | `complete` (`cinder/api/v3/attachments.py:270-284`) | 无 | 202 |
| `reset_status` | groups | `reset_status` (`cinder/api/v3/groups.py:71-110`) | `reset_status.status` | 202 |
| `delete` | groups | `delete_group` (`cinder/api/v3/groups.py:112-151`) | `delete.delete-volumes`(bool) | 202 |
| `create-from-src` | groups | `create_from_src` (`cinder/api/v3/groups.py:246-309`) | `group_snapshot_id` 或 `source_group_id` 二选一 | 202 |
| `enable_replication` | groups | `enable_replication` (`cinder/api/v3/groups.py:376-399`) | 复制参数 | 依实现 |
| `disable_replication` | groups | `disable_replication` (`cinder/api/v3/groups.py:400-423`) | 复制参数 | 依实现 |
| `failover_replication` | groups | `failover_replication` (`cinder/api/v3/groups.py:424-459`) | 复制参数 | 依实现 |
| `list_replication_targets` | groups | `list_replication_targets` (`cinder/api/v3/groups.py:460-481`) | 无 | 目标列表 |
| `reset_status` | group_snapshots | `reset_status` (`cinder/api/v3/group_snapshots.py:186-227`) | `reset_status.status` | 202 |

## 5. 共变耦合与修改清单

| 变更点 | 联动文件 | 隐式陷阱与标准动作 |
|---|---|---|
| 改 Action 字面量 | `cinder/api/contrib/*.py`、`etc/cinder/policy.json`、`cinder/api/v3/router.py:58-62` | `@wsgi.action` 字符串同时是 body 外层键与 policy 键的一部分；改名须同步策略与客户端 |
| 改 `os-admin-actions` 注入集合 | `cinder/api/contrib/admin_actions.py:340-348` | 同一 `os-reset_status` 被 volumes/snapshots 基类与 backups 覆写共用，调整注入列表会改变生效 controller |
| 改扩展加载 | `cinder/common/config.py:99-106`、`etc/cinder/api-paste.ini:12-28` | `osapi_volume_extension` 默认 `cinder.api.contrib.standard_extensions`，未列入的扩展不会注册，Action 静默消失 |
| 改状态白名单 | `cinder/api/contrib/admin_actions.py:45-51`、`151-157`、`302-304` | 基类与子类 `valid_status` 各自维护，遗漏合法状态会导致 400 |
| 改上传镜像字段 | `cinder/api/contrib/volume_actions.py:244-289`、`cinder/image/glance.py:578-611` | `visibility`/`is_public` 随 Glance 版本互换；改字段须同步下游翻译，见 [错误码字典](../error-codes.md) |

核心资源参数见 [v3 核心资源参数字典](v3-volumes.md)；其余资源参数见 [v3 其余资源与 v1/v2](v3-other.md)。
