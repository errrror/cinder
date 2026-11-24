---
kind: component
scope: cinder-cli-and-wsgi-entry
status: draft
origin: generated
source_paths:
  - setup.cfg
  - cinder/cmd/manage.py
  - cinder/cmd/rtstool.py
  - cinder/cmd/volume_usage_audit.py
  - cinder/wsgi/wsgi.py
  - cinder/tests/functional/api/client.py
symbols:
  - main
  - CATEGORIES
  - methods_of
  - add_command_parsers
  - fetch_func_args
  - create
  - parse_optional_create
  - initialize_application
  - OpenStackApiException
upstream: [architecture/index.md, architecture/api-service.md]
downstream: [contracts/api-reference.md, operations/dev-and-test.md]
---

# Cinder 命令行与 Web 网关入口组件

Cinder 仓库没有前端界面，交互入口由 `setup.cfg` 的 `console_scripts` 与 `wsgi_scripts` 声明：七个命令行二进制加一个 `cinder-wsgi` 网关脚本。管理类命令通过 `cfg.SubCommandOpt` 在运行时反射出「类别 → 动作 → 参数」三层结构，运维类命令 `cinder-rtstool` 则手写参数分派直接操作 `rtslib_fb`；对外 SDK 由独立项目提供，本仓只包含基于 `requests` 的功能测试客户端。

## 1. 可执行入口全景表

| 命令 / 脚本 | 入口符号 | 源码锚点 | 交互特征 |
|---|---|---|---|
| `cinder-api` | `cinder.cmd.api:main` | `setup.cfg:49` | 启动 [WSGI 接入组件](api-service.md) |
| `cinder-backup` | `cinder.cmd.backup:main` | `setup.cfg:50` | 启动备份后台服务 |
| `cinder-manage` | `cinder.cmd.manage:main` | `setup.cfg:51` | 11 类子命令，反射式分派 |
| `cinder-rootwrap` | `oslo_rootwrap.cmd:main` | `setup.cfg:52` | 外部包提供的提权代理 |
| `cinder-rtstool` | `cinder.cmd.rtstool:main` | `setup.cfg:53` | 本地 LIO target 配置工具 |
| `cinder-scheduler` | `cinder.cmd.scheduler:main` | `setup.cfg:54` | 启动调度后台服务 |
| `cinder-volume` | `cinder.cmd.volume:main` | `setup.cfg:55` | 启动卷后台服务 |
| `cinder-volume-usage-audit` | `cinder.cmd.volume_usage_audit:main` | `setup.cfg:56` | 用量审计任务 |
| `cinder-wsgi` | `cinder.wsgi.wsgi:initialize_application` | `setup.cfg:57-58` | 返回 paste 应用给外部 Web 服务器 |

`cinder-volume-usage-audit` 的 `main` (`cinder/cmd/volume_usage_audit.py:197-207`) 先 `objects.register_all()` 与 `rpc.init(CONF)`，再用 `utils.last_completed_audit_period()` 得到审计区间并交 `_time_error` 校正，随后由 admin context 遍历对象分别触发 `_create_action` / `_delete_action`（`:190-194`）。

```mermaid
graph LR
    A["console_scripts 入口"] --> B["cinder-manage main"]
    B --> C["CATEGORIES 十一类"]
    C --> D["methods_of 反射动作"]
    D --> E["fetch_func_args 装配参数"]
    E --> F["action_fn 执行"]
```

## 2. cinder-manage 子命令分发表

`CATEGORIES` (`cinder/cmd/manage.py:699-711`) 共 11 类，命令树在 `add_command_parsers` (`:727-744`) 中动态生成：对每类实例化命令对象，用 `methods_of` (`:714-724`) 反射所有非下划线开头的可调用方法，再依据方法上的 `args` 属性逐个 `parser.add_argument`。

| 类别键 | 命令类 | 典型动作来源 | 源码锚点 |
|---|---|---|---|
| `backup` | `BackupCommands` | 备份相关管理动作 | `cinder/cmd/manage.py:700` |
| `config` | `ConfigCommands` | 配置转储 | `cinder/cmd/manage.py:701` |
| `cluster` | `ClusterCommands` | 集群管理 | `cinder/cmd/manage.py:702` |
| `cg` | `ConsistencyGroupCommands` | 一致性组管理 | `cinder/cmd/manage.py:703` |
| `db` | `DbCommands` | 数据库迁移与同步 | `cinder/cmd/manage.py:704` |
| `host` | `HostCommands` | 主机能力管理 | `cinder/cmd/manage.py:705` |
| `logs` | `GetLogCommands` | 日志抓取 | `cinder/cmd/manage.py:706` |
| `service` | `ServiceCommands` | 服务状态与禁用 | `cinder/cmd/manage.py:707` |
| `shell` | `ShellCommands` | `bpython` / `ipython` / `python` / `run_script` | `cinder/cmd/manage.py:97-164`, `cinder/cmd/manage.py:708` |
| `version` | `VersionCommands` | 版本输出 | `cinder/cmd/manage.py:709` |
| `volume` | `VolumeCommands` | 卷管理动作 | `cinder/cmd/manage.py:710` |

