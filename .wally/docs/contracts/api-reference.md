---
kind: api-contract
scope: inbound-api
status: draft
origin: generated
source_paths: [etc/cinder/api-paste.ini, cinder/api/__init__.py, cinder/api/urlmap.py, cinder/api/v3/router.py, cinder/api/v1/router.py, cinder/api/v2/router.py, cinder/api/versions.py]
symbols: [urlmap_factory, URLMap._match, APIRouter._setup_routes, Versions.all, VersionsController.index, create_resource]
upstream: [INDEX.md]
downstream: [contracts/api/v3-volumes.md, contracts/api/v3-other.md, contracts/api/extensions.md, contracts/error-codes.md, operations/deployment-and-runtime.md]
---

# 入向接口契约全集（REST / Action / CLI）

本页给出 OpenStack Cinder 全部入向接口的**公共协议约定**与**全量路由总表**。接口形态为 PasteDeploy 挂载的 WSGI/REST（v1、v2、v3 三套并存）、由扩展管理器注入的 `os-*` Action，以及 `setup.cfg` 注册的 CLI 入口与 `cinder-manage` 子命令。逐接口参数字典拆分至 [v3 核心资源](api/v3-volumes.md)、[v3 其余资源与 v1/v2](api/v3-other.md)、[扩展 Action 全集](api/extensions.md)；错误语义见 [错误码字典](error-codes.md)，进程与端口边界见 [部署与运行期](../operations/deployment-and-runtime.md)。

## 1. 公共协议、鉴权与响应包络规范

| 维度 | 精确实现规则 | 源码锚点（`路径:行号`） |
|---|---|---|
| 应用入口与版本前缀 | `root_app_factory` 按路径前缀分发：`/`→版本文档、`/v1`、`/v2`、`/v3`；三套 API 各自独立 pipeline | `etc/cinder/api-paste.ini:5-10` (`osapi_volume`) |
| 生产挂载决策 | `root_app_factory` 依据 `enable_v1_api`/`enable_v2_api` 从 `local_conf` 删除 `/v1`/`/v2`；v1 默认关闭且会打弃用告警，v3 始终挂载 | `cinder/api/__init__.py:27-36` (`root_app_factory`) |
| 三段式鉴权 pipeline | `noauth` / `keystone` / `keystone_nolimit` 三套；公共中间件链 `cors http_proxy_to_wsgi request_id faultwrap sizelimit osprofiler`，末端再接鉴权与 app | `etc/cinder/api-paste.ini:12-28` |
| 鉴权过滤器 | `authtoken`（`keystonemiddleware.auth_token`）→ `keystonecontext`（`CinderKeystoneContext`）；`noauth` 由 `NoAuthMiddleware` 发伪 token | `etc/cinder/api-paste.ini:71-75`、`cinder/api/middleware/auth.py:77-145` |
| 生产的 URLMap 工厂 | 生产 composite 调用的是 `paste.urlmap.urlmap_factory`，**不是** `cinder/api/urlmap.py` 中的同名自定义实现 | `cinder/api/__init__.py:27-36` |
| 辅助路由模块（测试/Fakes 使用） | `cinder/api/urlmap.py` 自定义 `URLMap._match` 按 `(domain, app_url)` 最长前缀匹配，`_path_strategy` 先按 `rsplit('.',1)` 识别 MIME 再按版本前缀选 app，`_munge_path` 改写 `SCRIPT_NAME`/`PATH_INFO`；该模块当前仅被 `cinder/tests/unit/test_api_urlmap.py` 与 `cinder/tests/unit/api/fakes.py` 引用 | `cinder/api/urlmap.py:156-168`、`cinder/api/urlmap.py:171-209`、`cinder/api/urlmap.py:189-195` |
| 请求体大小限制 | `sizelimit` = `oslo_middleware.sizelimit:RequestBodySizeLimiter.factory` | `etc/cinder/api-paste.ini:49-50` |
| 故障包络 | `FaultWrapper` 捕获任意异常，`status = getattr(inner,'code',500)`；`safe=True` 才回显 `异常类名: msg`，否则 explanation 留空 | `cinder/api/middleware/fault.py:33-82` |
| 错误 JSON 结构 | `Fault._fault_names` 把状态码映射为 `badRequest`/`forbidden`/`itemNotFound`/`overLimit` 等键，包络为 `{fault_name: {code, message}}`，413 附加 `retryAfter` | `cinder/api/openstack/wsgi.py:1320-1355` |
| 微版本响应头 | 非 legacy 端点回写 `X-OpenStack-Volume-API-Version` 与 `Vary`，版本串来自 `req.api_version_request` | `cinder/api/openstack/wsgi.py:1356-1359` |

符号级请求分发调用树：

