---
kind: operations
scope: pitfalls-and-adr
status: draft
origin: generated
source_paths: [cinder/api/__init__.py, cinder/common/config.py, cinder/api/urlmap.py, cinder/volume/configuration.py, cinder/volume/api.py, cinder/api/v3/volumes.py, cinder/api/v2/volumes.py, cinder/api/middleware/fault.py, cinder/api/contrib/admin_actions.py, cinder/service.py, contrib/block-box/README.md, cinder/api/v3/groups.py, cinder/exception.py]
symbols: [root_app_factory, BackendGroupConfiguration.__getattr__, FaultWrapper._error, VolumeAdminController.validate_update, CinderException, _check_default_cgsnapshot_type]
upstream: [INDEX.md, overview/system-architecture.md]
downstream: [operations/deployment-and-runtime.md, contracts/configuration.md]
---

# 关键架构决策（ADR）、修改高危雷区与存量死路径警示

本页汇总决定本仓结构的硬性设计权衡、Agent 改代码时易误踩的隐式耦合，以及源码中仍存在但**当前主链路未挂载**的历史代码。接口全貌见 [入向接口总表](../contracts/api-reference.md)，配置默认值见 [配置项全集](../contracts/configuration.md)，运行期边界见 [部署、进程拓扑与持久化目录契约](deployment-and-runtime.md)。

## 1. 核心架构决策与不可违背的工程约束（Key ADRs）

| 编号 | 决策主题 | 核心实现机制与源码锚点 | Agent 修改时必须遵守的硬约束 |
|---|---|---|---|
| `ADR-01` | v1 API 默认关闭、逐步退场 | `root_app_factory` 在 `enable_v1_api=False`（默认）时从 `local_conf` 删除 `/v1`；开启时打弃用告警 (`cinder/api/__init__.py:27-33`、`cinder/common/config.py:85-88`) | 勿把 v1 当作当前主入口改业务逻辑；v1 路由源码仍在 `cinder/api/v1/router.py:39-92`，但默认不可达 |
| `ADR-02` | v2 仍挂载但已弃用、v3 为演进主线 | `enable_v2_api=True`（默认）但标 `deprecated_for_removal`；v3 默认 `True` 且承载微版本 (`cinder/common/config.py:89-95`) | 新字段优先在 v3 控制器实现；改 v2 会经继承影响 v3（如 `VolumeController` 继承 v2，`cinder/api/v3/volumes.py:50-57`） |
| `ADR-03` | 后端配置双层回退 | `BackendGroupConfiguration` 把 opt 注册进 `[backend_defaults]`，后端组默认值改写为 `None`，读取时 None 才回退共享组 (`cinder/volume/configuration.py:74-135`) | 不能用 `CONF` 的具体选项 直接读后端选项；必须经配置 shim，否则绕过回退 |
| `ADR-04` | PasteDeploy + WSGI 多进程部署 | ini 定义 `osapi_volume` composite 与 pipeline (`etc/cinder/api-paste.ini:5-75`)；Apache 用 `WSGIDaemonProcess processes=2 threads=1` (`etc/cinder/api-httpd.conf:4-7`) | 中间件顺序与异常包装强相关，改序前先在单测/Fakes 中验证 |
| `ADR-05` | 异常安全标志控制信息泄露 | `CinderException.safe=False` 默认；`FaultWrapper._error` 仅在 `safe=True` 时回显 msg (`cinder/exception.py:84-87`、`cinder/api/middleware/fault.py:46-75`) | 新异常不得随意设 `safe=True`；`NotFound`/`QuotaError` 是有意的安全例外 (`cinder/exception.py:326-329`、`614-618`) |
| `ADR-06` | 启动日志口令脱敏 | `service.wait` 对含 `_password`/`_key` 或 URI 型 `sql_connection` 的配置项打印 `FLAG SET` (`cinder/service.py:647-659`) | 新增秘密配置须命名含 `_key`/`_password` 或用 `secret=True`，否则明文入日志 |
| `ADR-07` | 微版本门禁控制字段可见性 | `@wsgi.Controller.api_version`、`req_version.matches(...)` 散落于各控制器 (`cinder/api/v3/volumes.py:68`、`211-221`、`cinder/api/v3/attachments.py:29-31`) | 新增响应字段必须配微版本门槛，老客户端不得看到新字段 |
| `ADR-08` | 特权命令经 rootwrap 白名单 | `rootwrap_config` 默认 `/etc/cinder/rootwrap.conf` (`cinder/common/config.py:145-148`)，过滤器目录仅 root 可写 (`etc/cinder/rootwrap.conf:1-27`) | 禁止拼接 shell 命令绕过过滤器；新增命令须登记过滤器与 `exec_dirs` |

## 2. 修改高危雷区与隐式耦合表

