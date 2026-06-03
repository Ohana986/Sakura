from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.core.app_context import AppContext
from app.core.bootstrap import build_deferred_services, build_initial_app_context
from app.config.character_loader import CharacterConfigError
from app.config.settings_service import AppSettingsService
from app.agent.mcp import MCPRuntimeSettings
from app.agent.proactive_care import ProactiveCareSettings
from app.ui.pet_window import PetWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.portrait_controller import PORTRAIT_SCALE_DEFAULT_PERCENT
from app.ui.subtitle_controller import (
    REPLY_SEGMENT_PAUSE_MS,
    SPEECH_TYPING_INTERVAL_MS,
    normalize_subtitle_display_speed,
)
from app.voice.tts import TTSConfigError


BASE_DIR = Path(__file__).resolve().parent


class DeferredStartupWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, base_dir: Path, context: AppContext) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.context = context

    @Slot()
    def run(self) -> None:
        try:
            services = build_deferred_services(self.base_dir, self.context)
            self._move_service_objects_to_ui_thread(services)
            self.finished.emit(services)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _move_service_objects_to_ui_thread(self, services: object) -> None:
        application = QApplication.instance()
        if application is None:
            return
        tts_provider = getattr(services, "tts_provider", None)
        if isinstance(tts_provider, QObject):
            tts_provider.moveToThread(application.thread())


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Sakura Desktop Pet")
    app.setQuitOnLastWindowClosed(False)

    try:
        context = build_initial_app_context(BASE_DIR)
    except CharacterConfigError as exc:
        if not _character_packages_missing(BASE_DIR):
            print(f"[Character] 配置无效：{exc}")
            return 1
        try:
            context = _open_first_run_settings(BASE_DIR)
        except (CharacterConfigError, OSError, TTSConfigError, ValueError) as first_run_exc:
            QMessageBox.critical(None, "启动失败", str(first_run_exc))
            print(f"[Character] 配置无效：{first_run_exc}")
            return 1
        if context is None:
            return 0
    except (OSError, ValueError) as exc:
        print(f"[Character] 配置无效：{exc}")
        return 1

    pet_window = PetWindow(context)
    app.aboutToQuit.connect(pet_window.close_external_tools)
    pet_window.show()
    QTimer.singleShot(0, lambda: _start_deferred_startup(BASE_DIR, pet_window))

    return app.exec()


def _character_packages_missing(base_dir: Path) -> bool:
    characters_dir = base_dir / "characters"
    if not characters_dir.is_dir():
        return True
    try:
        return not any(characters_dir.glob("*/character.json"))
    except OSError:
        return False


def _open_first_run_settings(base_dir: Path) -> AppContext | None:
    settings_service = AppSettingsService(base_dir=base_dir)
    api_settings = settings_service.load_api_settings()
    tts_settings = settings_service.load_tts_settings(
        validate_enabled=False,
        character_profile=None,
    )
    dialog = SettingsDialog(
        api_settings=api_settings,
        tts_settings=tts_settings,
        base_dir=base_dir,
        character_registry=None,
        current_character=None,
        proactive_care_settings=settings_service.load_proactive_care_settings(),
        mcp_settings=settings_service.load_mcp_runtime_settings(),
        debug_log_settings=settings_service.load_debug_log_settings(),
        portrait_scale_percent=PORTRAIT_SCALE_DEFAULT_PERCENT,
        subtitle_typing_interval_ms=SPEECH_TYPING_INTERVAL_MS,
        reply_segment_pause_ms=REPLY_SEGMENT_PAUSE_MS,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    (
        subtitle_typing_interval_ms,
        reply_segment_pause_ms,
    ) = normalize_subtitle_display_speed(
        getattr(dialog, "result_subtitle_typing_interval_ms", SPEECH_TYPING_INTERVAL_MS),
        getattr(dialog, "result_reply_segment_pause_ms", REPLY_SEGMENT_PAUSE_MS),
    )
    if (
        dialog.result_api_settings is None
        or dialog.result_tts_settings is None
        or dialog.result_character_id is None
        or dialog.result_proactive_care_settings is None
        or dialog.result_mcp_settings is None
        or dialog.result_debug_log_settings is None
        or dialog.result_portrait_scale_percent is None
        or dialog.character_registry is None
    ):
        QMessageBox.warning(None, "配置无效", "请先导入并选择一个角色包。")
        return None

    settings_service.save_api_settings(dialog.result_api_settings)
    settings_service.save_tts_settings(dialog.result_tts_settings)
    settings_service.save_current_character_id(
        dialog.character_registry,
        dialog.result_character_id,
    )
    settings_service.save_proactive_care_settings(
        dialog.result_proactive_care_settings or ProactiveCareSettings()
    )
    settings_service.save_mcp_runtime_settings(dialog.result_mcp_settings or MCPRuntimeSettings())
    settings_service.save_debug_log_settings(dialog.result_debug_log_settings)
    settings_service.save_system_values(
        "ui",
        {
            "portrait_scale_percent": int(dialog.result_portrait_scale_percent),
            "subtitle_typing_interval_ms": subtitle_typing_interval_ms,
            "reply_segment_pause_ms": reply_segment_pause_ms,
        },
    )
    return build_initial_app_context(base_dir)


def _start_deferred_startup(base_dir: Path, pet_window: PetWindow) -> None:
    thread = QThread(pet_window)
    worker = DeferredStartupWorker(base_dir, pet_window.context)
    worker.moveToThread(thread)
    pet_window.deferred_startup_thread = thread
    pet_window.deferred_startup_worker = worker
    thread.started.connect(worker.run)
    worker.finished.connect(pet_window.apply_deferred_services)
    worker.failed.connect(pet_window.handle_deferred_startup_failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda: setattr(pet_window, "deferred_startup_thread", None))
    thread.finished.connect(lambda: setattr(pet_window, "deferred_startup_worker", None))
    thread.start()

if __name__ == "__main__":
    raise SystemExit(main())
