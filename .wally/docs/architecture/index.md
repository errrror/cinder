---
kind: component
scope: architecture-index
status: draft
origin: generated
source_paths: [cinder/api, cinder/cmd, cinder/common, cinder/db, cinder/volume, cinder/scheduler, cinder/backup, cinder/objects, cinder/interface, cinder/wsgi, cinder/image, cinder/compute, cinder/keymgr, cinder/zonemanager, cinder/brick, cinder/message, cinder/group, cinder/consistencygroup, cinder/transfer, cinder/hacking, cinder/locale, cinder/tests, contrib/block-box, etc/cinder, tools, doc, api-ref, rally-jobs, releasenotes, setup.cfg, tox.ini]
symbols: [APIRouter, Service, FilterScheduler, VolumeManager, BackupManager, CinderObject, VolumeDriver]
upstream: [INDEX.md, overview/system-architecture.md]
downstream: [architecture/module-dep-matrix.md, operations/boundary.md]
---

# 组件技术架构总表

Cinder 是扁平 Python 包，按运行时框架模型可归为 API 服务、RPC 后台服务、核心调度/任务引擎、数据持久化与驱动底座、CLI 五类；下表覆盖全部技术模块，并将不单独成篇的工具目录与辅助模块纳入 Tier 3 归档表，确保源码目录零遗漏。各组件的内部实现见对应专页，跨模块调用边见 [模块依赖矩阵](module-dep-matrix.md)。

## 1. 全量核心组件矩阵（Tier 1 & Tier 2）

| 组件标识 | 框架模型（Archetype） | 源码路径 | 核心入口符号（`路径:行号`） | 技术能力与业务边界 | 直接上游 | 直接下游 | 详情文档 |
|---|---|---|---|---|---|---|---|
| `api-wsgi` | `API Service` | `cinder/api/`、`cinder/wsgi/`、`etc/cinder/api-paste.ini` | `APIRouter._setup_routes` (`cinder/api/v3/router.py:50`)、`WSGIService` (`cinder/service.py:533`) | Paste 管线、微版本、鉴权、扩展 Action | 租户 / cinderclient | `volume-api`、`scheduler-rpc` | [api-service](api-service.md) |
| `rpc-services` | `Async/Cron Worker` | `cinder/service.py`、`cinder/manager.py`、`cinder/coordination.py`、`cinder/cmd/{volume,scheduler,backup}.py` | `Service.start` (`cinder/service.py:232`)、`PeriodicTasks` (`cinder/manager.py:77`) | RPC Server、周期任务、分布式锁、多后端进程 | `api-wsgi`、`cinder-manage` | `scheduler-engine`、`volume-manager` | [async-job-worker](async-job-worker.md) |
| `scheduler-engine` | `Core Engine` | `cinder/scheduler/`、`cinder/volume/flows/`、`cinder/flow_utils.py` | `FilterScheduler._schedule` (`cinder/scheduler/filter_scheduler.py:507`)、`get_flow` (`cinder/volume/flows/api/create_volume.py:818`) | 过滤器/权重链、重调度、Taskflow 图 | `rpc-services` | `volume-manager`、`db-dao` | [core-engine](core-engine.md) |
| `volume-manager` | `Core Engine` | `cinder/volume/manager.py`、`cinder/volume/api.py` | `API.create` (`cinder/volume/api.py:218`)、`VolumeManager.create_volume` (`cinder/volume/manager.py:583`) | 卷状态机、配额编排、迁移/retype/快照 | `api-wsgi`、`scheduler-engine` | `driver-plugins`、`db-dao` | [core-engine](core-engine.md)、[卷生命周期](../business/volume-lifecycle.md) |
| `backup-manager` | `Async/Cron Worker` | `cinder/backup/` | `BackupManager.create_backup` (`cinder/backup/manager.py:279`) | 备份/恢复/导入导出，brick 挂载 | `api-wsgi` | `driver-plugins`、`db-dao` | [async-job-worker](async-job-worker.md)、[备份恢复](../business/backup-restore.md) |
| `db-dao` | `Data & Adapter` | `cinder/db/`、`cinder/objects/` | `model_query` (`cinder/db/sqlalchemy/api.py:274`)、`CinderObject` (`cinder/objects/base.py:157`) | 参数化 SQL、OVO 版本化序列化、配额事务 | 全业务层 | SQLAlchemy / DB | [data-and-adapter](data-and-adapter.md)、[领域模型](../business/domain-models/index.md) |
| `driver-plugins` | `Data & Adapter` | `cinder/volume/driver.py`、`cinder/interface/`、`cinder/brick/` | `VolumeDriver` (`cinder/volume/driver.py:2114`)、`DriverInfo` (`cinder/interface/util.py:60`) | 动态装载卷/备份/Zone 驱动，os-brick 连接 | `volume-manager`、`backup-manager` | 外部存储阵列 | [data-and-adapter](data-and-adapter.md)、[存储驱动契约](../integrations/downstream/storage-drivers.md) |
| `cli-admin` | `UI & CLI` | `cinder/cmd/manage.py`、`cinder/cmd/rtstool.py`、`cinder/cmd/volume_usage_audit.py`、`setup.cfg:48-58` | `CATEGORIES` (`cinder/cmd/manage.py:699`)、`main` (`cinder/cmd/manage.py:781`) | 11 类运维子命令、rts 工具、用量审计 | 运维人员 | `db-dao`、`rpc-services` | [ui-and-cli](ui-and-cli.md) |
| `external-adapters` | `Data & Adapter` | `cinder/image/`、`cinder/compute/`、`cinder/keymgr/`、`cinder/zonemanager/` | `GlanceClientWrapper` (`cinder/image/glance.py:147`)、`novaclient` (`cinder/compute/nova.py:107`) | 镜像、计算、密钥、FC Zone 外部封装 | `volume-manager`、`backup-manager` | Glance / Nova / Barbican / FC 交换机 | [集成总览](../integrations/index.md) |

