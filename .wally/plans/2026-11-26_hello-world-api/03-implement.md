# 03. Implement + UT + Docs

## 项目规则

已检查 `cinder/.wally/`，无 `.wally/rules/` 目录，无额外项目规则。按 Core `core/gates.md` 与工作区 `AGENTS.md` 执行：不修改目标仓库 `AGENTS.md`、不写入 `.wally/versions/`、不硬编码内部平台地址、密钥不落库、SQL 参数化（本次改动不涉及 SQL/密钥/内部地址）。

## 实际改动与 Plan 差异

- 按 Plan 完成：新增 `cinder/api/v3/hello.py`（`HelloController.index` 返回固定 JSON，不调用 policy）；修改 `cinder/api/v3/router.py` 注册 `GET /hello`；新增 `cinder/tests/unit/api/v3/test_hello.py`。
- 差异 1：额外修改 `.gitignore` 加 `!.wally/` 例外。Plan 未列，但 `builtin-policy` 要求 `.wally/plans/` 纳入 Git 跟踪，原 `/.` 规则会忽略 `.wally/`；已在写前门禁放开后执行。
- 差异 2：测试使用标准 `unittest.TestCase` 而非 `cinder.test.TestCase`。后者 `setUp` 调用的 `conf_fixture.set_defaults` 依赖已移除的 `rpc_backend` option，在现有 `oslo.config` 下抛 `NoSuchOptError`。
- 差异 3：新增第 5 个用例 `test_create_resource`，用于覆盖 `create_resource()` 分支。
- 无范围扩大；回滚方案与 Plan 一致。

## Red → Green → Refactor

- **Red（实现前）**：命令 `/data/workspace/wally-open-8892/.venv/bin/python3 -m unittest cinder.tests.unit.api.v3.test_hello`，退出码 `1`，`Ran 4 tests ... FAILED (failures=4)`；失败均为 `AssertionError: unexpectedly None : hello 模块缺失`，属预期断言失败（非环境/语法失败）。
- **Green（实现后）**：同命令，退出码 `0`，`Ran 5 tests ... OK`（5/5）。
- **Refactor**：无需重构；控制器为最小实现，无重复或可抽取逻辑。

## UT 与增量覆盖率

- 环境：专用 venv `/data/workspace/wally-open-8892/.venv/bin/python3`。为兼容老代码调整本地测试依赖（`ddt`、`retrying`、`mock`、`testrepository`、`oslotest<4`，降级 `SQLAlchemy` 1.3.24、`keystonemiddleware` 5.2.0、`oslo.db` 5.1.0）；未改动项目 requirements 文件。
- 增量覆盖率命令：`python3 -m coverage run --branch --include='*hello.py' -m unittest cinder.tests.unit.api.v3.test_hello`，随后 `python3 -m coverage report -m --include='*hello.py'`。
- 结果：`cinder/api/v3/hello.py` 6 stmts / 0 miss / 0 branch / **100%** 覆盖。
- 未覆盖边界：`router.py` 新增路由注册行未被执行——`APIRouter` 实例化受本机 `oslo.context` 版本不兼容影响（`RequestContext.__init__()` 参数不匹配），该行仅做静态 diff 复核，未计入覆盖率通过结论。项目未配置增量门槛，按实际增量结果记录。

## 缺陷回归（适用时）

不适用（功能新增，非缺陷/性能任务）。

## Docs

按 `core/knowledge.md` 读取 `README.rst` 与源码核实；项目无 `.wally/docs/`。新增 v3 hello 接口不影响现有 API 契约/SQL 文档，README 为项目整体介绍、不因示例接口失真 → 无需更新。无过期页、无补建骨架需求。

## 增量 CR

- 规则：无 `.wally/rules/`；按 Core gates 与工作区 `AGENTS.md`。
- 最终 diff 范围：`.gitignore`（1 行）、`cinder/api/v3/router.py`（导入 + 路由注册共 7 行）、新增 `hello.py` 与 `test_hello.py`、`.wally/plans/2026-11-26_hello-world-api/` 产物。
- 发现并修复：测试中 `_REPO_ROOT` 层级在 nova 侧修正（本仓库测试无此问题）；无业务缺陷。
- 未解决风险：真实 WSGI 端到端未验证；`APIRouter` 运行时路由表未验证。无阻断性缺陷。

## 完成结论

TDD 通过（Red 为断言失败、Green 5/5）、增量覆盖率通过（100%）、Docs 通过（无需更新）、增量 CR 通过（无阻断缺陷）；Deploy/IT 自动 SKIPPED，端到端行为未验证。

## 知识库证据

实际读取：`README.rst`、`cinder/api/v3/router.py`、`cinder/api/v3/limits.py`、`cinder/api/v3/messages.py`、`cinder/tests/unit/api/v3/test_limits.py`、`.gitignore`。未发现 `.wally/docs/`；使用系统默认 SOP，已核对现有文档与源码。
