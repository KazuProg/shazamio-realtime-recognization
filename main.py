import asyncio
import os
from pprint import pprint

import pyaudio
from shazamio import Shazam

from audio_converter import convert_pcm_to_wav_bytes, convert_wav_to_ogg_bytes
from audio_recorder import AudioRecorder

# --- 設定項目 ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
RECOGNIZE_SECONDS = 5
RECOGNIZE_INTERVAL = 1
# ----------------


async def main():
    recorder = AudioRecorder(
        audio_format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        chunk_size=CHUNK,
        buffer_seconds=RECOGNIZE_SECONDS + 1,  # 無限ループ対策
    )

    shazam = Shazam()

    try:
        while True:
            print("音声認識を開始します。録音を開始するにはEnterキーを押してください。")
            input()

            print(f"\n次の{RECOGNIZE_SECONDS}秒間の音声を準備します...")
            recorder.start()

            next_recognize_time = 2

            while True:
                recorded_time = recorder.get_recorded_duration()
                if recorded_time < next_recognize_time:
                    await asyncio.sleep(RECOGNIZE_INTERVAL * 0.1)
                    continue

                next_recognize_time += RECOGNIZE_INTERVAL

                ogg_audio_data_bytes = await asyncio.to_thread(
                    get_recent_ogg_bytes, recorder, RECOGNIZE_SECONDS
                )

                if not ogg_audio_data_bytes:
                    continue

                try:
                    out = await shazam.recognize(ogg_audio_data_bytes)

                    if out.get("track"):
                        title = out["track"].get("title", "タイトル不明")
                        subtitle = out["track"].get("subtitle", "サブタイトル不明")
                        clear_console()
                        print()
                        print(f"{title} / {subtitle}")
                        print()
                        break  # 認識成功したらループを抜ける
                    else:
                        print("楽曲情報が見つかりませんでした。")

                except Exception as e:
                    print(f"Shazam でのエラー: {e}")

                if RECOGNIZE_SECONDS < recorded_time:
                    print("指定した時間内に楽曲が認識できませんでした。")
                    break

            recorder.stop()

    except KeyboardInterrupt:
        print("\nプログラムを終了します...")
    finally:
        print("クリーンアップ処理を開始します。")
        recorder.stop()


def get_recent_ogg_bytes(recorder, duration_seconds):
    pcm_audio_data_bytes = recorder.get_recent_audio_bytes(duration_seconds)
    if not pcm_audio_data_bytes:
        return None

    wav_audio_data_bytes = convert_pcm_to_wav_bytes(
        pcm_audio_data_bytes,
        recorder.channels,
        recorder.rate,
        recorder.sample_width,
    )
    if not wav_audio_data_bytes:
        return None

    ogg_audio_data_bytes = convert_wav_to_ogg_bytes(
        wav_audio_data_bytes,
        recorder.rate,
        recorder.channels,
    )
    if not ogg_audio_data_bytes:
        return None

    return ogg_audio_data_bytes


def clear_console():
    """コンソールをクリアします。"""
    os_name = os.name
    if os_name == "posix":  # macOS, Linux, Unix系
        os.system("clear")
    elif os_name == "nt":  # Windows
        os.system("cls")
    else:
        print(
            f"お使いのオペレーティングシステム ({os_name}) では、コンソールのクリアはサポートされていません。"
        )


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e) and isinstance(e, RuntimeError):
            print("イベントループが既に閉じられています。新しいループで再試行します。")
            new_loop = asyncio.new_event_loop()
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