```text
HTTP 请求 -> etc/cinder/api-paste.ini:5-10 root_app_factory
  ├─ [挂载判定] cinder/api/__init__.py:27-36 删除禁用的 /v1 /v2 -> paste.urlmap.urlmap_factory
  ├─ [路径 "/"] cinder/api/versions.py:76-86 Versions._setup_routes -> Versions.all (300 多版本清单)
  ├─ [前缀 /v1|/v2|/v3] pipeline_factory (middleware/auth.py:49)
  │    └─ cinder/api/v3/router.py:50-194 APIRouter._setup_routes -> mapper.resource/connect
  │         ├─ 常规 REST action: index/show/create/update/delete/detail
  │         └─ member={action:POST} -> Controller._action -> 扩展 Action (见 extensions.md)
  └─ [异常] cinder/api/middleware/fault.py:77-82 FaultWrapper.__call__ -> _error -> wsgi.Fault
```

## 2. 版本文档与微版本协商

`Versions` 路由仅在根路径注册 `index`/`all`，且不挂载任何扩展（`_setup_extensions` 为空实现），避免版本资源被污染。

| 版本端点 | 方法 | 行为 | 源码锚点（`路径:行号`） |
|---|---|---|---|
| `/` | `GET` | `Versions.all` 返回 `_KNOWN_VERSIONS` 全部条目，`@wsgi.response(300)` | `cinder/api/versions.py:131-136` |
| `/v1` | `GET` | `index@api_version('1.0')`：深拷贝后剔除 `v2.0`、`v3.0` | `cinder/api/versions.py:100-107` |
| `/v2` | `GET` | `index@api_version('2.0')`：剔除 `v1.0`、`v3.0` | `cinder/api/versions.py:109-116` |
| `/v3` | `GET` | `index@api_version('3.0')`：剔除 `v1.0`、`v2.0`，保留微版本 | `cinder/api/versions.py:118-125` |

## 3. 全量入向接口路由总表（Master Inbound Inventory）

以下清单按源码 `mapper.resource` / `mapper.connect` / `ResourceExtension` / `@wsgi.action` 逐条登记，**不做合并省略**。标准 `mapper.resource(name, collection)` 展开为 `GET /{collection}`(index)、`GET /{collection}/detail`(若声明)、`POST /{collection}`(create)、`GET /{collection}/{id}`(show)、`PUT /{collection}/{id}`(update)、`DELETE /{collection}/{id}`(delete)。

### 3.1 v3 资源路由（`cinder/api/v3/router.py:50-194`）

