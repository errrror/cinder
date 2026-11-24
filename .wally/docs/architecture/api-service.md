---
kind: component
scope: cinder-osapi-volume-wsgi
status: draft
origin: generated
source_paths:
  - etc/cinder/api-paste.ini
  - cinder/cmd/api.py
  - cinder/service.py
  - cinder/api/__init__.py
  - cinder/api/middleware/auth.py
  - cinder/api/urlmap.py
  - cinder/api/v3/router.py
  - cinder/api/extensions.py
  - cinder/api/middleware/fault.py
  - cinder/api/openstack/wsgi.py
symbols:
  - main
  - WSGIService
  - root_app_factory
  - pipeline_factory
  - urlmap_factory
  - URLMap._match
  - APIRouter._setup_routes
  - ExtensionManager
  - FaultWrapper._error
  - ResourceExceptionHandler.__exit__
  - Fault.__call__
upstream: [overview/system-architecture.md, architecture/index.md]
downstream: [architecture/async-job-worker.md, contracts/api-reference.md, contracts/api/v3-other.md]
---

# Cinder OS API（WSGI）接入组件

`cinder-api` 进程以 `oslo_service.wsgi.Server` 承载名为 `osapi_volume` 的 paste 复合应用，`cinder-wsgi` 脚本加载同一应用；请求先穿过按 `auth_strategy` 选择的中间件栈，再落到 v3 的 `APIRouter`，由 `Resource` 分派至具体控制器。本组件只做同步请求解析与参数校验，耗时的卷操作通过 RPC cast 转交给 [异步作业执行组件](async-job-worker.md)，因此接入层的并发模型是多 worker 进程加 green 协程，而非后台任务队列。

## 1. 进程入口与装配链

| 装配阶段 | 源码锚点 | 符号与行为 |
|---|---|---|
| 进程入口 | `cinder/cmd/api.py:47-63` (`main`) | `objects.register_all()` → `CONF(sys.argv[1:], project='cinder')` → `rpc.init(CONF)` → `service.WSGIService('osapi_volume')` → `launcher.launch_service(server, workers=server.workers)` → `launcher.wait()` |
| 服务容器 | `cinder/service.py:533-567` (`WSGIService.__init__`) | `self.loader = wsgi.Loader(CONF)`，`self.app = self.loader.load_app(name)`；worker 数缺省取 `processutils.get_worker_count()`，小于 1 时抛 `exception.InvalidInput` |
| 启动与端口回填 | `cinder/service.py:590-602` (`WSGIService.start`) | 先 `self.manager.init_host()`（若配置了 manager），再 `self.server.start()`，并把 `self.port` 回填为真实端口，支持配置为 `0` 时随机端口 |
| 版本分发 | `cinder/api/__init__.py:27-36` (`root_app_factory`) | 依据 `CONF.enable_v1_api` / `CONF.enable_v2_api` 从 `local_conf` 删除 `/v1`、`/v2` 键，最终返回 `paste.urlmap.urlmap_factory(loader, global_conf, **local_conf)` |
| 策略化管道 | `cinder/api/middleware/auth.py:49-61` (`pipeline_factory`) | `pipeline = local_conf[CONF.auth_strategy]`；`CONF.api_rate_limit` 为假时改用认证策略名与 `_nolimit` 后缀拼接而成的管道行；`filters.reverse()` 后逐层包裹 `app` |
| 复合与过滤声明 | `etc/cinder/api-paste.ini:5-10`, `etc/cinder/api-paste.ini:24-28`, `etc/cinder/api-paste.ini:30-50` | `composite:osapi_volume` 把 `/`、`/v1`、`/v2`、`/v3` 映射到四个应用；v3 三套管道分别为 `noauth`、`keystone`、`keystone_nolimit`；过滤器顺序为 `cors → http_proxy_to_wsgi → request_id → faultwrap → sizelimit → osprofiler → authtoken/keystonecontext` |
| 应用与版本端点 | `etc/cinder/api-paste.ini:52-65` | `app:apiv3` 指向 `cinder.api.v3.router:APIRouter.factory`；`pipeline:apiversions` 指向 `cinder.api.versions:Versions.factory` |

```mermaid
graph LR
    A["进程入口 main"] --> B["WSGIService 加载 osapi_volume"]
    B --> C["root_app_factory 版本分发"]
    C --> D["pipeline_factory 中间件栈"]
    D --> E["APIRouter 路由与扩展装配"]
    E --> F["Resource 控制器分派"]
    F --> G["RPC cast 转交后台服务"]
```

图中 `APIRouter` 继承 `base_wsgi.Router`，并通过 `ext_mgr.get_resources()` 汇总扩展资源（`cinder/api/openstack/__init__.py:65`, `cinder/api/openstack/__init__.py:82-94`）；扩展资源最终成为可分派的 WSGI 资源。

