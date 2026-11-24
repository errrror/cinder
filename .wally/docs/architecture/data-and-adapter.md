---
kind: component
scope: cinder-sqlalchemy-ovo-driver-base
status: draft
origin: generated
source_paths:
  - cinder/db/base.py
  - cinder/db/api.py
  - cinder/db/sqlalchemy/api.py
  - cinder/db/sqlalchemy/models.py
  - cinder/objects/base.py
  - cinder/volume/driver.py
  - cinder/backup/driver.py
  - cinder/volume/configuration.py
symbols:
  - Base.__init__
  - IMPL
  - model_query
  - quota_reserve
  - Volume
  - CinderObjectRegistry
  - CinderObject.cinder_obj_get_changes
  - CinderObjectSerializer
  - VolumeDriver
  - BackupDriver
  - Configuration
upstream: [architecture/core-engine.md, architecture/async-job-worker.md]
downstream: [integrations/downstream/sqlalchemy-db.md, integrations/downstream/storage-drivers.md, integrations/downstream/swift-backup.md]
---

# Cinder 数据持久化、对象与驱动底座组件

> **边界切分铁律**：本页只讲**本地数据库访问门面、ORM 映射、CinderObject（OVO）版本兼容层与驱动抽象基类**。各具体外部后端的业务封装（请求字典如何组装、返回字段如何解包）分别在 [数据库下游契约](../integrations/downstream/sqlalchemy-db.md)、[存储驱动下游契约](../integrations/downstream/storage-drivers.md) 与 [备份后端契约](../integrations/downstream/swift-backup.md) 展开。

本组件把三类关注点分层：`db.Base` 负责按配置注入数据库驱动，`cinder.db.api` 以 `IMPL` 门面转发到 SQLAlchemy 实现，`CinderObject` 负责跨 RPC 的版本兼容与字段变更提取；`VolumeDriver` / `BackupDriver` 则是后端厂商实现的抽象契约，配置通过 `Configuration` 按 backend 分组注入。

## 1. 本地持久化契约

```mermaid
graph LR
    A["db.Base 注入 db_driver"] --> B["cinder.db.api 门面"]
    B --> C["IMPL = DBAPI.from_config"]
    C --> D["cinder.db.sqlalchemy.api"]
    D --> E["cinder.db.sqlalchemy.models"]
```

| 表名 / 模型 | 主键与约束 | 权威读写函数（`路径:行号`） | 事务、锁与安全约束 |
|---|---|---|---|
| `volumes` / `Volume` | `id = Column(String(36), primary_key=True)`；`_name_id` 禁止直接访问 | `Volume` 模型 (`cinder/db/sqlalchemy/models.py:240-310`)；门面 `service_get` 等 (`cinder/db/api.py:101-129`) | ORM `filter_by` 参数化查询，不做字符串拼接；`name` 由 `CONF.volume_name_template % self.name_id` 派生 (`:254-256`) |
| `volume_metadata` / `VolumeMetadata` | `id = Column(Integer, primary_key=True)`，`key = Column(String(255))` | `VolumeMetadata` (`cinder/db/sqlalchemy/models.py:313-317`) | 作为卷的键值附属表，通过 ORM relationship 关联 |
| 配额用量表（由 `quota_reserve` 维护） | 以 `project_id` + `resource` 为逻辑键 | `quota_reserve` (`cinder/db/sqlalchemy/api.py:1146-1236`) | `with session.begin():` 包裹（`:1151`）；`@require_context` 与 `@_retry_on_deadlock` 装饰（`:1144-1145`）；刷新用 `QUOTA_SYNC_FUNCTIONS[resources[resource].sync]`（`:1193`） |
| 服务注册表（由 `Service` 对象操作） | 以 `host` + `binary` 定位 | `service_get` / `service_create` (`cinder/db/api.py:101-134`) | `dispose_engine` 对 sqlite 引擎刻意跳过重建（`cinder/db/api.py:79-90`），避免测试库丢失 |

`model_query` (`cinder/db/sqlalchemy/api.py:274-310`) 是读路径的统一入口：它从 `context.read_deleted` 推导过滤，`read_deleted='no'` 加 `deleted=False`、`'only'` 加 `deleted=True`、`'int_no'` 加 `deleted=0`，`project_only` 且为用户上下文时追加 `project_id` 过滤；对 `VolumeAttachment` 特殊处理为 join `models.Volume.project_id`（`:301-308`）。不可识别的 `read_deleted` 值直接抛异常（`:297-299`）。

## 2. 驱动注入与查询调用树

