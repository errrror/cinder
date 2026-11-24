---
kind: api-contract
scope: api-v3-core-resources
status: draft
origin: generated
source_paths: [cinder/api/v3/volumes.py, cinder/api/v2/volumes.py, cinder/api/v3/snapshots.py, cinder/api/v3/attachments.py, cinder/api/v3/messages.py, cinder/api/v3/limits.py, cinder/api/v3/volume_metadata.py]
symbols: [VolumeController.create, VolumeController.delete, VolumeController.summary, VolumeController.revert, AttachmentsController.create, AttachmentsController.complete, MessagesController.index, LimitsController.index]
upstream: [contracts/api-reference.md]
downstream: [contracts/api/v3-other.md, contracts/api/extensions.md, contracts/error-codes.md]
---

# v3 核心资源逐接口参数字典（volumes / snapshots / attachments / messages / limits）

本页展开 [入向接口总表](../api-reference.md) 中 v3 核心资源的每个接口的路径参数、查询参数、请求体字段、响应与错误分支。字段字面均来自控制器源码；微版本门槛以 `@wsgi.Controller.api_version` 与 `req_version.matches(...)` 为准。备份、组、集群、worker 等资源见 [v3 其余资源与 v1/v2](v3-other.md)，`os-*` 动作见 [扩展 Action 全集](extensions.md)，状态码语义见 [错误码字典](../error-codes.md)。

## 1. volume 资源（`/volumes`）

`VolumeController` 继承 v2 实现并覆写关键方法（`cinder/api/v3/volumes.py:50-57`）。

### 1.1 `POST /{project_id}/volumes` — 创建云硬盘

- 编排链：`cinder/api/v3/volumes.py:197-327` (`VolumeController.create`) → `self.volume_api.create(...)` (`cinder/api/v3/volumes.py:319-323`)；成功返回 `_view_builder.detail`，HTTP 202（`@wsgi.response(ACCEPTED)`，`cinder/api/v3/volumes.py:196`）。
- 入参字典（位置 `body.volume`）：

| 字段名 | 类型 | 必填 | 默认值 / 校验约束 | 含义与透传去向 |
|---|---|---|---|---|
| `name` | str | 否 | 校验名称与描述后改写为 `display_name` (`cinder/api/v3/volumes.py:239-241`) | 显示名 |
| `description` | str | 否 | 改写为 `display_description` (`cinder/api/v3/volumes.py:245-246`) | 显示描述 |
| `size` | int | 否 | 无 snapshot/source 时可为 None；从快照取 `volume_size`、从源卷取 `size` (`cinder/api/v3/volumes.py:300-304`) | 容量（GB） |
| `image_id` | UUID | 否 | 改写为 `imageRef`，仅当 `os-image-create` 已加载才解析 (`cinder/api/v3/volumes.py:248-249`、`308-312`) | 从镜像创建 |
| `imageRef` | str | 否 | 同上分支 | 镜像引用 |
| `volume_type` | str | 否 | `get_by_name_or_id` 解析 (`cinder/api/v3/volumes.py:251-255`) | 卷类型 |
| `metadata` | dict | 否 | 直接置入 kwargs (`cinder/api/v3/volumes.py:257`) | 元数据 |
| `snapshot_id` | UUID | 否 | 非 UUID 抛 400 (`cinder/api/v3/volumes.py:259-268`) | 快照源 |
| `source_volid` | UUID | 否 | 非 UUID 抛 400 (`cinder/api/v3/volumes.py:270-281`) | 卷源 |
| `consistencygroup_id` | UUID | 否 | 非 UUID 抛 400，解析为 `group` (`cinder/api/v3/volumes.py:285-292`) | 一致性组 |
| `group_id` | UUID | 否 | 微版本 ≤3.12 时从 body 弹出 (`cinder/api/v3/volumes.py:211-225`、`294-298`) | 组归属 |
| `availability_zone` | str | 否 | 透传 kwargs (`cinder/api/v3/volumes.py:314`) | 可用区 |
| `scheduler_hints` | dict | 否 | 透传 kwargs (`cinder/api/v3/volumes.py:315`) | 调度提示 |
| `multiattach` | bool | 否 | 默认 `False` (`cinder/api/v3/volumes.py:316-317`) | 多挂载 |
| `source_replica` | UUID | 否 | **传入即快速失败** `InvalidInput` (`cinder/api/v3/volumes.py:231-237`) | 已废弃的 replication v1 参数 |

### 1.2 其余 volume 接口