| 高危源码位置（`路径:行号`） | 涉及符号 | 隐蔽陷阱机制 | 安全修改标准动作 |
|---|---|---|---|
| `cinder/api/__init__.py:27-36` | `root_app_factory` | 生产使用 `paste.urlmap.urlmap_factory`，**不是** `cinder/api/urlmap.py` 的同名自定义工厂；改后者对运行态毫无影响 | 改路由挂载先改 ini 与 `root_app_factory`；自定义 urlmap 仅用于测试 |
| `cinder/volume/configuration.py:97-111` | `BackendGroupConfiguration._ensure_config_values` | 后端组默认值被 `CONF.set_default(opt.name, None, ...)` 改写为 None，目的是判定「是否显式设置」 | 修改注册顺序会破坏回退判定；改后跑 `cinder/tests/unit/test_volume_configuration.py` |
| `cinder/api/contrib/admin_actions.py:45-51`、`151-157`、`302-304` | `valid_status` | 基类与 volume/backup 子类各自维护状态集合，`VolumeAdminController` 用 `union` 扩充；遗漏合法状态会使 reset 返回 400 | 新增状态须同时更新所有相关集合并补对应 contrib 单测 |
| `cinder/api/middleware/fault.py:53-75` | `FaultWrapper._error` | `status=None` 回落 500；`safe=False` 时 explanation 置空；headers 仅当经此中间件才透传 | 控制器直接抛 `webob` 异常会绕过 `safe` 逻辑，需评估是否改用 `exception.*` |
| `cinder/volume/api.py:228-233`、`cinder/api/v3/volumes.py:231-237`、`cinder/api/v2/volumes.py:182-188` | `source_replica` 快速失败 | 三处独立重复同一拒绝逻辑；只改一处会导致某版本仍接受废弃参数 | 三处同步修改并补单测；这是 replication v1 的刻意保留入口 |
| `cinder/service.py:653-655` | `wait` 日志脱敏 | 判断依赖配置项**命名约定**而非 `secret=True` 元数据 | 新秘密项命名须含 `_password`/`_key` |
| `cinder/api/v3/groups.py:49-54`、`186`、`221`、`295`、`364` | `_check_default_cgsnapshot_type` | 默认 cgsnapshot 类型被保留用于 CG→group 迁移，命中即拒绝操作，错误信息与直觉不符 | 操作组资源报 400 时先核对该守卫，勿盲目改业务逻辑 |

## 3. 存量死路径与历史兼容保留代码警示

| 存量代码位置（`路径:行号`） | 符号 / 配置 / 目录 | 当前真实状态 | 当前真正生效的主入口 |
|---|---|---|---|
| `cinder/api/v1/router.py:39-92` | v1 全套路由 | 默认不挂载（`enable_v1_api=False`，`cinder/api/__init__.py:32-33`）；仅历史兼容 | `cinder/api/v3/router.py:46-194` |
| `cinder/api/v2/router.py:45-94` | v2 全套路由 | 默认仍挂载但已标弃用 (`cinder/common/config.py:89-92`) | `cinder/api/v3/router.py:46-194` |
| `cinder/api/urlmap.py:156-209` | `urlmap_factory` / `URLMap._match` / `_path_strategy` | 自定义 URLMap 仅被 `cinder/tests/unit/test_api_urlmap.py`、`cinder/tests/unit/api/fakes.py` 引用，生产未挂载 | `cinder/api/__init__.py:27-36` 调用 `paste.urlmap.urlmap_factory` |
| `cinder/volume/api.py:222-233` 等多处 | `source_replica` 参数 | replication v1 已移除，参数保留仅用于**快速失败**并给出 `InvalidInput`：创建卷时传入即拒绝 | 复制能力走 group replication Action (`cinder/api/v3/groups.py:376-481`) |
| `cinder/common/config.py:56-61`、`186-215` | `glance_api_version`、`os_privileged_user_*` | 均标 `deprecated_for_removal`（自 11.0.0），仅兼容旧部署 | `[nova]` 段配置特权用户；Glance v2 为默认（`cinder/common/config.py:56-61`） |
| `contrib/block-box/README.md:1-40`、`contrib/block-box/docker-compose.yml:1-86` | block-box 容器化 demo | 仓库内的演示资产（noauth + loci 镜像），不参与 Python 包构建（`setup.cfg:23-25` 仅 `packages = cinder`） | 生产部署由各发行商/Ansible 等外部体系负责；参见 [部署产物清单](deployment-and-runtime.md) |
| `cinder/api/v3/groups.py:49-54` | 默认 cgsnapshot group type 守卫 | 为迁移遗留的一致性组保留的拒绝逻辑，非通用业务规则 | 新建组走 `groups.create` (`cinder/api/v3/groups.py:200-244`) |
| `cinder/exception.py:1331-1333` | `NotSupportedOperation` | 继承 `Invalid` 但显式覆写 `code=405`，与大多数 400 类异常不同 | 维护状态码映射表见 [错误码字典](../contracts/error-codes.md) |

## 4. 共变耦合与修改清单

| 变更点 | 联动文件 | 隐式陷阱与标准动作 |
|---|---|---|
| 启用/停用 v1/v2 | `cinder/common/config.py:85-95`、`cinder/api/__init__.py:27-36`、`etc/cinder/api-paste.ini:5-28`、`cinder/api/v1/router.py` | 开关同时影响挂载与日志告警；v1 客户端在关闭后请求 `/v1` 将 404 |
| 调整配置回退 | `cinder/volume/configuration.py:49-138`、`cinder/common/config.py:218-247`、`cinder/opts.py:212-408` | 改 shim 必须重跑 `tox -egenconfig`/`-egenopts`（[构建与测试手册](dev-and-test.md)） |
| 清理 replication v1 残留 | `cinder/volume/api.py:228-233`、`cinder/api/v3/volumes.py:231-237`、`cinder/api/v2/volumes.py:182-188` | 三处快速失败需成套删除或成套保留；单独删除会让某版本 API 接收无效参数 |
| 改 rootwrap/特权路径 | `cinder/common/config.py:145-148`、`etc/cinder/rootwrap.conf:1-27`、`contrib/block-box/docker-compose.yml:61-66` | 容器与裸机两条路径的特权边界不同，改动需双环境验证 |
| 改异常状态码 | `cinder/exception.py:84-87`、`166-190`、`326-329`、`614-618`、`1331-1333`、`cinder/api/middleware/fault.py:46-75` | 状态码、safe、headers 三者共同决定对外表现，需同步 [错误码字典](../contracts/error-codes.md) 与 runbook 症状 A/B |

请求全链路的权威入口见 [调用链全景](../overview/callchain-panorama.md)；服务边界复核由主 Agent 在 `operations/boundary.md` 统一维护。
