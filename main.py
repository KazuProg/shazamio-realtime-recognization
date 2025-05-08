import asyncio
import json
import os
from pprint import pprint

import pyaudio
from shazamio import Shazam

from audio_recorder import AudioRecorder
from audio_converter import convert_pcm_to_wav_bytes, convert_wav_to_ogg_bytes

# --- 設定項目 ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
RECORD_SECONDS = 5
RECORDER_BUFFER_SECONDS = 10
# ----------------


async def main():
    recorder = AudioRecorder(
        audio_format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        chunk_size=CHUNK,
        buffer_seconds=RECORDER_BUFFER_SECONDS,
    )
    recorder.start()

    shazam = Shazam()
    debug_output_dir = "debug_audio"
    os.makedirs(debug_output_dir, exist_ok=True)

    try:
        while True:
            print(f"\n次の{RECORD_SECONDS}秒間の音声を準備します...")
            pcm_audio_data_bytes = await asyncio.to_thread(
                recorder.get_recent_audio_bytes, RECORD_SECONDS
            )

            if pcm_audio_data_bytes:
                print(
                    f"取得したPCM音声データ（{len(pcm_audio_data_bytes)} bytes）をWAV形式に変換します..."
                )
                wav_audio_data_bytes = await asyncio.to_thread(
                    convert_pcm_to_wav_bytes,
                    pcm_audio_data_bytes,
                    recorder.channels,
                    recorder.rate,
                    recorder.sample_width,
                )

                if wav_audio_data_bytes:
                    print("WAV形式データをogg形式に変換します...")
                    ogg_audio_data_bytes = await asyncio.to_thread(
                        convert_wav_to_ogg_bytes,
                        wav_audio_data_bytes,
                        recorder.rate,
                        recorder.channels,
                    )

                    if ogg_audio_data_bytes:
                        try:
                            print(
                                f"ogg形式データ（{len(ogg_audio_data_bytes)} bytes）を使ってShazamで楽曲を認識します..."
                            )
                            out = await shazam.recognize(ogg_audio_data_bytes)
                            print("Shazam 認識結果:")

                            with open("shazam_result.json", "w", encoding="utf-8") as f:
                                json.dump(out, f, ensure_ascii=False, indent=4)
                            print("認識結果を shazam_result.json に保存しました。")

                            if out.get("track"):
                                title = out["track"].get("title", "タイトル不明")
                                subtitle = out["track"].get(
                                    "subtitle", "サブタイトル不明"
                                )
                                pprint(f"楽曲: {title} / アーティスト: {subtitle}")
                            else:
                                print("楽曲情報が見つかりませんでした。")
                                if out.get("matches"):
                                    print(
                                        "類似候補が見つかりましたが、確定的な楽曲情報はありません。"
                                    )
                                pprint(out)

                        except Exception as e:
                            print(f"Shazam でのエラー: {e}")
                    else:
                        print(
                            "WAVからogg形式への変換に失敗しました。Shazam認識をスキップします。"
                        )
                else:
                    print("WAV形式への変換に失敗しました。Shazam認識をスキップします。")
            else:
                print("録音データが不足しています。Shazam認識をスキップします。")

            await asyncio.sleep(RECORD_SECONDS)

    except KeyboardInterrupt:
        print("\nプログラムを終了します...")
    finally:
        print("クリーンアップ処理を開始します。")
        recorder.stop()


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
