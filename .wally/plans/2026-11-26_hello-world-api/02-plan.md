# 02. Plan

## 方案与改动范围

关联需求：`GET /hello` 返回 `{"message": "Hello, World!"}`，无需鉴权（cinder v3）。

最小改动文件清单：
1. 新增 `cinder/api/v3/hello.py`：定义 `HelloController(wsgi.Controller)`，`index(self, req)` 直接返回 `{"message": "Hello, World!"}`，不调用 `cinder.policy.enforce`；提供 `create_resource()`。
2. 修改 `cinder/api/v3/router.py`：新增 `from cinder.api.v3 import hello`，并在 `_setup_routes` 中增加 `mapper.connect("hello", "/hello", controller=..., action="index", conditions={"method": ["GET"]})`。
3. 新增 `cinder/tests/unit/api/v3/test_hello.py`：UT 覆盖正向返回、方法限制、返回结构。

无新增依赖。风险等级：低（局部新增、可逆、不改现有接口与数据结构）。

## 调用链与兼容性

- 调用链：HTTP `GET /v3/.../hello` → `cinder.api.v3.router.APIRouter._setup_routes` 注册的路由 → `HelloController.index` → 返回 dict，由 wsgi 层序列化为 JSON。
- 兼容性：仅新增路由与控制器，不影响现有资源；不引入 microversion 变更。
- 无需鉴权：控制器内不调用 policy；框架中间件行为不变。
- 副作用：无数据库、无 RPC、无外部调用。
- 回滚：删除新增控制器文件，撤销 `router.py` 的导入与路由注册行即恢复原行为。

## UT 设计

- H1 正向：构造 GET 请求调用 `index`，断言返回 `{"message": "Hello, World!"}`，HTTP 200。
- H2 方法限制：对 `/hello` 发起 POST，断言路由不匹配（404/405），仅 GET 生效。
- H3 返回结构：断言返回值为 dict，仅含 `message` 键且值为 `Hello, World!`（ASCII 场景，无中文数据）。
- H4 无鉴权：在不提供鉴权 context 的情况下调用仍返回预期结果，证明控制器未触发 policy 检查。

测试位置：`cinder/tests/unit/api/v3/test_hello.py`。执行入口：项目现有 pytest/tox 单测入口（实现阶段以实际可用命令为准）。

## IT 设计（六步适用）

`execution.json` 中 deploy/it 均未配置，按规则自动 SKIPPED，不声称端到端验证；仅保留代码层 UT。

## 风险与完成结论

- 关键决定：挂在 cinder v3、不启用 policy、返回固定 JSON。
- 未覆盖边界：真实 WSGI 服务部署下的端到端请求（未配置环境）。
- 无额外授权需求；回滚方案明确；UT 已先于实现设计。

## 知识库证据

- 源码核验：`cinder/api/v3/router.py`、`cinder/api/v3/limits.py`、`cinder/api/v3/messages.py`、`README.rst`。
- 预计受影响知识页：无（未发现 `.wally/docs/`，现有 README 描述项目整体，不因新增一个 API 接口而失真）。
- 无 API/SQL 契约文档需要同步；无缺口需补建文档骨架。
