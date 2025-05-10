import asyncio
import os
import sys
import logging
import signal
from typing import (
    Dict,
    Any,
    Optional,
    Final,
    NoReturn,
)

from shazam_realtime_recognizer import ShazamRealtimeRecognizer
from logger_config import setup_logger, log_exception

# このモジュール用のロガーを設定
logger = setup_logger(logger_name="main", log_level=logging.INFO)

# 定数定義
MAX_RECOGNITION_ATTEMPTS: Final[int] = 3  # 認識試行の最大回数
EXIT_SUCCESS: Final[int] = 0  # 正常終了コード
EXIT_ERROR: Final[int] = 1  # エラー終了コード


def recognition_callback(result: Optional[Dict[str, Any]]) -> None:
    """認識結果を処理するコールバック関数です。"""
    try:
        if result is None:
            logger.info("認識できませんでした。")
            print("認識できませんでした。")  # ユーザーへの表示として残す
            return

        # 結果から情報を抽出
        track_info = result.get("track", {})
        title: str = track_info.get("title", "タイトル不明")
        artist: str = track_info.get("subtitle", "アーティスト不明")

        # 認識結果をログに記録
        logger.info(f"認識結果: {title} / {artist}")

        # ユーザーへの表示
        clear_console()
        print(f"\n  {title} / {artist}\n")

    except Exception as e:
        log_exception(e, "認識結果の処理中にエラーが発生しました")


async def main() -> int:
    """
    メイン実行関数です。ユーザー入力に基づいて楽曲認識を繰り返し実行します。

    Returns:
        int: 終了コード。正常終了は0、エラー終了は1
    """
    # シグナルハンドラの設定
    setup_signal_handlers()

    recognizer: Optional[ShazamRealtimeRecognizer] = None

    try:
        logger.info("ShazamRealtimeRecognizerを初期化しています...")
        recognizer = ShazamRealtimeRecognizer(
            recognition_callback=recognition_callback,
            stop_on_found=True,
        )
        logger.info("初期化完了。認識準備完了。")

        # メインループ
        while True:
            try:
                # このメッセージはユーザーのためのものなのでprint()を使用
                print(
                    "\n楽曲認識を開始するにはEnterキーを押してください。Ctrl+Cで終了します。"
                )
                input()

                # 開始前の確認
                logger.info("楽曲認識を開始します...")

                # 認識開始
                await recognizer.start_recognition()

                # 認識処理が完了するまで待機
                await wait_for_recognition_complete(recognizer)

                logger.info("楽曲認識が完了しました")

            except KeyboardInterrupt:
                # 録音中なら停止
                if recognizer and recognizer._is_recognizing:
                    recognizer.stop_recognition()
                    logger.info("キーボード割り込みにより認識処理をキャンセルしました")
                    print("\n認識処理をキャンセルしました。")
                    # 停止処理が完了するまで少し待つ
                    await asyncio.sleep(0.5)
                else:
                    logger.info("キーボード割り込みによりプログラムを終了します")
                    print("\nプログラムを終了します。")
                    break
            except asyncio.CancelledError:
                logger.info("非同期処理がキャンセルされました")
                print("\n非同期処理がキャンセルされました。")
                break
            except Exception as e:
                log_exception(e, "楽曲認識中に予期せぬエラーが発生しました")
                # ユーザーへのエラー表示
                print(f"\n楽曲認識中にエラーが発生しました: {type(e).__name__} - {e}")
                logger.info("プログラムを終了します")
                print("\nプログラムを終了します。")
                break

    except KeyboardInterrupt:
        logger.info("キーボード割り込みによりプログラムを終了します")
        print("\nプログラムを終了します。")
    except Exception as e:
        log_exception(e, "メイン処理中に重大なエラーが発生しました")
        print(f"\nエラーが発生しました: {type(e).__name__} - {e}")
        return EXIT_ERROR
    finally:
        # 確実にリソースを解放
        await cleanup_resources(recognizer)

    logger.info("プログラムが正常に終了しました")
    return EXIT_SUCCESS


async def wait_for_recognition_complete(recognizer: ShazamRealtimeRecognizer) -> None:
    """
    認識処理が完了するまで待機します。

    Args:
        recognizer: 楽曲認識インスタンス
    """
    retry_count = 0
    retry_limit = 3
    retry_interval = 0.1  # 秒

    while recognizer._is_recognizing:
        try:
            await asyncio.sleep(retry_interval)
        except asyncio.CancelledError:
            logger.warning("認識待機中に処理がキャンセルされました")
            break
        except Exception as e:
            log_exception(e, "認識待機中にエラーが発生しました")
            retry_count += 1
            if retry_count >= retry_limit:
                logger.error(f"{retry_limit}回のエラーが発生したため待機を中断します")
                break


async def cleanup_resources(recognizer: Optional[ShazamRealtimeRecognizer]) -> None:
    """
    プログラム終了時にリソースを解放します。

    Args:
        recognizer: 楽曲認識インスタンス
    """
    if recognizer and recognizer._is_recognizing:
        try:
            logger.info("録音認識を停止しています...")
            recognizer.stop_recognition()
            # 停止処理が完了するまで少し待つ
            await asyncio.sleep(0.5)
            logger.info("録音認識を停止しました")
        except Exception as e:
            log_exception(e, "リソース解放中にエラーが発生しました")


