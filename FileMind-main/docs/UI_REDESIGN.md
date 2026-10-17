# FileMind 界面改造与验收记录

日期：2026-10-15。基于现有代码继续修改，没有重写文件整理核心、AI 请求、API Key 管理和操作历史模块。当前目录没有可用 Git 元数据，因此不能提供与 Claude 修改前的 Git 差异。

## 参考与实现选择

已从原始本地视频提取并查看约 35 秒画面，确认目标为分类结果中的蓝色文件夹图标和层级节点。当前图片附件是账户栏局部及旧整理预览，没有完整登录页参考；新登录页采用与现有主界面协调的浅蓝白色双栏设计，并未声称复制未见过的登录图。

继续采用 Python 3.13、PySide6 Essentials 6.12.0、Qt Widgets，运行依赖和 requirements.txt 没有改变。现有模型/视图、线程和执行确认机制足以实现任务；引入 Qt Quick 或另一套桌面框架会增加两套布局与生命周期的维护工作。本机锁使用 Python 标准库和 Windows 系统 API，不引入密码库或系统凭据管理依赖。requirements-dev.txt 新增 pytest 9.x 的明确安装方式（验收环境为 9.0.2）。

## 目录树

- PlanTargetTree 从 OperationPlan 构建，不读取磁盘目录内容。
- 根目录、分类、子目录都有本地 SVG 图标，目录数量和异常摘要来自计划。
- 显示文件的待执行/异常/冲突状态；表格保留校验状态、建议来源和完整详情。
- 搜索与目录/文件筛选组合使用。路径按组件关系判断，消除了文档/文档2、notes.txt/notes.txt.bak 的误匹配。
- 展开/折叠、横向可拖动分隔栏、完整路径提示与可选择文本仍可用。
- 空计划和存在异常时不能发出执行请求，主窗口的二次确认及执行器安全复检保留。
- 修复 Fusion 分支在 QSS 覆盖后箭头丢失和选中分支蓝色色块：在 drawBranches 中统一绘制缩进背景和展开/折叠 SVG，避免系统选中背景叠加。

## 本机单用户锁屏

- 首次启动设置密码，后续解锁；认证成功前不会创建加载模型配置的主窗口。
- 16 字节随机盐、600,000 次 PBKDF2-HMAC-SHA256，hmac.compare_digest 比较。
- 用户应用数据目录单独存储验证值；随机临时文件在写入前限制权限，再 fsync 和原子替换。
- 记住解锁为七天期限、当前 Windows 用户 DPAPI 保护的随机令牌。密码本身不保存，API Key 存储逻辑未修改。
- 手动锁定、修改密码撤销令牌；忘记密码使用恢复码重置，恢复码轮换且只显示一次。
- 五次失败后有持久化冷却；损坏配置拒绝解锁，不静默退回首次设置。
- 密码派生、配置写入都在 TaskWorker 中。关闭对话框会等待正在进行的原子写入结束。
- 主窗口左下角本机账户菜单与设置页提供锁屏和修改密码；手动锁屏保留原窗口状态，忙碌时提示先停止/完成当前任务。
- 这是应用锁屏，不是文件加密；有权限修改本机程序/配置的人可以绕过应用层防护。密码和恢复码同时遗失时没有应用内免验证重置入口。

## 交互修复

- 未选择目录时禁用扫描/重新扫描，底部状态允许换行，避免小窗口拥挤。
- 设置页可滚动，增加本机锁屏说明和真实行为按钮；共享下拉框补充清晰箭头。
- 最近对话取消 280px 的硬性上限，继续使用独立滚动区域。
- Orbit 长回复按当前视口宽度计算完整高度，消除隐藏滚动条加固定 400px 高度造成的截断；助手消息不再被额外伸缩项挤到半宽。
- Markdown 不自动加载模型回复中引用的本地或远程图片；显式附件流程不变。
- 本轮没有发送真实模型请求，也没有读取实际 API Key 或改动 .env。

## 调研和许可证

Exa 请求返回 402 额度耗尽，改用公开网页搜索与 GitHub 连接器核实官方来源。

