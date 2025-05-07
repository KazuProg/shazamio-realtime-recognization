import asyncio
import pyaudio
import soundfile as sf
from shazamio import Serialize

# --- 設定項目 ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
RECORD_SECONDS = 5
OUTPUT_OGG_FILE = "recorded_audio.ogg"  # 保存するoggファイル名
# ----------------


async def record_audio_bytes(
    seconds: int, rate: int, chunk_size: int, channels: int, audio_format: int
) -> bytes:
    """
    マイクから指定された秒数だけ音声を録音し、バイト列として返します。
    """
    audio = pyaudio.PyAudio()
    stream = None
    try:
        stream = audio.open(
            format=audio_format,
            channels=channels,
            rate=rate,
            input=True,
            frames_per_buffer=chunk_size,
        )

        print(f"{seconds}秒間の録音を開始します...")
        frames = []
        num_chunks = int(rate / chunk_size * seconds)

        for i in range(0, num_chunks):
            try:
                data = stream.read(chunk_size, exception_on_overflow=False)
                frames.append(data)
            except IOError as e:
                if e.errno == pyaudio.paInputOverflowed:
                    print(
                        f"警告: マイク入力バッファがオーバーフローしました (chunk {i+1}/{num_chunks})。一部の音声データが失われた可能性があります。"
                    )
                else:
                    raise

        print("録音終了。")
        return b"".join(frames)

    except Exception as e:
        print(f"録音中にエラーが発生しました: {e}")
        return b""
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        audio.terminate()


def save_to_ogg(
    audio_data: bytes, filename: str, rate: int, channels: int, sample_width: int
):
    """
    バイト列の音声データを ogg ファイルとして保存します。
    """
    try:
        import os

        os.remove(filename)
    except FileNotFoundError:
        pass
    try:
        # NumPy配列に変換 (soundfileはNumPy配列を扱う)
        import numpy as np

        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # libsndfileはfloat型のデータを扱うため、正規化
        audio_float = audio_array.astype(np.float32) / 32767.0

        sf.write(filename, audio_float, rate, format="OGG", subtype="VORBIS")
        print(f"音声を {filename} に保存しました。")
        return True
    except Exception as e:
        print(f"oggファイルへの保存中にエラーが発生しました: {e}")
        return False


async def main():
    while True:
        audio_data_bytes = await record_audio_bytes(
            seconds=RECORD_SECONDS,
            rate=RATE,
            chunk_size=CHUNK,
            channels=CHANNELS,
            audio_format=FORMAT,
        )

        if audio_data_bytes:
            # PyAudioの paInt16 は 2バイトなので、sample_width は 2
            sample_width = pyaudio.get_sample_size(FORMAT)
            if save_to_ogg(
                audio_data_bytes, OUTPUT_OGG_FILE, RATE, CHANNELS, sample_width
            ):
                from shazamio import Shazam

                shazam = Shazam()
                try:
                    out = await shazam.recognize(OUTPUT_OGG_FILE)
                    print("Shazam 認識結果:")
                    from pprint import pprint
                    import json

                    json.dump(
                        out,
                        open("shazam_result.json", "w"),
                        ensure_ascii=False,
                        indent=4,
                    )
                    pprint(f"{out["track"]["title"]} / {out["track"]["subtitle"]}")
                except Exception as e:
                    print(f"Shazam でのエラー: {e}")
        else:
            print("録音データがありませんでした。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
        else:
            raise
