# FileMind 工作区改造验收

日期：2026-10-15。本轮以实际源码和新运行的测试为依据，保留 Claude 已完成的合理实现。目录没有可用的 Git 元数据，未初始化仓库，也无法提供基于提交的差异。

## 实现与数据流

继续使用 Python 3.13 + PySide6 Essentials 6.12.0 / Qt Widgets。未增加运行依赖、未修改构建配置；保留现有 OpenAI SDK 2.54.0、模型配置、密钥存储、执行器和撤销逻辑。Qt 原生图像编码器、PDF 写入器和 Python 标准库足以支持第一版真实转换。

文件整理流程：选择目录 → 后台只读扫描 → 导入清单 → 选择预设/编辑规则 → 本地分类或真实 AI 服务接口 → 本地计划校验 → 主工作区目录树 → 独立预览 → 明确确认 → 执行器 → 历史/撤销。

### 第一阶段：整理工作区

- 根因：规则输入控件此前没有发送按钮或提交信号，AI 请求只挂在扫描动作上。现在按钮和 Enter 都接入原有后台整理服务；Shift+Enter 换行，输入法候选编辑不触发提交。
- 导入与建议生成分离，选目录不再立即提交 AI；真实页面生成建议后仍需主动打开预览。保留旧私有方法默认参数，避免现有测试和调用点回归，但正式按钮走新流程。
- 预设为文件类型、修改年月（真实本地分类），课程/项目/自定义（需要 AI）；不能从视频可靠识别预设文案，因此没有声称逐项复制。
- 原视频约 35 秒画面已提取查看，采用其蓝色文件夹和层级目录方向；主工作区复用已校验 OperationPlan 的树与表，不浏览任意磁盘目录。
- 大统计卡片改为行内真实计数；目录树、导入清单占主要区域。文件类型图标区分图片、表格、代码和普通文件。
- 删除第一条冗长 AI 提示的可见展示，保留紧凑模型状态和第二条元数据隐私说明；授权和无密钥引导保留。
- 请求期间仍可编辑规则，但签名不一致的迟到结果不会成为可执行计划。取消、失败和部分失败保留真实状态。
- 规则变化使旧计划失效；执行/撤销完成后只重新读取清单，不自动再次向 AI 发送请求。
- 底部显示状态、进度、上次整理成功/失败数量和历史入口。完整详情、执行确认和历史撤销继续保留。

### 第二阶段：本机用户

- 复用已有首次设密、PBKDF2 验证、DPAPI 记住解锁、恢复码、修改密码和手动锁屏控制器，没有重写稳定认证逻辑。
- 用户菜单新增本机头像选择；后台解码、缩放、去元数据后写入独立配置目录。仅接受普通栅格图片，拒绝符号链接、无效格式、过大文件或像素量。
- “锁定 / 登出”回到锁屏并使记住解锁令牌失效。忙碌中的文件、聊天、头像和转换任务须先安全结束。
- 验证值与 API 凭据仍分离；本轮没有读取实际密码、API Key、.env 或 Windows 凭据。头像不会进入模型或聊天历史。

### 第三阶段：侧栏

- 主侧栏与内容区放入 QSplitter，宽度限制 230–380px；内容区负责吸收剩余宽度。
- 顶部常驻展开/收起按钮与 Ctrl+B 不随侧栏隐藏。宽度和展开状态通过独立 workspace.json 原子保存。
- 导航和最近对话仍各自滚动；统一 NAVIGATION_ITEMS 定义页面入口。格式转换增加一条定义和页面注册即可接入。

### 第四阶段：Orbit

- 浅紫渐变、自绘轨道光球、白色输入卡片、紫色发送按钮；用户消息仍保留蓝色背景。
- 两个状态复用 ChatInput，隐私文字另起一行，避免挤压模型选择器与发送按钮。
- 首页独立滚动，窄内容区快捷卡片由四列改两列；聊天态输入框固定在下方，消息独立滚动。
- 模型请求、附件确认、停止/重试和本地会话模块继续复用，没有伪造新连接、回复或模型列表。本轮只用 mock 验证服务路径，未测试用户真实 API。

### 第五阶段：格式转换

- 独立 conversion 服务与页面；后台识别、选择目标、明确输出位置、进度、取消、结果与错误反馈。
- 动态读取 Qt 编码器，仅显示当前输入能使用的已实现目标。支持单帧图片、单页图片 PDF、UTF-8/UTF-16、CSV/JSON 和单文件 ZIP。
- 输出先暂存、重新检查源文件、取消和目标冲突，再以不覆盖操作发布；失败清理仅限本任务临时文件。
- 初次测试发现 InterruptedError 是 OSError 子类，转换中途取消被通用错误包装；现单独传递取消信号，并补充编码后取消测试。
- 不上传、不删除源文件、不把改扩展名当成转换；动图、多页图片、Office/WPS、OCR、PDF 转文档、音视频转换未集成。外部程序检测结果不代表对应功能可用。

## 修改文件

