# 交接：Sakura issue #94 资源管理器重构（第 3 阶段起）

> 给下一个会话的上下文交接。配合 `docs/RUNTIME_RESOURCE_MANAGER_PLAN.md`（设计文档）一起读。

## 项目与分支
- 仓库根目录：`C:\Users\LBW\MyFile\sakura-project\Sakura`（PySide6/Qt 桌宠，Windows）
- 当前分支：`refactor/resource-manager`（从 `origin/dev` 切出），第 1+2 阶段已完成，ahead 4 个提交，**未推送**。
- issue #94：把散落在 `PetWindow`（6700+ 行）里的 Qt/Python/进程生命周期，分 5 阶段抽到统一的后端资源管理器。

## 已完成（第 1+2 阶段，4 个提交）
1. 设计文档 `docs/RUNTIME_RESOURCE_MANAGER_PLAN.md`
2. 新增 `app/core/resource_manager.py`：
   - `QtWorkerResource`：托管一对 `QThread+QObject worker`；`stop()` 复刻 `cancel→requestInterruption→quit→wait→linger`；`_finalize()` 负责 wrapper 保留 + deleteLater + 清空宿主属性 + 调 `on_finished` 业务回调。
   - `ResourceManager(QObject)`：`spawn_qt_worker(...)` 工厂、`stop_all()`、`stop_qt_thread()` 原语、`retain_wrappers()`/prune、lingering 线程管理。`spawn_qt_worker` 有 `register=False` 选项（不纳入 `stop_all` 清单）。
   - 单测 `tests/unit/test_resource_manager.py`（10 个，全绿）。
3. 第 1 阶段：`PetWindow.__init__` 建 `self.resource_manager = ResourceManager(self)`；`_shutdown_qthread`/lingering/wrapper 委托给管理器。
4. 第 2 阶段：**7 个** QThread worker 创建点全部迁到 `spawn_qt_worker`（ChatWorker 聊天+动作、EventWorker、MemoryCurationWorker、ScreenObservationEncodeWorker、TTSReadyWarmupWorker、DeferredStartupWorker、TTSBundleMigrationWorker[用 register=False]）；`close_external_tools` 改用 `stop_all`；删了 `_shutdown_qthread` 和两个空 cleanup 方法，cleanup 方法只剩业务逻辑。

## 必须保持的约束
- 关闭序列、Shiboken wrapper 保留窗口、QThread 仍 parent 到窗口（否则 `tests/conftest.py:_cleanup_qt_objects` 靠 `children()` 递归回收不到线程）。
- `PetWindow` 仍持有 `self.worker`/`self.worker_thread` 等属性（指向管理器创建的对象），不要打断现有处理器与测试断言。
- 插件只能经 service facade，不得接触 PetWindow/TTS 内部实例。

## 测试怎么跑（重要）
- **用 `./runtime/python.exe -m pytest ...`**，不要用系统 Python（Anaconda 的 PySide6 会崩 0xc0000139）。
- 已知 2 个**环境性**失败、与重构无关：`tests/ui/test_history_window.py` 需要 qtbot（runtime 没装 pytest-qt）；`test_public_api_cleanup.py::test_legacy_sdk_package_is_removed` 因工作树里有残留未跟踪的 `sdk/` 目录。CI 下不会出现。
- 回归验证命令：`./runtime/python.exe -m pytest tests/unit/test_resource_manager.py tests/ui/test_pet_window.py tests/ui/test_backchannel_controller.py -q -p no:warnings`

## 下一步：第 3 阶段——拆分 TTS Provider（风险最高，最需谨慎）
当前 `app/voice/tts.py` 的 `GPTSoVITSTTSProvider`（QObject）混了三类职责，按 issue 拆成：
- `TTSServiceSupervisor`：本地 GPT-SoVITS/Genie 子进程、健康检查、Broken pipe 重启
- `TTSSynthesisQueue`：合成请求队列、prepare、HTTP 超时、失败重试
- `TTSPlaybackEndpoint`：**留在 UI 主线程**，QMediaPlayer/AudioSinkPlayer 播放（绝不移出主线程）

必须保留的语义：prepare、播放完成回调、fallback timeout、Broken pipe 重启、临时 wav 清理。后台只生成 wav，播放仍回 UI 线程。

## 工作方式（请遵守）
- **分段提交 git**，每个提交保持测试绿（破坏某测试就在同一提交里改它）。
- 第 3 阶段体量大、风险高：先给计划，**确认后再动手**；做完先停下等确认，再继续第 4/5 阶段。
- 用中文交流。
- 工作树里两个未跟踪的 `docs/*CHANGELOG.md` 与本次无关，别动。
