import asyncio
import os
from typing import Dict, Any, Optional

from shazam_realtime_recognizer import ShazamRealtimeRecognizer


def recognition_callback(result: Optional[Dict[str, Any]]) -> None:
    """認識結果を処理するコールバック関数です。"""
    if result is None:
        print("認識できませんでした。")
        return

    title: str = result.get("track", {}).get("title", "タイトル不明")
    artist: str = result.get("track", {}).get("subtitle", "アーティスト不明")
    clear_console()
    print(f"\n  {title} / {artist}\n")


async def main() -> None:
    """
    メイン実行関数です。ユーザー入力に基づいて楽曲認識を繰り返し実行します。
    """
    recognizer = ShazamRealtimeRecognizer(
        recognition_callback=recognition_callback,
        stop_on_found=True,
    )
    while True:
        print("\n楽曲認識を開始するにはEnterキーを押してください。")
        input()

        await recognizer.start_recognition()

        while recognizer._is_recognizing:
            await asyncio.sleep(0.1)


def clear_console() -> None:
    """
    コンソールをクリアします。OSに応じて適切なコマンドを実行します。

    Returns:
        None
    """
    os_name: str = os.name
    if os_name == "posix":  # macOS, Linux, Unix系
        os.system("clear")
    elif os_name == "nt":  # Windows
        os.system("cls")
    else:
        print(
            f"お使いのオペレーティングシステム ({os_name}) では、コンソールのクリアはサポートされていません。"
        )


if __name__ == "__main__":
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e) and isinstance(e, RuntimeError):
            print("イベントループが既に閉じられています。新しいループで再試行します。")
            new_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(main())
            except KeyboardInterrupt:
                print("\nプログラムが強制終了されました。")
            finally:
                if new_loop.is_running():
                    new_loop.stop()
                print("新しいイベントループでの処理を終了しました。")
        else:
            raise
    except KeyboardInterrupt:
        print("\nプログラムがメインループ開始前に中断されました。")
    finally:
        if loop.is_running():
            loop.stop()