```text
cinder-manage -> cinder/cmd/manage.py:781-810 main()
  ├─ objects.register_all() (:782)
  ├─ CONF.register_cli_opt(category_opt) (:784)，category_opt 定义于 :747-749
  ├─ [if len(sys.argv) < 2] 打印 CATEGORIES 列表并 sys.exit(2) (:786-793)
  ├─ CONF(sys.argv[1:], project='cinder') + logging.setup(CONF, "cinder") (:795-799)
  │    ├─ [except ConfigDirNotFoundError / ConfigFilesNotFoundError] 打印路径并 sys.exit(2) (:800-806)
  ├─ fn = CONF.category.action_fn (:808)
  ├─ fn_kwargs = fetch_func_args(fn) (:809)
  │    └─ 读取装饰器记录的 args，键名取自 kwargs['dest'] 或 get_arg_string(args[0]) (:771-778, :752-768)
  └─ fn(**fn_kwargs) (:810)
```

`args` 装饰器 (`cinder/cmd/manage.py:90-94`) 把参数声明附加到方法对象上，`get_arg_string` 会剥离 `-` / `--` 前缀并把剩余连字符替换为下划线（`:752-768`），这决定了 `fetch_func_args` 传给动作函数的键名。

## 3. cinder-rtstool 子命令与执行链

`cinder-rtstool` 不走 `oslo_config` 子命令框架，而是在 `main(argv=None)` (`cinder/cmd/rtstool.py:268-351`) 中按 `argv[1]` 逐项比对并校验参数个数，长度不足即 `usage()`。

```text
cinder-rtstool main (cinder/cmd/rtstool.py:268-351)
  ├─ create 的五个位置参数 backing_device, name, userid, password, iser_enabled 加可选参数 (:275-294)
  │    ├─ parse_optional_create (:243-259) -> portals_ips / portals_port / initiator_iqns
  │    └─ create (:43-110) -> RTSRoot -> BlockStorageObject -> Target(iscsi) -> TPG -> LUN -> NodeACL/CHAP -> NetworkPortal
  ├─ add-initiator 的四个位置参数 target_iqn, userid, password, initiator_iqn (:296-305)
  │    └─ _lookup_target (:113-124) -> next(target.tpgs) -> NodeACL(mode='create') 写 chap_userid / chap_password (:127-141)
  ├─ delete-initiator / get-targets / delete (:307-324)
  ├─ verify -> verify_rtslib() (:326-330)
  └─ save / restore (:332-346)
       ├─ save_to_file (:200)
       └─ restore_from_file (:229)
```

| 分派键 | 必填参数 | 处理函数（`路径:行号`） | 副作用与失败语义 |
|---|---|---|---|
| `create` | 5 个位置参数加可选 `-a` / `-p` | `create` (`cinder/cmd/rtstool.py:43-110`) | 未挂载 `configfs` 时提示并抛 `RTSLibError`（`:49-53`）；IPv6 绑定失败依 `ips_allow_fail` 降级为警告（`:83-101`） |
| `add-initiator` | `target_iqn`、`userid`、`password`、`initiator_iqn` | `add_initiator` (`cinder/cmd/rtstool.py:127-141`) | 已存在相同 `node_wwn` 的 ACL 时直接返回，不重复创建（`:130-134`） |
| `delete` / `get-targets` | `iqn` 或无 | `delete` (`:161`), `get_targets` (`:155`) | 目标不存在时 `_lookup_target` 抛 `RtstoolError`（`:124`） |
| `verify` | 无 | `verify_rtslib` (`:174`) | 供 Cinder 校验脚本可调用且 `rtslib_fb` 版本足够新（`:327-328`） |
| `save` / `restore` | 可选文件路径 | `save_to_file` (`:200`), `restore_from_file` (`:229`) | 参数超过 3 个即 `usage()`，成功返回 0 |

`create` 的可选参数解析依赖前缀约定：`-a` 后接逗号分隔 IP 列表写入 `portals_ips`，`-p` 后接整数端口写入 `portals_port`，其余位置参数整串作为 `initiator_iqns`（`cinder/cmd/rtstool.py:243-259`）；未给 IP 时绑定 `('0.0.0.0', '[::0]')`，默认端口 `3260`（`:44`, `:84-87`）。

