import asyncio
import pyaudio
import soundfile as sf
from shazamio import Shazam
import numpy as np

import os
from pprint import pprint
import json

from audio_recorder import AudioRecorder

# --- 設定項目 ---
FORMAT = pyaudio.paInt16  # 音声フォーマット (paInt16 は 16ビット整数)
CHANNELS = 1  # モノラル
RATE = 16000  # サンプリングレート (Hz)
CHUNK = 1024  # 1回の読み込みでのフレーム数
RECORD_SECONDS = 5  # Shazamに渡す音声の長さ（秒）
OUTPUT_OGG_FILE = "recorded_audio.ogg"  # 保存するoggファイル名
RECORDER_BUFFER_SECONDS = 10  # AudioRecorderが内部で保持する音声データの最大長（秒）
# ----------------


def save_to_ogg(
    audio_data: bytes, filename: str, rate: int, channels: int, sample_width: int
):
    """
    バイト列の音声データを ogg ファイルとして保存します。
    sample_width はこの関数内では直接使用されませんが、データ型を特定するのに役立ちます。
    soundfile は NumPy 配列の dtype から自動的に判断します。
    """
    if not audio_data:
        print("保存する音声データがありません。")
        return False
    try:
        # 既存のファイルを削除 (上書きのため)
        if os.path.exists(filename):
            os.remove(filename)

        # バイトデータをNumPy配列に変換
        # FORMATがpaInt16なので、dtypeはnp.int16
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # soundfileがfloat型のデータを期待する場合があるため、正規化
        # sf.write は int16 も扱えるが、念のため float に変換
        # 最大値 32767.0 で割ることで -1.0 から 1.0 の範囲に正規化
        audio_float = audio_array.astype(np.float32) / 32767.0

        sf.write(filename, audio_float, rate, format="OGG", subtype="VORBIS")
        print(f"音声を {filename} に保存しました。")
        return True
    except Exception as e:
        print(f"oggファイルへの保存中にエラーが発生しました: {e}")
        return False


async def main():
    recorder = AudioRecorder(
        audio_format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        chunk_size=CHUNK,
        buffer_seconds=RECORDER_BUFFER_SECONDS,
    )
    recorder.start()

    # Shazamクライアントの初期化
    shazam = Shazam()

    try:
        while True:
            print(f"\n次の{RECORD_SECONDS}秒間の音声を準備します...")
            # get_recent_audio_bytes は同期的なので、asyncio.to_thread で実行
            audio_data_bytes = await asyncio.to_thread(
                recorder.get_recent_audio_bytes, RECORD_SECONDS
            )

            if audio_data_bytes:
                # PyAudioの paInt16 は 2バイトなので、sample_width は 2
                sample_width = pyaudio.get_sample_size(
                    FORMAT
                )  # AudioRecorderからも取得可能

                # save_to_ogg も同期的である可能性があるため、to_thread でラップ
                saved_successfully = await asyncio.to_thread(
                    save_to_ogg,
                    audio_data_bytes,
                    OUTPUT_OGG_FILE,
                    RATE,
                    CHANNELS,
                    sample_width,
                )

                if saved_successfully:
                    try:
                        print(f"{OUTPUT_OGG_FILE} を使ってShazamで楽曲を認識します...")
                        out = await shazam.recognize(
                            OUTPUT_OGG_FILE
                        )  # shazamio は非同期
                        print("Shazam 認識結果:")

                        # 結果をJSONファイルに保存
                        with open("shazam_result.json", "w", encoding="utf-8") as f:
                            json.dump(out, f, ensure_ascii=False, indent=4)
                        print("認識結果を shazam_result.json に保存しました。")

                        if out.get("track"):
                            title = out["track"].get("title", "タイトル不明")
                            subtitle = out["track"].get("subtitle", "サブタイトル不明")
                            pprint(f"楽曲: {title} / アーティスト: {subtitle}")
                        else:
                            print("楽曲情報が見つかりませんでした。")
                            pprint(out)  # 認識できなかった場合の結果全体を出力

                    except Exception as e:
                        print(f"Shazam でのエラー: {e}")
                else:
                    print(
                        "音声ファイルの保存に失敗しました。Shazam認識をスキップします。"
                    )
            else:
                print("録音データが不足しています。Shazam認識をスキップします。")

            # 次の認識までの待機時間（任意）
            # RECORD_SECONDS 秒ごとに新しい音声を取得するため、それに近い値を設定
            # ただし、処理時間も考慮に入れる
            await asyncio.sleep(RECORD_SECONDS)

    except KeyboardInterrupt:
        print("\nプログラムを終了します...")
    finally:
        print("クリーンアップ処理を開始します。")
        recorder.stop()
        # asyncioのイベントループが閉じている場合のエラーを回避するため、
        # mainの呼び出し側で対応しているが、ここでも確認
        if os.path.exists(OUTPUT_OGG_FILE):
            try:
                os.remove(OUTPUT_OGG_FILE)
                print(f"{OUTPUT_OGG_FILE} を削除しました。")
            except Exception as e:
                print(f"{OUTPUT_OGG_FILE} の削除中にエラー: {e}")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except RuntimeError as e:
        # Windowsで `KeyboardInterrupt` 時に `Event loop is closed` エラーが
        # 出ることがあるため、その場合のフォールバック
        if "Event loop is closed" in str(e) and isinstance(e, RuntimeError):
            print("イベントループが既に閉じられています。新しいループで再試行します。")
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(main())
            except KeyboardInterrupt:  # 再度 Ctrl+C された場合
                print("\nプログラムが強制終了されました。")
            finally:
                # new_loopのクリーンアップ (main関数内でrecorder.stop()が呼ばれているはず)
                if new_loop.is_running():
                    new_loop.stop()  # 安全のため
                # new_loop.close() # 既に閉じられている可能性
                print("新しいイベントループでの処理を終了しました。")
        else:
            raise  # その他のRuntimeErrorは再送出
    except KeyboardInterrupt:
        print("\nプログラムがメインループ開始前に中断されました。")
    finally:
        # メインのイベントループのクリーンアップ
        if loop.is_running():
            loop.stop()
        if not loop.is_closed():
            # すべての非同期タスクが完了するのを待つ (推奨されるクリーンアップ方法)
            # ただし、Ctrl+C の場合はタスクがキャンセルされるので、即座に閉じる方が良い場合もある
            # ここでは、すでにmain関数内で適切に停止処理が行われていると仮定
            pass
        print("メインのイベントループ処理を終了しました。")