## 2. 轻量辅助模块归档表（Tier 3 Utilities — 零遗漏兜底）

所有文件数少、无需独立成篇的辅助模块、常量定义或脚本统一登记于此，供 Agent 快速定位复用函数（禁止重复造轮子）：

| 源码文件路径 | 核心导出函数 / 类 / 常量 | 调用方模块 | 具体职责说明 |
|---|---|---|---|
| `cinder/common/config.py` | `set_middleware_defaults` (`:222`) | `cinder/cmd/api.py:52`、`cinder/wsgi/wsgi.py:43` | 统一 oslo.middleware CORS 头与方法白名单 |
| `cinder/common/constants.py` | `SCHEDULER_TOPIC`、`VOLUME_TOPIC`、`BACKUP_TOPIC` (`:21-27`) | `cinder/rpc.py`、三个 `rpcapi.py` | 服务二进制名与 RPC Topic 常量 |
| `cinder/common/sqlalchemyutils.py` | `paginate_query` (`:62`) | `cinder/db/sqlalchemy/api.py` | 统一分页/排序查询封装 |
| `cinder/policy.py` | `init`、`enforce`、`check_is_admin` (`:31-75`) | `cinder/volume/api.py:105` 等 | 策略文件加载与权限判定 |
| `cinder/context.py` | `RequestContext`、`get_admin_context` (`:46,194`) | 全服务 | 租户上下文序列化与提权 |
| `cinder/quota.py` / `cinder/quota_utils.py` | `QuotaEngine`、`process_reserve_over_quota` (`:822,250`) | Taskflow 配额任务 | 配额引擎与嵌套项目层级 |
| `cinder/utils.py` / `cinder/ssh_utils.py` | `execute`、`get_root_helper`、`SSHPool` (`:119,459` / `:55`) | 驱动层 | 命令执行、rootwrap、SSH 连接池 |
| `cinder/exception.py` | `CinderException` 及 288 个异常类 (`:76`) | 全仓 | 领域异常与 `code` 属性定义 |
| `cinder/i18n.py` / `cinder/locale/` | `enable_lazy`、`translate` (`:31,35`) | 全仓 | gettext 翻译目录（非业务逻辑） |
| `cinder/version.py` / `cinder/hacking/` | `version_string`、`checks.factory` | `cinder/cmd/*`、`tox.ini:138` | 版本字符串与 flake8 本地检查 |
| `cinder/test.py` | `TestCase`、`RPCAPITestCase` (`:91,406`) | `cinder/tests/unit/*` | 单测基类、超时与配置加载 |
| `cinder/message/` | `API`、`EventIds` (`cinder/message/api.py:40`、`defined_messages.py:25`) | 调度器/卷管理器 | 异步错误消息写入与文本翻译 |
| `cinder/transfer/` | `API` (`cinder/transfer/api.py:54`) | `cinder/api/contrib/volume_transfer.py` | 卷转移凭据流程 |
| `cinder/group/` / `cinder/consistencygroup/` | `wrap_check_policy`、`check_policy` (`cinder/group/api.py:60,74`) | `cinder/api/v3/groups.py`、`consistencygroups.py` | 组 API 的策略包装 |
| `cinder/brick/local_dev/` | `Lvm` (`cinder/brick/local_dev/lvm.py`) | `cinder/volume/drivers/lvm.py` | 本地 LVM 卷管理命令封装 |
| `cinder/volume/throttling.py` / `cinder/volume/qos_specs.py` / `cinder/volume/volume_types.py` / `cinder/volume/group_types.py` | `Throttle`、`create`、`create`、`create` (`:31,36,43,34`) | `cinder/volume/api.py` | 卷类型、QoS、组类型与 cgroup 限流 |
| `cinder/scheduler/evaluator/` / `cinder/scheduler/{filters,weights,flows}/` | `HostFilterHandler` 等插件 | `cinder/scheduler/host_manager.py` | 过滤/权重/任务图插件集合（入口见 `setup.cfg:28-43`） |
| `cinder/backup/drivers/` | `CephBackupDriver`、`GlusterfsBackupDriver` 等 7 个驱动 | `cinder/backup/manager.py:386` | Ceph/GlusterFS/Google/NFS/POSIX/Swift/TSM 备份后端 |
| `cinder/volume/drivers/` | 30+ 厂商驱动（LVM、Ceph、NetApp、Hitachi、IBM 等） | `cinder/volume/manager.py` | 通过 `cinder/interface/util.py:42` 动态装载 |
| `cinder/tests/unit/`、`cinder/tests/functional/`、`cinder/tests/compliance/`、`cinder/tests/tempest/plugin.py` | `ostestr` 用例集合 | `tox.ini:21-55` | 单测/functional/compliance/Tempest 插件，映射见 [构建与单测](../operations/dev-and-test.md) |
| `etc/cinder/` | `api-paste.ini`、`policy.json`、`rootwrap.conf`、`resource_filters.json` | 全服务 | Paste 管线、策略、提权与过滤器配置 |
| `api-ref/source/`、`doc/source/`、`doc/ext/` | Sphinx 文档源 | `tox.ini:30-40,94-100` | API 参考与开发者文档构建 |
| `contrib/block-box/` | `Makefile`、`docker-compose.yml`、`cinder.rc`、`etc-cinder/cinder.conf` | 可选 demo | noauth 容器化 Cinder 演示环境 |
| `tools/config/`、`tools/hooks/`、`tools/*.sh` | `cinder-config-generator.conf`、`generate_cinder_opts.py`、CI 脚本 | `tox.ini:56-124` | 配置生成、lint、pre-commit 与矩阵测试 |
| `rally-jobs/extra/`、`rally-jobs/plugins/` | Rally 场景与插件 | CI | 性能/规模回归场景 |
| `releasenotes/notes/`、`releasenotes/source/` | YAML 发布说明片段 | `tox.ini:39-40` | 版本变更记录与 Sphinx 构建 |
| `.wally/` | `config.json`、`core/`、`docs/`、`profiles/`、`rules/`、`scripts/`、`versions/` | 本地 AI 协作流程 | SOP 任务与知识库元数据，边界见 [认知边界](../operations/boundary.md) |