| 分组 | 协议 / 方法 | 精确路径 | Handler 符号与源码锚点 | 执行模式 |
|---|---|---|---|---|
| 版本 | GET | `/` | `VersionsController.all` (`cinder/api/versions.py:131-136`) | 同步 |
| volumes | GET/POST/DELETE/PUT | `/{project_id}/volumes`、`/detail`、`/summary`、`/{id}`、`/{id}/action` | `volumes.create_resource` (`cinder/api/v3/router.py:58-62`) | 同步 / 202 / 动作 |
| messages | GET/DELETE | `/{project_id}/messages`、`/detail`、`/{id}` | `messages.create_resource` (`cinder/api/v3/router.py:64-67`) | 同步 / 204 |
| clusters | GET/PUT | `/{project_id}/clusters`、`/detail`、`/{id}` | `clusters.create_resource` (`cinder/api/v3/router.py:69-72`) | 同步 |
| types | GET/POST/DELETE/PUT | `/{project_id}/types`、`/{id}`、`/{id}/action` | `cinder.api.v2.types` (`cinder/api/v3/router.py:74-77`) | 同步 / 动作 |
| group_types | GET/POST/DELETE/PUT | `/{project_id}/group_types`、`/{id}`、`/{id}/action` | `group_types.create_resource` (`cinder/api/v3/router.py:79-82`) | 同步 / 动作 |
| group_specs | GET/POST/DELETE/PUT | `/{project_id}/group_types/{group_type_id}/group_specs`、`/{id}` | `group_specs.create_resource` (`cinder/api/v3/router.py:84-88`) | 同步 |
| groups | GET/POST/DELETE/PUT | `/{project_id}/groups`、`/detail`、`/{id}` | `groups.create_resource` (`cinder/api/v3/router.py:90-94`) | 同步 / 202 |
| groups action | POST | `/{project_id}/groups/{id}/action` | `GroupsController.action` (`cinder/api/v3/router.py:95-99`) | 动作 |
| groups action | POST | `/{project_id}/groups/action` | `GroupsController.action` (`cinder/api/v3/router.py:100-104`) | 动作 |
| group_snapshots | GET/POST/DELETE/PUT | `/{project_id}/group_snapshots`、`/detail`、`/{id}` | `group_snapshots.create_resource` (`cinder/api/v3/router.py:106-110`) | 同步 / 202 |
| group_snapshots action | POST | `/{project_id}/group_snapshots/{id}/action` | `GroupSnapshotsController.action` (`cinder/api/v3/router.py:111-115`) | 动作 |
| snapshots | GET/POST/DELETE/PUT | `/{project_id}/snapshots`、`/detail`、`/{id}`、`/{id}/action` | `snapshots.create_resource` (`cinder/api/v3/router.py:116-120`) | 同步 / 202 |
| limits | GET | `/{project_id}/limits` | `limits.create_resource` (`cinder/api/v3/router.py:122-124`) | 同步 |
| snapshot_metadata | GET/POST/DELETE/PUT | `/{project_id}/snapshots/{snapshot_id}/metadata`、`/{id}` | `snapshot_metadata` (`cinder/api/v3/router.py:126-133`) | 同步 |
| snapshot_metadata | PUT | `/{project_id}/snapshots/{snapshot_id}/metadata` | `update_all` (`cinder/api/v3/router.py:135-139`) | 同步 |
| volume_metadata | GET/POST/DELETE/PUT | `/{project_id}/volumes/{volume_id}/metadata`、`/{id}` | `volume_metadata` (`cinder/api/v3/router.py:141-148`) | 同步 |
| volume_metadata | PUT | `/{project_id}/volumes/{volume_id}/metadata` | `update_all` (`cinder/api/v3/router.py:150-154`) | 同步 |
| consistencygroups | GET/POST/DELETE/PUT | `/{project_id}/consistencygroups`、`/detail`、`/{id}`、`/{id}/action` | `consistencygroups.create_resource` (`cinder/api/v3/router.py:156-161`) | 同步 / 202 |
| manageable_volumes | GET | `/{project_id}/manageable_volumes`、`/detail` | `volume_manage.create_resource` (`cinder/api/v3/router.py:163-166`) | 同步 |
| manageable_snapshots | GET | `/{project_id}/manageable_snapshots`、`/detail` | `snapshot_manage.create_resource` (`cinder/api/v3/router.py:168-172`) | 同步 |
| backups | GET/POST/DELETE/PUT | `/{project_id}/backups`、`/detail`、`/{id}` | `backups.create_resource` (`cinder/api/v3/router.py:174-178`) | 同步 / 202 |
| attachments | GET/POST/DELETE/PUT | `/{project_id}/attachments`、`/detail`、`/summary`、`/{id}`、`/{id}/action` | `attachments.create_resource` (`cinder/api/v3/router.py:180-184`) | 同步 / 202 / 动作 |
| workers | POST | `/{project_id}/workers/cleanup` | `WorkerController.cleanup` (`cinder/api/v3/router.py:186-189`) | 202 异步 |
| resource_filters | GET | `/{project_id}/resource_filters` | `resource_filters.create_resource` (`cinder/api/v3/router.py:191-194`) | 同步 |

### 3.2 v1 / v2 资源路由

| 版本 | 分组 | 精确路径 | Handler 符号与源码锚点 |
|---|---|---|---|
| v1 | versions | `/v1/` | `versions.create_resource` (`cinder/api/v1/router.py:39-41`) |
| v1 | volumes | `/v1/{project_id}/volumes`、`/detail`、`/{id}`、`/{id}/action` | `volumes.create_resource` (`cinder/api/v1/router.py:45-49`) |
| v1 | types | `/v1/{project_id}/types`、`/{id}` | `types.create_resource` (`cinder/api/v1/router.py:51-53`) |
| v1 | snapshots | `/v1/{project_id}/snapshots`、`/detail`、`/{id}`、`/{id}/action` | `snapshots.create_resource` (`cinder/api/v1/router.py:55-59`) |
| v1 | snapshot_metadata | `/v1/{project_id}/snapshots/{snapshot_id}/metadata`、`/{id}` 及 `PUT .../metadata` | `cinder/api/v1/router.py:61-74` |
| v1 | limits | `/v1/{project_id}/limits` | `cinder/api/v1/router.py:76-78` |
| v1 | volume_metadata | `/v1/{project_id}/volumes/{volume_id}/metadata`、`/{id}` 及 `PUT .../metadata` | `cinder/api/v1/router.py:79-92` |
| v2 | versions | `/v2/` | `versions.create_resource` (`cinder/api/v2/router.py:39-41`) |
| v2 | volumes | `/v2/{project_id}/volumes`、`/detail`、`/{id}`、`/{id}/action` | `volumes.create_resource` (`cinder/api/v2/router.py:45-49`) |
| v2 | types | `/v2/{project_id}/types`、`/{id}`、`/{id}/action` | `types.create_resource` (`cinder/api/v2/router.py:51-54`) |
| v2 | snapshots | `/v2/{project_id}/snapshots`、`/detail`、`/{id}`、`/{id}/action` | `snapshots.create_resource` (`cinder/api/v2/router.py:56-60`) |
| v2 | limits | `/v2/{project_id}/limits` | `cinder/api/v2/router.py:62-64` |
| v2 | snapshot_metadata | `/v2/{project_id}/snapshots/{snapshot_id}/metadata`、`/{id}` 及 `PUT .../metadata` | `cinder/api/v2/router.py:66-79` |
| v2 | volume_metadata | `/v2/{project_id}/volumes/{volume_id}/metadata`、`/{id}` 及 `PUT .../metadata` | `cinder/api/v2/router.py:81-94` |