## 2. 请求处理洋葱链

```text
HTTP 请求 -> etc/cinder/api-paste.ini:24-28 pipeline_factory(auth_strategy)
  ├─ [1. cors / http_proxy_to_wsgi / request_id] oslo_middleware 注入 CORS 头、代理前缀与请求 ID
  ├─ [2. faultwrap] cinder/api/middleware/fault.py:33-44 FaultWrapper.status_to_type() 预建状态码到 webob 异常类的映射
  ├─ [3. sizelimit / osprofiler] 限制请求体大小并挂接 osprofiler 追踪
  ├─ [4. 认证] cinder/api/middleware/auth.py:49-61 选 noauth 或 keystone； keystonecontext 由 cinder.api.middleware.auth:CinderKeystoneContext.factory 构造
  ├─ [5. 路径匹配] cinder/api/urlmap.py:171-180 URLMap._match() 取最长 app_url 前缀，未命中走 not_found_app
  ├─ [6. 路由] cinder/api/v3/router.py:46-48 APIRouter(ExtensionManager=extensions.ExtensionManager) -> :50-194 _setup_routes(mapper, ext_mgr)
  ├─ [7. 分派] cinder/api/openstack/wsgi.py:584-620 ResourceExceptionHandler.__exit__() 包裹控制器动作
  │    ├─ NotAuthorized -> Fault(HTTPForbidden) (:599-601)
  │    ├─ Invalid / NotFound -> Fault(ConvertedException(code, explanation)) (:604-606)
  │    ├─ TypeError -> 记错误日志并 Fault(HTTPBadRequest) (:607-611)
  │    └─ HTTPException -> Fault(ex_value) (:615-617)
  └─ [8. 错误序列化] cinder/api/openstack/wsgi.py:1339-1373 Fault.__call__() 按 best_match_content_type 选 JSONDictSerializer，写 x-compute-request-id 与版本头
```

`cinder/api/urlmap.py:156-168` (`urlmap_factory`) 与 `cinder/api/urlmap.py:182-195` (`_set_script_name` / `_munge_path`) 提供带 `SCRIPT_NAME` 改写能力的 URLMap 实现；本仓中它主要由测试夹具 `cinder/tests/unit/api/fakes.py:93` 使用，生产复合应用走 paste 自带的 `paste.urlmap`，这是修改路径匹配逻辑时必须先确认的落点差异。

## 3. 路由装配与错误映射契约表

> 每个端点的请求/响应字段字典见 [接口参考](../contracts/api-reference.md) 与 [其余 v3 接口](../contracts/api/v3-other.md)，本节只列架构侧契约。

| 契约维度 | 实现符号 | 源码锚点 | 约束与影响 |
|---|---|---|---|
| 版本集合 | `root_app_factory` | `cinder/api/__init__.py:27-36` | 关闭 v1 时直接 `del local_conf['/v1']`；若配置项缺失会触发 `KeyError`，新增版本须同步补 `enable_vX_api` 开关 |
| 认证策略 | `pipeline_factory` | `cinder/api/middleware/auth.py:49-61` | 键名由 `CONF.auth_strategy` 决定；新增策略必须在 `etc/cinder/api-paste.ini:24-28` 声明同名管道，否则取不到配置 |
| 资源路由 | `APIRouter._setup_routes` | `cinder/api/v3/router.py:50-194` | `mapper.resource` 挂载 `volumes`、`groups`、`snapshots`、`backups`、`attachments`、`workers`、`resource_filters` 等；`groups` 额外用 `mapper.connect` 注册 `{id}/action` 与 `/groups/action` POST |
| 扩展发现 | `load_standard_extensions` | `cinder/api/extensions.py:252-263` | `os.walk` 扫描扩展目录并跳过 `FILES_TO_SKIP = ['resource_common_manage.py']`（`cinder/api/extensions.py:34`） |
| 扩展鉴权 | `extension_authorizer` / `soft_extension_authorizer` | `cinder/api/extensions.py:323-333`, `cinder/api/extensions.py:336-339` | 动作串由 `api_name`、`extension_name` 与可选 `action` 通过 `_extension:` 与 `:` 拼接（`cinder/api/extensions.py:329-331`），经 `cinder.policy.enforce` 判定 |
| 异常到状态码 | `FaultWrapper._error` | `cinder/api/middleware/fault.py:46-82` | `safe` 为真才回填 `explanation`，否则刻意留空以防敏感信息泄漏；`QuotaError` 不打印异常栈 |
| 资源异常到故障体 | `ResourceExceptionHandler.__exit__` | `cinder/api/openstack/wsgi.py:595-620` | 未识别异常返回 `False` 交还解释器；`VersionNotFoundForAPIMethod` 直接 `raise` 不做转换 |