## 3. 分层隔离与运行期边界原则

| 边界 | 允许的调用方向 | 禁止的反向耦合 | 证据锚点（`路径:行号`） |
|---|---|---|---|
| API ↔ 业务编排 | Controller 调 `volume_api` / `backup_api` | 编排层不得 import webob 或读取 `req` 对象 | `cinder/api/v3/volumes.py:197-331`、`cinder/volume/api.py:218` |
| 编排 ↔ 调度 | Taskflow 任务通过 `scheduler_rpcapi` 发 cast | 调度器不得直接写卷状态 | `cinder/volume/flows/api/create_volume.py:730-789` |
| 调度 ↔ 执行 | RPC Topic 解耦，OVO 传输 | 调度器不得驱动 import 厂商驱动 | `cinder/scheduler/rpcapi.py:94-101`、`cinder/volume/rpcapi.py` |
| 执行 ↔ 存储 | Manager 调驱动接口与 DAO | 驱动不得写业务状态字段 | `cinder/volume/manager.py:583-670`、`cinder/db/sqlalchemy/api.py:274` |
| CLI ↔ 服务 | cinder-manage 直连 DB 与 RPC | 不得绕过策略检查直接改业务表 | `cinder/cmd/manage.py:699-781` |

## 4. 共变耦合与修改清单（Co-Change Playbook）

1. 新增顶层源码目录：必须在上表或 [认知边界](../operations/boundary.md) 登记，并同步 `.wiki-meta.json` 的 `moduleTree`，否则 G2 目录覆盖门禁会失败。
2. 调整组件边界（如把逻辑从 API 移到 Manager）：同时更新 [模块依赖矩阵](module-dep-matrix.md) 的调用边、[主干调用链](../overview/callchain-panorama.md) 的符号树与相关单测映射。
3. 修改 `setup.cfg` 的 entry_points：检查 [模块依赖矩阵](module-dep-matrix.md) 的插件清单与 `cinder/tests/unit/test_*opts*` 是否仍覆盖新增入口。