| 来源 | 核验信息 | 实际采用方式 |
| --- | --- | --- |
| [Anthropic frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design) | 独立技能目录 LICENSE.txt 为 Apache-2.0；调研时公开可读 | 使用当前已安装 frontend-design 技能的设计方法，没有复制外部组件源代码 |
| [Qt Company agent-skills / qt-qml](https://github.com/TheQtCompanyRnD/agent-skills/blob/main/skills/qt-qml/SKILL.md) | 官方技能元数据版本 1.2、Qt 6.x，许可证 LicenseRef-Qt-Commercial OR BSD-3-Clause；文件最近修改时间 2026-10-08；仓库非归档 | 阅读评估后保留 Widgets；没有引入 QML 源码或运行依赖 |
| [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) | 官方仓库 GPL-3.0，非归档；调研时最近推送 2026-10-11；提供 PySide6 版本 | 未安装、未复制；避免额外控件框架和许可证义务 |
| 本项目 filemind-desktop-ui skill | 用 skill-creator 初始化并按本项目实际问题编写 | 存于 .agents/skills/，记录计划树、锁屏、长消息与隔离验收的约束 |

design-system 没有作为独立外部技能安装；沿用主题文件和字体策略建立本项目界面规范。新 SVG 箭头与图形为本次自绘。没有下载或执行第三方安装脚本。

密码和记住状态的技术依据：[Python hashlib 文档](https://docs.python.org/3.13/library/hashlib.html#hashlib.pbkdf2_hmac)、[Microsoft CryptProtectData 文档](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)。

## 修改文件清单

| 文件 | 变化 |
| --- | --- |
| main.py | 正式入口传播退出码 |
| filemind/storage/local_lock.py | 密码验证、恢复、限速、私有原子写入、DPAPI 令牌 |
| filemind/ui/startup.py | 启动前认证、手动锁屏控制器 |
| filemind/ui/dialogs/local_lock.py | 首次设置/解锁/修改/恢复码页面 |
| filemind/ui/dialogs/plan_preview.py | 层级筛选、搜索、摘要与安全按钮 |
| filemind/ui/widgets/plan_tree.py | 图标目录树、数量与冲突展示 |
| filemind/ui/widgets/file_table.py | 长名称与单元格完整提示 |
| filemind/ui/widgets/chat_message.py | 长回复布局、阻止自动图片资源加载 |
| filemind/ui/main_window.py | 账户菜单、锁屏信号、对话列表空间分配 |
| filemind/ui/pages/organize_page.py | 目录选择与扫描按钮状态、小窗口状态文本 |
| filemind/ui/pages/settings_page.py | 本机锁屏卡片、状态文本换行 |
| filemind/ui/styles/theme.py | 锁屏、菜单、焦点、提示与树分支统一样式 |
| filemind/ui/styles/icons.py | 目录图标、锁和警告图标 |
| filemind/ui/assets/tree-closed.svg、tree-open.svg | 展开/折叠矢量箭头 |
| tests/conftest.py | 统一 Qt 测试退出生命周期，避免先销毁 QApplication |
| tests/test_plan_tree.py | 路径精确筛选、层级图标、冲突、空计划 |
| tests/test_local_lock.py | 哈希、恢复、冷却、令牌、权限及 DPAPI |
| tests/test_lock_ui.py | 初始设置、错误状态、后台响应、关闭与启动门控 |
| tests/test_lock_controller.py | 手动锁屏联动、忙碌拒绝、损坏配置 |
| tests/test_chat_layout.py | 长回复重排与模型图片资源隔离 |
| tools/review_ui.py | 临时数据 UI 启动与截图工具，不读真实凭据 |
| .agents/skills/filemind-desktop-ui/ | 后续界面开发技能及其元数据 |
| README.md、requirements-dev.txt、.gitignore | 使用说明、测试安装、验收产物忽略 |
| docs/UI_REDESIGN.md | 本说明 |

## 验收

基线：本次修改前重新运行 pytest，80 passed，24 subtests passed（13.71 秒）。新增测试不会替代原测试，原测试文件没有删除或降低断言。

最终完整运行：`py -3.13 -m pytest -q`，**104 passed，24 subtests passed（28.66 秒）**，进程退出码 0。`compileall` 和新增模块导入检查通过；本项目 UI skill 通过 quick_validate。

正式启动入口还进行了隔离冒烟检查：实际创建 QApplication、显示首次设置页并定时取消，验证退出码为 0，且没有构造加载模型配置的主窗口。记住解锁的 Windows DPAPI 测试使用本次生成的随机令牌，不访问 Windows Credential Manager。

早期新增预览测试的断言虽然通过，但退出时发生 Qt 析构异常。tests/conftest.py 现明确保证先结束线程、销毁测试窗口，再释放 QApplication；最终完整测试进程正常退出。

实际检查：920×660 本机首次设置页在 Windows 上启动，按 Enter 提交空密码会显示长度要求；1024×700 整理预览在 Windows 上检查图标、层级和展开/折叠；1024×700 与 1280×850 的整理、Orbit、设置等状态用 Qt 实际渲染和截图核对。模型网络请求没有实测，验收对话为生成数据。

全部界面测试只使用工具生成的临时文件与会话。没有自动整理用户真实目录。截图保存在 .artifacts/ui-review/，已加入忽略列表。

后续仍需用户用自己的实际模型服务验证网络与模型权限；高 DPI 的不同显示缩放、多个屏幕环境和大规模文件夹可进一步补充人工验证。缺少 Git 元数据的现状未修改。