| 文件 | 变化 |
| --- | --- |
| filemind/core/organization_presets.py | 分类预设及本地修改年月分类 |
| filemind/ui/pages/organize_page.py | 可发送规则、紧凑统计、工作区、状态、计划失效 |
| filemind/ui/widgets/imported_files.py | 原始清单模型和行内计数 |
| filemind/ui/widgets/organization_workspace.py | 导入清单与目标树/表页签 |
| filemind/ui/widgets/plan_filter.py | 抽出供主工作区与预览共享的层级筛选 |
| filemind/ui/dialogs/plan_preview.py | 复用筛选模型，保留确认流程 |
| filemind/ui/widgets/plan_tree.py | 按文件类型显示图标 |
| filemind/ui/main_window.py | 导入/分析分流、请求阶段、迟到结果保护、侧栏、账户、转换注册 |
| filemind/storage/workspace.py | 独立非秘密 UI 设置、头像安全缩略图 |
| filemind/ui/widgets/local_account.py | 本机头像与圆形裁剪展示 |
| filemind/ui/pages/assistant_page.py | Orbit 配色、滚动、卡片响应布局 |
| filemind/ui/widgets/chat_input.py | 输入底栏与隐私说明分离 |
| filemind/ui/pages/conversion_page.py | 真实本地转换流程和后台任务 |
| filemind/conversion/__init__.py、models.py、service.py | 输入/目标/结果模型、格式能力、转换与安全发布 |
| filemind/ui/styles/icons.py、theme.py | 新图标、页签、锁屏、侧栏与状态样式 |
| tests/test_organization_workspace.py | 导入不调用 AI、规则发送、真实预览链路、迟到结果 |
| tests/test_workspace_preferences.py | 本机偏好保存、头像去元数据、菜单、侧栏恢复 |
| tests/test_conversion.py、test_conversion_ui.py | 格式真实性、错误、取消、冲突、后台响应与关闭 |
| tools/review_ui.py | 增加隔离转换页面启动/截图 |
| README.md、本文件 | 使用方法、能力边界与验收 |

## 技能、来源和许可证

采用已安装的 filemind-desktop-ui 和 frontend-design 技能指导布局，computer-use 用于实际 Windows 验收；没有下载执行第三方安装脚本。新增图标、工作区和转换代码均为项目内实现，没有复制第三方控件代码。

再次查看 [PyQt-Fluent-Widgets 官方仓库](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)：提供 PySide6 分支，许可证为 GPL-3.0/商业许可；没有安装或复制该库，避免为了视觉额外引入组件框架。GitHub 页面未可靠显示本次最新提交日期，因此不声称核实其近期提交活跃度。

转换依据 [Qt QImageWriter 文档](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QImageWriter.html) 的动态编码能力，使用实际运行环境读取格式列表。没有新增转换库。现有安装版本许可证：PySide6 Essentials 6.12.0 元数据为 LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only；OpenAI SDK 2.54.0 为 Apache-2.0；pytest 9.0.2 为 MIT（仅开发）。发行时仍需履行实际使用组件的许可证要求。

## 验证记录

修改前实际基线：104 passed，24 subtests passed，23.82 秒。

分阶段测试：原预览/界面 30 项通过；加入侧栏与锁屏联动后 33 项通过；转换、偏好、工作区专项 28 项通过；最后补充关闭和迟到结果边界。现有测试没有删除、跳过或降低断言。

完整测试：`py -3.13 -m pytest -q`，最后一次为 **134 passed、24 subtests passed（43.70 秒）**，退出码 0；此前两次完整复跑也通过（47.52 秒 / 45.43 秒）。更早一次与多个 UI 进程并行启动的回归中，新工作区测试曾达到 5 秒等待上限；保留原断言后复跑通过，未据此宣称确定的系统性能原因。

`py -3.13 -m compileall -q main.py filemind tests tools` 通过；入口、主窗口、转换页/服务、偏好存储与共享筛选六个模块导入通过；`py -3.13 -m pip check` 显示 No broken requirements found。

正式启动逻辑另做隔离冒烟：创建真实 QApplication、显示首次设置页并定时取消，确认返回 0 且 MainWindow 从未构造，没有加载实际模型设置。此检查使用临时锁存储，不读取 Windows 凭据。

UI 已通过隔离工具实际启动并查看 1024×700、1280×850 的整理、Orbit、聊天，1024×700 设置/预览，1024×700 和 1280×850 转换，以及 920×660 首次设置页；另在 Windows 原生窗口检查侧栏收起/展开、Orbit 导航和模型菜单展开/收起。测试还覆盖 1024px 主窗口将侧栏拖至 380px 时快捷卡片两列布局。截图位于 .artifacts/ui-review，均为临时生成数据，不代表真实模型响应。

仍需用户使用自己的 API 验证联网和模型账户权限；本轮没有访问真实凭据或对用户文件自动执行整理。应用锁屏不替代 Windows 账户安全或磁盘加密。没有在多个显示器、所有缩放比例或数万文件上进行人工验收。