| 接口 | 关键参数 | 行为与错误分支 | 源码锚点 |
|---|---|---|---|
| `GET /{project_id}/volumes` | query: `marker`/`limit`/`offset`（`get_pagination_params`）、`sort_key`/`sort_dir`、`name`(映射为 `display_name`)、通用过滤器 | `get_all` + `summary_list`；`check_volume_filters` 在 3.2+ 严格校验 (`cinder/api/v3/volumes.py:101-141`) | `cinder/api/v3/volumes.py:101-141` |
| `GET /{project_id}/volumes/detail` | 同上 | `detail_list` 详细视图 (`cinder/api/v3/volumes.py:137-138`) | `cinder/api/v3/volumes.py:137-141` |
| `GET /{project_id}/volumes/summary` | query: 通用过滤器；微版本 ≥ `SUMMARY_BASE_MICRO_VERSION` | `get_volume_summary` 返回数量/总量，3.36+ 附带 distinct metadata (`cinder/api/v3/volumes.py:143-163`) | `cinder/api/v3/volumes.py:143-163` |
| `GET /{project_id}/volumes/{id}` | path: `id` | v2 `show` 直接复用 (`cinder/api/v2/volumes.py:54-64`) | `cinder/api/v2/volumes.py:54` |
| `PUT /{project_id}/volumes/{id}` | body: `volume` 字典 | v2 `update` 校验非空 body 与 `volume` 键 (`cinder/api/v2/volumes.py:280-288`) | `cinder/api/v2/volumes.py:280-338` |
| `DELETE /{project_id}/volumes/{id}` | query: `cascade`、3.23+ `force` | `force=True` 需 `force_delete` 策略；返回 202 (`cinder/api/v3/volumes.py:59-86`) | `cinder/api/v3/volumes.py:59-86` |
| `POST /{project_id}/volumes/{id}/action` → `revert` | body: `revert.snapshot_id`（须等于最新快照 id，否则 400；`InvalidVolume/InvalidSnapshot`→409，配额超限→403） | 3.40+，返回 202 (`cinder/api/v3/volumes.py:165-194`) | `cinder/api/v3/volumes.py:165-194` |

### 1.3 volume 元数据子资源

| 接口 | 关键参数 | 行为 | 源码锚点 |
|---|---|---|---|
| `GET /{project_id}/volumes/{volume_id}/metadata` | path: `volume_id` | `index` 返回元数据列表 | `cinder/api/v3/volume_metadata.py:46` |
| `POST /{project_id}/volumes/{volume_id}/metadata` | body: `metadata` | `create` 创建单键 | `cinder/api/v3/volume_metadata.py:34-80` |
| `PUT /{project_id}/volumes/{volume_id}/metadata/{id}` | path: `id` | `update` 更新单键，先 `_validate_etag` | `cinder/api/v3/volume_metadata.py:34-70` |
| `DELETE /{project_id}/volumes/{volume_id}/metadata/{id}` | path: `id` | `delete` 删除单键 | `cinder/api/v3/volume_metadata.py:34-80` |
| `PUT /{project_id}/volumes/{volume_id}/metadata` | body: `metadata` | `update_all` 全量覆盖 | `cinder/api/v3/volume_metadata.py:70-78` |

## 2. snapshot 资源（`/snapshots`）

v3 `SnapshotsController` 继承 v2 并覆写过滤逻辑（`cinder/api/v3/snapshots.py:111` 复用 v2 `create`）。

| 接口 | 关键参数 | 行为与错误分支 | 源码锚点 |
|---|---|---|---|
| `POST /{project_id}/snapshots` | body: `snapshot`：`volume_id`(必填)、`name`→`display_name`、`description`→`display_description`、`force`、`metadata` | v2 `create` 创建快照，返回 202 | `cinder/api/v2/snapshots.py:113-162` |
| `GET /{project_id}/snapshots` | query: `name`/`status`/`volume_id`/`metadata` 等过滤与分页 | `_items` + `summary_list` | `cinder/api/v3/snapshots.py:70-111`、`cinder/api/v2/snapshots.py:78-111` |
| `GET /{project_id}/snapshots/detail` | 同上 | `detail_list` | `cinder/api/v2/snapshots.py:74` |
| `GET /{project_id}/snapshots/{id}` | path: `id` | `show` | `cinder/api/v2/snapshots.py:48` |
| `PUT /{project_id}/snapshots/{id}` | body: `snapshot` | `update` | `cinder/api/v2/snapshots.py:163` |
| `DELETE /{project_id}/snapshots/{id}` | path: `id` | `delete` | `cinder/api/v2/snapshots.py:58` |
| `POST /{project_id}/snapshots/{snapshot_id}/metadata`（含 PUT update_all） | body: `metadata` | 由 v2 `snapshot_metadata` 提供（v3 路由复用，`cinder/api/v3/router.py:126-139`） | `cinder/api/v3/router.py:126-139` |

## 3. attachment 资源（`/attachments`）

`AttachmentsController` 自 3.27 起可用，`os-complete` 自 3.44 起可用（`cinder/api/v3/attachments.py:29-31`）。

