import wave
import io

from pydub import AudioSegment


def convert_pcm_to_wav_bytes(
    pcm_data: bytes, channels: int, rate: int, sample_width: int
) -> bytes:
    """生のPCM音声データ（バイト列）をWAVフォーマットのバイト列（ヘッダ付き）に変換します。"""
    if not pcm_data:
        return b""
    wav_buffer = io.BytesIO()
    try:
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm_data)
        return wav_buffer.getvalue()
    except Exception as e:
        print(f"PCMからWAVへの変換中にエラーが発生しました: {e}")
        return b""
    finally:
        wav_buffer.close()


def convert_wav_to_ogg_bytes(wav_data: bytes, sample_rate: int, channels: int) -> bytes:
    """WAV形式のバイト列をogg形式のバイト列に変換します。"""
    if not wav_data:
        return b""
    ogg_buffer = io.BytesIO()
    try:
        audio_segment = AudioSegment.from_wav(io.BytesIO(wav_data))
        audio_segment.export(ogg_buffer, format="ogg")
        return ogg_buffer.getvalue()
    except Exception as e:
        print(f"WAVからOGGへの変換中にエラーが発生しました: {e}")
        return b""
    finally:
        ogg_buffer.close()