## 4. 核心源码符号表

| 源码文件 | 核心符号（`行号`） | 职责边界 |
|---|---|---|
| `etc/cinder/api-paste.ini` | `composite:osapi_volume` (`:5-10`), `composite:openstack_volume_api_v3` (`:24-28`), `app:apiv3` (`:58-59`) | 声明式装配版本分发、过滤链与应用工厂 |
| `cinder/cmd/api.py` | `main` (`:47-63`) | 进程级初始化与 launcher 持有 |
| `cinder/service.py` | `WSGIService` (`:533-567`), `WSGIService.start` (`:590-602`), `process_launcher` (`:629-630`) | WSGI 服务器生命周期与 worker 数决策 |
| `cinder/api/__init__.py` | `root_app_factory` (`:27-36`) | 版本开关裁剪与 paste 复合应用创建 |
| `cinder/api/middleware/auth.py` | `pipeline_factory` (`:49-61`), `CinderKeystoneContext` (`:77-81`), `NoAuthMiddleware` (`:117-121`) | 按认证策略构造洋葱链并注入 `cinder.context` |
| `cinder/api/urlmap.py` | `urlmap_factory` (`:156-168`), `URLMap._match` (`:171-180`) | 最长前缀匹配与 `SCRIPT_NAME` 改写 |
| `cinder/api/v3/router.py` | `APIRouter` (`:46-48`), `APIRouter._setup_routes` (`:50-194`) | v3 资源到控制器的映射表 |
| `cinder/api/extensions.py` | `ExtensionDescriptor` (`:37-58`), `ExtensionManager` (`:116-127`), `load_standard_extensions` (`:252-263`) | 扩展契约、加载与策略授权 |
| `cinder/api/middleware/fault.py` | `FaultWrapper` (`:33-44`), `FaultWrapper._error` (`:46-75`), `FaultWrapper.__call__` (`:77-82`) | 兜底异常转 webob fault |
| `cinder/api/openstack/wsgi.py` | `ResourceExceptionHandler` (`:584-620`), `Resource` (`:623-627`), `Fault.__call__` (`:1339-1373`) | 控制器动作异常翻译与故障体序列化 |

## 5. 上下游调用关系

- **上游调用方**：外部客户端经 `cinder-wsgi` 或 `cinder-api` 入口进入；仓内可运行的 HTTP 客户端样例见 `cinder/tests/functional/api/client.py:15-17`（基于 `requests`）。`python-cinderclient` 的 SDK 实现「仓库内未找到字面实现」。
- **仓内下游**：控制器把写操作转成 RPC 调用，落到 [异步作业执行组件](async-job-worker.md) 的 `Service.start()` 所建的 RPC server；具体领域流程见 [调度与业务流程](../business/scheduling.md)。
- **跨组件契约**：错误码与响应体格式由 [错误码字典](../contracts/error-codes.md) 统一约束；部署侧的 worker 数与监听地址见 [部署与运行](../operations/deployment-and-runtime.md)。

## 6. 共变耦合与修改清单

1. 新增或改名 v3 资源：先在 `cinder/api/v3/router.py:50-194` 的 `_setup_routes` 注册 `mapper.resource` / `mapper.connect`，再同步 [接口参考](../contracts/api-reference.md) 的端点清单与 `cinder/api/extensions.py:323-333` 的授权动作串，否则策略侧会拒绝新动作。
2. 调整认证策略名：必须同时改 `CONF.auth_strategy` 取值、`etc/cinder/api-paste.ini:24-28` 的管道行与 `cinder/api/middleware/auth.py:49-61` 的回退键逻辑，三处不一致会直接导致启动期 `KeyError`。
3. 修改异常映射：`cinder/api/middleware/fault.py:46-75` 的 `safe` 判断与 `cinder/api/openstack/wsgi.py:595-620` 的分支顺序需成对审查，避免把本应 403 的授权失败降级为 500；同步更新 [错误码字典](../contracts/error-codes.md)。
4. 变更中间件顺序：以 `etc/cinder/api-paste.ini:24-28` 的字符串顺序为准，`pipeline_factory` 会 `filters.reverse()`（`cinder/api/middleware/auth.py:58-60`），务必验证 `faultwrap` 仍在认证外层，否则认证异常会绕过统一错误体。
5. 若改动 `cinder/api/urlmap.py:171-195` 的路径匹配，须同时核对测试夹具 `cinder/tests/unit/api/fakes.py:93` 与生产 `paste.urlmap` 的行为差异，避免只在单测中通过。