## 4. Web 网关与对外接口入口边界

`cinder-wsgi` 入口 `initialize_application()` (`cinder/wsgi/wsgi.py:38-46`) 依次执行 `objects.register_all()`、`CONF(sys.argv[1:], project='cinder')`、`logging.setup`、`config.set_middleware_defaults()`、`rpc.init(CONF)`，最后返回 `wsgi.Loader(CONF).load_app(name='osapi_volume')`。它与 `cinder-api` 共用同一 paste 配置名，因此路由与中间件行为完全一致，细节见 [WSGI 接入组件](api-service.md)。

| 入口形态 | 仓内实现 | 源码锚点 | 边界说明 |
|---|---|---|---|
| Web 网关脚本 | `initialize_application` | `cinder/wsgi/wsgi.py:38-46` | 仅返回 WSGI 应用，不自带监听循环，由外部 WSGI 服务器托管 |
| HTTP 客户端样例 | `OpenStackApiException` 及子类 | `cinder/tests/functional/api/client.py:15-17`, `:25-49` | 基于 `requests` 的功能测试客户端，按状态码派生 `OpenStackApiException401` / `404` |
| 生产对外 SDK | 「仓库内未找到字面实现」 | `setup.cfg:48-58` 无相关入口点 | `python-cinderclient` 位于独立项目，本仓只提供 [接口参考](../contracts/api-reference.md) 所述的 HTTP 契约 |

## 5. 核心源码符号表

| 源码文件 | 核心符号（`行号`） | 职责边界 |
|---|---|---|
| `setup.cfg` | `console_scripts` (`:48-56`), `wsgi_scripts` (`:57-58`) | 可执行入口注册中心 |
| `cinder/cmd/manage.py` | `ShellCommands` (`:97-164`), `CATEGORIES` (`:699-711`), `methods_of` (`:714-724`), `add_command_parsers` (`:727-744`), `get_arg_string` (`:752-768`), `fetch_func_args` (`:771-778`), `main` (`:781-810`) | 管理命令的反射式分派框架 |
| `cinder/cmd/rtstool.py` | `create` (`:43-110`), `_lookup_target` (`:113-124`), `add_initiator` (`:127-141`), `parse_optional_create` (`:243-259`), `_canonicalize_ip` (`:262-265`), `main` (`:268-351`) | iSCSI target 本地配置工具 |
| `cinder/cmd/volume_usage_audit.py` | `main` (`:197-207`) | 用量审计入口与审计区间计算 |
| `cinder/wsgi/wsgi.py` | `initialize_application` (`:38-46`) | 外部 WSGI 服务器装配钩子 |
| `cinder/tests/functional/api/client.py` | `OpenStackApiException` (`:25-40`), `OpenStackApiException401` (`:43-44`), `OpenStackApiException404` (`:47-49`) | 测试侧 HTTP 调用与错误包装 |

## 6. 共变耦合与修改清单

1. 新增管理子命令：在 `cinder/cmd/manage.py` 定义命令类与非下划线方法 → 用 `@args` 声明参数 → 把类注册进 `CATEGORIES` (`cinder/cmd/manage.py:699-711`)；`methods_of` (`:714-724`) 会自动发现动作，无需手改分派代码，但需在 [接口参考](../contracts/api-reference.md) 同步记录。
2. 修改 `@args` 前缀解析：`get_arg_string` (`cinder/cmd/manage.py:752-768`) 的连字符转下划线规则会改变 `fetch_func_args` (`:771-778`) 的键名，必须成对检查所有命令类的参数声明，否则运行时抛 `TypeError`。
3. 调整 `cinder-rtstool` 参数：`main` (`cinder/cmd/rtstool.py:268-351`) 用位置下标硬编码取值，新增可选参数需同时改 `parse_optional_create` (`:243-259`) 与对应长度校验分支；`verify` 子命令的调用方在 Cinder 驱动侧，改动后要核对 [开发测试指引](../operations/dev-and-test.md)。
4. 变更网关初始化：`initialize_application` (`cinder/wsgi/wsgi.py:38-46`) 与 `cinder/cmd/api.py:47-63` 的 `main` 必须保持相同的 `objects.register_all()` 与 `rpc.init(CONF)` 次序，否则其一会缺失 OVO 注册或 RPC 通道。
5. 静态资源与 SDK 版本：本仓 `static/` 不属于本组件，且无生产 SDK 代码；若对外新增入口点，先在 `setup.cfg:48-58` 注册，再同步 [部署与运行](../operations/deployment-and-runtime.md) 的路径说明。