```text
db.Base.__init__ (cinder/db/base.py:32-42)
  ├─ super().__init__() (:38) 保证多继承下 MRO 正确
  ├─ db_driver = db_driver or CONF.db_driver (:39-40)
  ├─ self.db = importutils.import_module(db_driver) (:41)
  └─ self.db.dispose_engine() (:42)

cinder.db.api 门面 (cinder/db/api.py:66-71)
  ├─ _BACKEND_MAPPING = {'sqlalchemy': 'cinder.db.sqlalchemy.api'} (:66)
  └─ IMPL = DBAPI.from_config(conf=CONF, backend_mapping=_BACKEND_MAPPING, lazy=True) (:69-71)
       └─ 门面函数（如 service_get）直接 return IMPL 的同名函数(...) (:101-134)

cinder.db.sqlalchemy.api.model_query (cinder/db/sqlalchemy/api.py:274-310)
  ├─ session = kwargs.get('session') or get_session() (:283)
  ├─ read_deleted = kwargs.get('read_deleted') or context.read_deleted (:284)
  ├─ query = session.query(model, *args) (:287)
  ├─ [switch read_deleted] filter_by(deleted=...) (:289-299)
  └─ [if project_only and is_user_context] filter_by(project_id=context.project_id) (:301-308)

quota_reserve (cinder/db/sqlalchemy/api.py:1146-1236)
  ├─ session = get_session(); with session.begin() (:1150-1151)
  ├─ usages = _get_quota_usages(...); allocated = quota_allocated_get_all_by_project(...) (:1156-1160)
  ├─ [for resource in deltas] 判 in_use < 0 / until_refresh / max_age 决定 refresh (:1163-1188)
  │    └─ refresh 时 sync = QUOTA_SYNC_FUNCTIONS[...] 并写回 usages[res].in_use (:1193-1216)
  └─ [检查负向 delta] unders 由 allocated 或 usages 计算 (:1230-1236)
```

## 3. CinderObject（OVO）版本兼容层

| 契约维度 | 实现符号 | 源码锚点 | 语义与陷阱 |
|---|---|---|---|
| 命名空间 | `CinderObject.OBJ_PROJECT_NAMESPACE` | `cinder/objects/base.py:157-161` | 固定为 `'cinder'`，使 nova/cinder 对象可在同一消息总线上区分 |
| 注册钩子 | `CinderObjectRegistry.registration_hook` | `cinder/objects/base.py:140-154` | `setattr(objects, cls.obj_name(), cls)`；若类有 `cinder_ovo_cls_init` 则调用，用于持久化类注册模型 |
| 变更提取 | `CinderObject.cinder_obj_get_changes` | `cinder/objects/base.py:163-183` | `obj_get_changes()` 后把带时区 datetime 转为 UTC 再去时区，便于直接传给不接受时区的数据库更新方法 |
| 向后兼容 | `CinderObject.obj_make_compatible` | `cinder/objects/base.py:185-188` | 先 `_log_backport` 再委托父类，目标版本低于对象当前版本时裁剪字段 |
| 字典兼容 | `CinderObjectDictCompat.get` | `cinder/objects/base.py:198-237` | 未知键返回 `None` 并打调试日志；仅作过渡 shim，源码注明最终会删除（`:207-208`） |
| 持久化公共字段 | `CinderPersistentObject` | `cinder/objects/base.py:240-245` | 单独的 mixin 基类，声明 `OPTIONAL_FIELDS`，由具体对象多重继承 |
| 序列化钉住 | `CinderObjectSerializer` | `cinder/objects/base.py:492` | 由 RPC server 以 `get_minimum_obj_version` 构造，见 [后台服务组件](async-job-worker.md) |

具体对象 `Volume` 的继承链为 `cleanable.CinderCleanableObject, base.CinderObject, base.CinderObjectDictCompat, base.CinderComparableObject, base.ClusteredObject`（`cinder/objects/volume.py:52-54`），并在类上通过 `@base.CinderObjectRegistry.register` 注册（`:51`）。`OBJ_VERSIONS` 历史版本表见 `cinder/objects/base.py:136-137`（如 `'1.27': {'Backup': '1.5', 'BackupImport': '1.5'}`）。

## 4. 驱动底座与配置注入

| 底座类 / 函数 | 统一契约 | 缺省行为 | 源码锚点 |
|---|---|---|---|
| `VolumeDriver` | 多重继承 `ManageableVD, CloneableImageVD, ManageableSnapshotsVD, MigrateVD, BaseVD` | `create_volume`、`delete_volume`、`create_snapshot` 等抛 `NotImplementedError`（`:2116-2142`） | `cinder/volume/driver.py:2114-2142` |
| `VolumeDriver` 导出与连接 | `ensure_export`、`create_export`、`initialize_connection` | 基类声明空实现/默认行为，由厂商覆盖 | `cinder/volume/driver.py:2201-2219` |
| `BackupDriver` | 抽象方法 `backup(backup, volume_file, backup_metadata=False)`、`restore(backup, volume_id, volume_file)`、`delete_backup(backup)` | 默认 `export_record` 返回 `{}`、`import_record` 空操作（`:380-411`） | `cinder/backup/driver.py:348-415` |
| `BackupDriverWithVerify` | 增加抽象 `verify(backup)` | 用于后端自带校验的子类 | `cinder/backup/driver.py:418-422` |
| `DefaultGroupConfiguration` | 仅从 `DEFAULT` 取配置，`safe_get` 捕获 `cfg.NoSuchOptError` 返回 `None` | `__getattr__` 直接转发 `CONF` | `cinder/volume/configuration.py:49-71` |
| `BackendGroupConfiguration` | 先查 backend 专属分组，值为 `None` 时回落共享分组 `backend_defaults` | `_safe_register` 吞掉 `cfg.DuplicateOptError` | `cinder/volume/configuration.py:74-135` |
| `Configuration` | 兼容 `DEFAULT` 风格与 backend 分组风格的配置 shim | 由卷管理器构造并传给驱动 | `cinder/volume/configuration.py:138-144` |

