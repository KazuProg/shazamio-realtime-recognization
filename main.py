import asyncio
import os
import sys
import logging
from typing import Dict, Any, Optional

from shazam_realtime_recognizer import ShazamRealtimeRecognizer
from logger_config import setup_logger, log_exception

# このモジュール用のロガーを設定
logger = setup_logger(logger_name="main", log_level=logging.INFO)


def recognition_callback(result: Optional[Dict[str, Any]]) -> None:
    """認識結果を処理するコールバック関数です。"""
    try:
        if result is None:
            logger.info("認識できませんでした。")
            print("認識できませんでした。")  # ユーザーへの表示として残す
            return

        title: str = result.get("track", {}).get("title", "タイトル不明")
        artist: str = result.get("track", {}).get("subtitle", "アーティスト不明")

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
    recognizer = None
    try:
        logger.info("ShazamRealtimeRecognizerを初期化しています...")
        recognizer = ShazamRealtimeRecognizer(
            recognition_callback=recognition_callback,
            stop_on_found=True,
        )
        logger.info("初期化完了。認識準備完了。")

        while True:
            try:
                # このメッセージはユーザーのためのものなのでprint()を使用
                print(
                    "\n楽曲認識を開始するにはEnterキーを押してください。Ctrl+Cで終了します。"
                )
                input()

                logger.info("楽曲認識を開始します...")
                await recognizer.start_recognition()

                # 認識処理が完了するまで待機
                while recognizer._is_recognizing:
                    await asyncio.sleep(0.1)

                logger.info("楽曲認識が完了しました")

            except KeyboardInterrupt:
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
        return 1  # エラーコードを返す
    finally:
        # 確実にリソースを解放
        if recognizer and recognizer._is_recognizing:
            logger.info("録音認識を停止しています...")
            recognizer.stop_recognition()
            # 停止処理が完了するまで少し待つ
            await asyncio.sleep(0.5)
            logger.info("録音認識を停止しました")

    logger.info("プログラムが正常に終了しました")
    return 0  # 正常終了


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
        return 1


if __name__ == "__main__":
    exit_code = 0
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
    except RuntimeError as e:
        # イベントループに関するエラー処理
        if "Event loop is closed" in str(e) and isinstance(e, RuntimeError):
            logger.warning(
                "イベントループが既に閉じられています。新しいループで再試行します"
            )
            print("イベントループが既に閉じられています。新しいループで再試行します。")
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                exit_code = new_loop.run_until_complete(run_app())
            except KeyboardInterrupt:
                logger.info("新しいループ実行中にプログラムが中断されました")
                print("\nプログラムが中断されました。")
                exit_code = 0
            except Exception as e2:
                log_exception(e2, "新しいイベントループでもエラーが発生しました")
                print(f"新しいイベントループでもエラーが発生しました: {e2}")
                exit_code = 1
            finally:
                # 新しいループのクリーンアップ
                try:
                    if new_loop.is_running():
                        new_loop.stop()
                    new_loop.close()
                except Exception:
                    pass
        else:
            log_exception(e, "ランタイムエラーが発生しました")
            print(f"ランタイムエラーが発生しました: {e}")
            exit_code = 1
    except Exception as e:
        log_exception(e, "予期せぬエラーが発生しました")
        print(f"予期せぬエラーが発生しました: {type(e).__name__} - {e}")
        exit_code = 1
    finally:
        # メインループのクリーンアップ
        if loop:
            try:
                if loop.is_running():
                    loop.stop()
                # 未完了のタスクをキャンセル
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                # すべてのタスクが完了するのを待つ
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                loop.close()
                logger.debug("イベントループをクリーンアップしました")
            except Exception as e:
                log_exception(e, "ループのクリーンアップ中にエラーが発生しました")

        logger.info(f"プログラムを終了します（終了コード: {exit_code}）")
        # 終了コードを設定
        sys.exit(exit_code)