| 接口 | 关键参数 | 行为与错误分支 | 源码锚点 |
|---|---|---|---|
| `POST /{project_id}/attachments` | body: `attachment.instance_uuid`(必填，缺失→400)、`attachment.volume_uuid`(必填，缺失→400)、`attachment.connector`(可选) | `attachment_create` 预留或初始化连接，返回 202；`NotAuthorized` 透传，其余异常→500 (`cinder/api/v3/attachments.py:97-193`) | `cinder/api/v3/attachments.py:97-193` |
| `GET /{project_id}/attachments` | query: `volume_id`/`status`/`instance_id`/`attach_status` + 分页排序 | `get_all_by_project`；admin 带 `all_tenants` 时走 `get_all`；`instance_id` 改写为 `instance_uuid` (`cinder/api/v3/attachments.py:71-95`) | `cinder/api/v3/attachments.py:53-95` |
| `GET /{project_id}/attachments/detail` | 同上 | `ViewBuilder.list(detail=True)` | `cinder/api/v3/attachments.py:59-63` |
| `GET /{project_id}/attachments/{id}` | path: `id` | `VolumeAttachment.get_by_id` | `cinder/api/v3/attachments.py:46-51` |
| `PUT /{project_id}/attachments/{id}` | body: `attachment.connector`(必填，缺失→400) | `attachment_update` 建立连接信息 | `cinder/api/v3/attachments.py:195-253` |
| `DELETE /{project_id}/attachments/{id}` | path: `id` | `attachment_delete`，返回共享该连接的 attachment 列表 | `cinder/api/v3/attachments.py:255-268` |
| `POST /{project_id}/attachments/{id}/action` → `os-complete` | 无必填体字段 | 置 `attach_status=attached`、`volume.status=in-use`，返回 202；3.44+ (`cinder/api/v3/attachments.py:270-284`) | `cinder/api/v3/attachments.py:270-284` |

## 4. messages 与 limits

| 接口 | 关键参数 | 行为与错误分支 | 源码锚点 |
|---|---|---|---|
| `GET /{project_id}/messages` | 3.5+ query: `resource_uuid`/`resource_type`/`event_id`/`request_id`/`message_level` + 分页排序；通通过滤器校验见 `resource_filters.json` | `get_all` + `_build_user_message`；需 `message:get_all` 策略 | `cinder/api/v3/messages.py:90-123` |
| `GET /{project_id}/messages/{id}` | path: `id` | `show`，按 `MESSAGES_BASE_MICRO_VERSION` 生效 | `cinder/api/v3/messages.py:66-76` |
| `DELETE /{project_id}/messages/{id}` | path: `id` | `delete`，返回 204 | `cinder/api/v3/messages.py:79-88` |
| `GET /{project_id}/limits` | query: `project_id`/`tenant_id`（非 admin 或 ≤3.38 时被剔除） | `QUOTAS.get_project_quotas` 取绝对限额，`cinder.limits` 取速率限制，交 `ViewBuilder.build` | `cinder/api/v3/limits.py:27-53` |

## 5. 共变耦合与修改清单

| 变更点 | 联动文件 | 隐式陷阱与标准动作 |
|---|---|---|
| 改 `create` 字段别名映射 | `cinder/api/v3/volumes.py:239-249`、`cinder/api/v2/volumes.py:193-203` | `name`→`display_name`、`image_id`→`imageRef` 是 v2/v3 双向约定；只改一处会导致视图层读不到字段 |
| 调整微版本门槛 | `cinder/api/v3/volumes.py:68`、`211-221`、`cinder/api/v3/attachments.py:29-31`、`cinder/api/v3/messages.py:103-112` | 微版本会用 `req_version.matches` 决定字段去留，门槛写反会使新字段对老客户端泄漏或对目标版本不可见 |
| 恢复 `source_replica` | `cinder/api/v3/volumes.py:231-237`、`cinder/api/v2/volumes.py:182-188`、`cinder/volume/api.py:228-233` | 三处快速失败必须一致；这是废弃的 replication v1 路径，改动前确认是否已决定重启该能力 |
| 改 attachment 过滤 | `cinder/api/v3/attachments.py:38-69`、`etc/cinder/resource_filters.json` | `allowed_filters` 与 JSON 资源配置两处需同步，否则 `reject_invalid_filters` 会拒绝合法键 |
| 改错误码 | `cinder/api/v3/volumes.py:177-194`、`cinder/api/v3/attachments.py:181-192` | 异常到 HTTP 的翻译散落在控制器内，统一口径参见 [错误码字典](../error-codes.md) |

更多动作类接口（挂载、卸载、扩展、retype 等 30 个 contrib Action）见 [扩展 Action 全集](extensions.md)；接口总数与族谱见 [入向接口总表](../api-reference.md)。
