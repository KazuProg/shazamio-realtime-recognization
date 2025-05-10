import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logger(
    logger_name: str = "shazam_realtime",
    log_level: int = logging.INFO,
    log_to_file: bool = True,
    log_file_path: Optional[str] = None,
    console_output: bool = True,
) -> logging.Logger:
    """
    アプリケーション用のロガーを設定します。

    Args:
        logger_name: ロガーの名前
        log_level: ログレベル（例：logging.DEBUG, logging.INFO）
        log_to_file: ファイルにログを出力するかどうか
        log_file_path: ログファイルのパス（Noneの場合はデフォルトパスを使用）
        console_output: コンソールにログを出力するかどうか

    Returns:
        設定されたロガーインスタンス
    """
    # すでに設定されているロガーがあれば、それを返す
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    # ロガーのレベルを設定
    logger.setLevel(log_level)

    # ログのフォーマットを設定
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ファイルへの出力を設定
    if log_to_file:
        if log_file_path is None:
            # デフォルトのログディレクトリとファイル名
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            os.makedirs(log_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d")
            log_file_path = os.path.join(log_dir, f"{logger_name}_{timestamp}.log")

        # ローテーティングファイルハンドラーを設定
        file_handler = RotatingFileHandler(
            log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5  # 10 MB
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # コンソール出力を設定
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


# デフォルトのロガー設定
# このデフォルトロガーは他のモジュールからインポートして使用できます
default_logger = setup_logger()


# 例外をログに記録する便利な関数
def log_exception(
    e: Exception, message: str, logger: logging.Logger = default_logger
) -> None:
    """
    例外情報をログに記録します。

    Args:
        e: 記録する例外
        message: 例外の説明メッセージ
        logger: 使用するロガーインスタンス
    """
    logger.error(f"{message}: {type(e).__name__} - {e}")
