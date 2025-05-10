import asyncio
import os
import sys
from typing import Dict, Any, Optional

from shazam_realtime_recognizer import ShazamRealtimeRecognizer


def recognition_callback(result: Optional[Dict[str, Any]]) -> None:
    """認識結果を処理するコールバック関数です。"""
    try:
        if result is None:
            print("認識できませんでした。")
            return

        title: str = result.get("track", {}).get("title", "タイトル不明")
        artist: str = result.get("track", {}).get("subtitle", "アーティスト不明")
        clear_console()
        print(f"\n  {title} / {artist}\n")
    except Exception as e:
        print(f"認識結果の処理中にエラーが発生しました: {type(e).__name__} - {e}")


async def main() -> None:
    """
    メイン実行関数です。ユーザー入力に基づいて楽曲認識を繰り返し実行します。
    """
    recognizer = None
    try:
        recognizer = ShazamRealtimeRecognizer(
            recognition_callback=recognition_callback,
            stop_on_found=True,
        )

        while True:
            try:
                print(
                    "\n楽曲認識を開始するにはEnterキーを押してください。Ctrl+Cで終了します。"
                )
                input()

                await recognizer.start_recognition()

                # 認識処理が完了するまで待機
                while recognizer._is_recognizing:
                    await asyncio.sleep(0.1)

            except KeyboardInterrupt:
                print("\n認識処理をキャンセルしました。")
                if recognizer and recognizer._is_recognizing:
                    recognizer.stop_recognition()
                # プログラム自体は継続させる（次の認識のため）
            except asyncio.CancelledError:
                print("\n非同期処理がキャンセルされました。")
                break
            except Exception as e:
                print(
                    f"楽曲認識中に予期せぬエラーが発生しました: {type(e).__name__} - {e}"
                )
                # 致命的でないエラーの場合は続行
                await asyncio.sleep(1)  # 少し待機して再試行

    except KeyboardInterrupt:
        print("\nプログラムを終了します。")
    except Exception as e:
        print(f"メイン処理中に重大なエラーが発生しました: {type(e).__name__} - {e}")
        return 1  # エラーコードを返す
    finally:
        # 確実にリソースを解放
        if recognizer and recognizer._is_recognizing:
            recognizer.stop_recognition()
            # 停止処理が完了するまで少し待つ
            await asyncio.sleep(0.5)

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
            print(
                f"お使いのオペレーティングシステム ({os_name}) では、コンソールのクリアはサポートされていません。"
            )
    except Exception as e:
        print(f"コンソールのクリア中にエラーが発生しました: {e}")
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
        print(
            f"アプリケーション実行中に回復不能なエラーが発生しました: {type(e).__name__} - {e}"
        )
        return 1


if __name__ == "__main__":
    exit_code = 0
    loop = None

    try:
        # 明示的にイベントループを作成
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # アプリケーションを実行
        exit_code = loop.run_until_complete(run_app())

    except KeyboardInterrupt:
        print("\nプログラムが中断されました。")
    except RuntimeError as e:
        # イベントループに関するエラー処理
        if "Event loop is closed" in str(e) and isinstance(e, RuntimeError):
            print("イベントループが既に閉じられています。新しいループで再試行します。")
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                exit_code = new_loop.run_until_complete(run_app())
            except Exception as e2:
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
            print(f"ランタイムエラーが発生しました: {e}")
            exit_code = 1
    except Exception as e:
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
            except Exception as e:
                print(f"ループのクリーンアップ中にエラーが発生しました: {e}")

        # 終了コードを設定
        sys.exit(exit_code)