无外部环境时，本仓通过 fixture 替身降级：备份驱动的单测替身见 `cinder/tests/unit/backup/fake_swift_client.py` 与 `cinder/tests/unit/backup/fake_google_client.py`；与此同时，真正的业务字典组装在 `cinder/backup/driver.py` 的子类而非本页展开。

## 5. 核心源码符号表

| 源码文件 | 核心符号（`行号`） | 职责边界 |
|---|---|---|
| `cinder/db/base.py` | `Base.__init__` (`:32-42`) | 数据库驱动按 `CONF.db_driver` 动态注入 |
| `cinder/db/api.py` | `_BACKEND_MAPPING` (`:66`), `IMPL` (`:69-71`), `dispose_engine` (`:79-90`), `service_get` (`:101-114`) | 稳定门面，隔离后端实现切换 |
| `cinder/db/sqlalchemy/api.py` | `model_query` (`:274-310`), `quota_reserve` (`:1146-1236`) | ORM 查询与配额事务 |
| `cinder/db/sqlalchemy/models.py` | `Volume` (`:240-310`), `VolumeMetadata` (`:313-317`) | 表结构声明与关系映射 |
| `cinder/objects/base.py` | `CinderObjectRegistry` (`:140-154`), `CinderObject` (`:157-195`), `CinderObjectDictCompat` (`:198-237`), `CinderPersistentObject` (`:240-245`), `CinderObjectSerializer` (`:492`) | OVO 注册、版本兼容与变更提取 |
| `cinder/volume/driver.py` | `VolumeDriver` (`:2114-2142`), `create_volume` (`:2119`), `initialize_connection` (`:2216`) | 卷后端能力契约 |
| `cinder/backup/driver.py` | `BackupDriver` (`:348-415`), `BackupDriverWithVerify` (`:418-422`) | 备份后端能力契约 |
| `cinder/volume/configuration.py` | `DefaultGroupConfiguration` (`:49-71`), `BackendGroupConfiguration` (`:74-135`), `Configuration` (`:138-144`) | 多后端配置回退解析 |

## 6. 上下游调用关系

- **上游调用方**：[调度引擎](core-engine.md) 经 `driver.volume_update_db` 写回 host；[后台服务组件](async-job-worker.md) 的 `VolumeManager` / `BackupManager` 通过 `db.Base` 注入的门面读写状态。
- **仓内下游**：`VolumeDriver` 的具体子类位于 `cinder/volume/drivers/`，`BackupDriver` 子类位于 `cinder/backup/drivers/`，真实外部交互字典见 [存储驱动契约](../integrations/downstream/storage-drivers.md)。
- **事务边界**：配额预留的原子性由 `cinder/db/sqlalchemy/api.py:1151` 的 `session.begin()` 保证，与 Taskflow 的配额预留任务（`cinder/volume/flows/api/create_volume.py:600`）配合形成双层保护。

## 7. 共变耦合与修改清单

1. 改 `volumes` 表字段：`cinder/db/sqlalchemy/models.py:240-310` → `CinderObject` 的字段声明与 `OBJ_VERSIONS` 历史表（`cinder/objects/base.py:136-137`）→ `CinderObject.obj_make_compatible`（`:185-188`）→ RPC 消费端；漏改版本表会导致滚动升级期间旧节点解包失败。
2. 改 `model_query` 的过滤语义（`cinder/db/sqlalchemy/api.py:274-310`）：必须同时复核 `VolumeAttachment` 的 join 分支（`:301-306`）与所有依赖 `read_deleted` 值的门面函数，避免误删数据被过滤掉或反之下。
3. 新增数据库后端：在 `cinder/db/api.py:66-71` 的 `_BACKEND_MAPPING` 增加键，并保证新模块导出同名函数；门面层不做参数转换，签名不一致会在运行时才暴露。
4. 新增驱动抽象方法：先改 `cinder/volume/driver.py:2114-2142` 或 `cinder/backup/driver.py:348-415`，再逐一补齐所有厂商子类与单测替身 `cinder/tests/unit/backup/fake_swift_client.py` 等，否则既有驱动会在实例化时抛 `NotImplementedError`。
5. 调整多后端配置回退：`cinder/volume/configuration.py:74-135` 的 `SHARED_CONF_GROUP = 'backend_defaults'`（`:46`）与 `_safe_register` 的去重策略改变时，须同步 [配置字典](../contracts/configuration.md) 并验证 `cinder/cmd/volume.py:84-98` 为每个 backend 注册独立分组的路径。
6. 时区处理：`cinder_obj_get_changes`（`cinder/objects/base.py:163-183`）刻意去掉时区信息，任何新增 datetime 字段若绕开此方法直接入库，会在严格时区校验的数据库上失败。