def setup_signal_handlers() -> None:
    """
    シグナルハンドラを設定します。Windows/Unix両対応。
    """
    # Windowsではシグナルの種類が限られるため、対応を分ける
    try:
        # SIGTERM: プロセス終了リクエスト (Unix/Linux)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, lambda sig, frame: handle_termination())

        # SIGINT: キーボード割り込み (Ctrl+C) - 全プラットフォーム
        signal.signal(signal.SIGINT, lambda sig, frame: handle_termination())

        logger.debug("シグナルハンドラを設定しました")
    except Exception as e:
        log_exception(e, "シグナルハンドラの設定に失敗しました")


def handle_termination() -> NoReturn:
    """
    終了シグナル受信時の処理。
    """
    logger.info("終了シグナルを受信しました")
    print("\n終了シグナルを受信しました。プログラムを終了します。")
    sys.exit(0)


def clear_console() -> None:
    """
    コンソールをクリアします。OSに応じて適切なコマンドを実行します。

    Returns:
        None
    """
    try:
        os_name: str = os.name
        if os_name == "posix":  # macOS, Linux, Unix系
            os.system("clear")
        elif os_name == "nt":  # Windows
            os.system("cls")
        else:
            logger.warning(
                f"OS '{os_name}' ではコンソールクリアがサポートされていません"
            )
            print(
                f"お使いのオペレーティングシステム ({os_name}) では、コンソールのクリアはサポートされていません。"
            )
    except Exception as e:
        log_exception(e, "コンソールのクリア中にエラーが発生しました")
        # コンソールクリアは重要な機能ではないので、失敗しても続行


async def run_app() -> int:
    """
    アプリケーションを実行し、適切なエラーハンドリングを行います。

    Returns:
        int: 終了コード。正常終了は0、エラー終了は1
    """
    try:
        return await main()
    except Exception as e:
        log_exception(e, "アプリケーション実行中に回復不能なエラーが発生しました")
        return EXIT_ERROR


def run_with_event_loop() -> int:
    """
    イベントループを作成し、アプリケーションを実行します。

    Returns:
        int: 終了コード
    """
    exit_code = EXIT_SUCCESS
    loop = None

    try:
        logger.info("プログラムを開始します")
        # 明示的にイベントループを作成
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # アプリケーションを実行
        exit_code = loop.run_until_complete(run_app())

    except KeyboardInterrupt:
        logger.info("プログラムが中断されました")
        print("\nプログラムが中断されました。")
        exit_code = EXIT_SUCCESS  # キーボード割り込みによる終了は正常終了として扱う
    except RuntimeError as e:
        # イベントループに関するエラー処理
        if "Event loop is closed" in str(e) and isinstance(e, RuntimeError):
            logger.warning(
                "イベントループが既に閉じられています。新しいループで再試行します"
            )
            print("イベントループが既に閉じられています。新しいループで再試行します。")

            # 新しいループで再試行
            exit_code = retry_with_new_loop()
        else:
            log_exception(e, "ランタイムエラーが発生しました")
            print(f"ランタイムエラーが発生しました: {e}")
            exit_code = EXIT_ERROR
    except Exception as e:
        log_exception(e, "予期せぬエラーが発生しました")
        print(f"予期せぬエラーが発生しました: {type(e).__name__} - {e}")
        exit_code = EXIT_ERROR
    finally:
        # メインループのクリーンアップ
        if loop:
            try:
                # ループのクリーンアップ
                cleanup_event_loop(loop)
                logger.debug("イベントループをクリーンアップしました")
            except Exception as e:
                log_exception(e, "ループのクリーンアップ中にエラーが発生しました")

        logger.info(f"プログラムを終了します（終了コード: {exit_code}）")

    return exit_code


def retry_with_new_loop() -> int:
    """
    新しいイベントループでアプリケーションを再試行します。

    Returns:
        int: 終了コード
    """
    new_loop = None
    try:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        return new_loop.run_until_complete(run_app())
    except KeyboardInterrupt:
        logger.info("新しいループ実行中にプログラムが中断されました")
        print("\nプログラムが中断されました。")
        return EXIT_SUCCESS
    except Exception as e2:
        log_exception(e2, "新しいイベントループでもエラーが発生しました")
        print(f"新しいイベントループでもエラーが発生しました: {e2}")
        return EXIT_ERROR
    finally:
        # 新しいループのクリーンアップ
        if new_loop:
            cleanup_event_loop(new_loop)


def cleanup_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """
    イベントループをクリーンアップします。

    Args:
        loop: クリーンアップするイベントループ
    """
    try:
        if loop.is_running():
            loop.stop()

        # 未完了のタスクをキャンセル
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()

        # すべてのタスクが完了するのを待つ
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        # ループを閉じる
        loop.close()
    except Exception:
        # クリーンアップ中のエラーは無視
        pass


if __name__ == "__main__":
    # アプリケーションを実行し、終了コードを設定
    sys.exit(run_with_event_loop())