### 3.3 扩展注入的顶层资源与 Action

33 个 `ExtensionDescriptor` 通过 `get_resources()` 注入顶层资源、通过 `get_controller_extensions()` 注入 Action。全量逐条清单见 [扩展 Action 全集](api/extensions.md)，其中 Action 共 40 个（v3 内置 10 + contrib 注入 30）。

## 4. CLI 子命令与入口脚本全集

`setup.cfg` 的 `[entry_points]` 定义 8 个 `console_scripts` 与 1 个 `wsgi_scripts`；`cinder-manage` 由 `CATEGORIES` 反射出 11 类子命令，每类子命令由该类的公开方法动态生成。

| 入口 | 目标 | 源码锚点（`路径:行号`） |
|---|---|---|
| `cinder-api` | `cinder.cmd.api:main` | `setup.cfg:49` |
| `cinder-backup` | `cinder.cmd.backup:main` | `setup.cfg:50` |
| `cinder-manage` | `cinder.cmd.manage:main` | `setup.cfg:51` |
| `cinder-rootwrap` | `oslo_rootwrap.cmd:main` | `setup.cfg:52` |
| `cinder-rtstool` | `cinder.cmd.rtstool:main` | `setup.cfg:53` |
| `cinder-scheduler` | `cinder.cmd.scheduler:main` | `setup.cfg:54` |
| `cinder-volume` | `cinder.cmd.volume:main` | `setup.cfg:55` |
| `cinder-volume-usage-audit` | `cinder.cmd.volume_usage_audit:main` | `setup.cfg:56` |
| `cinder-wsgi` | `cinder.wsgi.wsgi:initialize_application` | `setup.cfg:58` |

`cinder-manage` 的 11 个类别及生成机制：`CATEGORIES` 字典（`cinder/cmd/manage.py:699-711`）含 `backup`、`config`、`cluster`、`cg`、`db`、`host`、`logs`、`service`、`shell`、`version`、`volume`；`add_command_parsers` 对每个类别反射 `methods_of()` 得到的公开方法注册为子命令与参数（`cinder/cmd/manage.py:714-745`）；顶层 `category_opt` 用 `cfg.SubCommandOpt` 挂载（`cinder/cmd/manage.py:747-749`），入口 `main` 注册该选项后分发（`cinder/cmd/manage.py:781-788`）。

## 5. 共变耦合与修改清单

| 变更点 | 联动文件 | 隐式陷阱与标准动作 |
|---|---|---|
| 新增/删除顶层资源 | `cinder/api/v3/router.py:50-194`、`etc/cinder/api-paste.ini:24-28` | 路由表与 pipeline 的 app 名必须同步；改 `mapper.resource` 集合项（如 `member={'action':'POST'}`）会改变展开的 HTTP 方法集合 |
| 修改 Action 名 | `cinder/api/contrib/*.py`、`etc/cinder/policy.json` | `@wsgi.action` 字面量同时被 `policy.json` 的 `volume_extension:*` 规则引用，改名需同步策略键，否则默认拒绝 |
| 修改错误包络 | `cinder/api/middleware/fault.py:46-75`、`cinder/api/openstack/wsgi.py:1320-1355` | `safe` 标志决定是否回显内部 msg，误开泄露敏感信息；`_fault_names` 未覆盖的状态码退化为 `computeFault` |
| 修改版本前缀 | `etc/cinder/api-paste.ini:5-10`、`cinder/api/__init__.py:27-36`、`cinder/api/versions.py:76-136`；辅助模块 `cinder/api/urlmap.py:156-209` | 生产前缀由 ini 与 `root_app_factory` 决定，辅助 urlmap 仅供测试；`_KNOWN_VERSIONS` 深拷贝剔除逻辑若不同步会导致版本文档多报/漏报 |
| 新增 CLI 入口 | `setup.cfg:48-58`、`cinder/cmd/manage.py:699-749` | 新增类别必须加入 `CATEGORIES`，否则 `cinder-manage` 不识别；子命令由方法反射生成，注意 `@args` 装饰器参数 |

验证命令见 [构建、启动与单测验证手册](../operations/dev-and-test.md)，运行期端口与进程边界见 [部署、进程拓扑与持久化目录契约](../operations/deployment-and-runtime.md)。
