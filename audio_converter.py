import wave
import io

from pydub import AudioSegment

"""
音声フォーマット変換ユーティリティモジュール。
様々な音声フォーマット間の変換機能を提供します。
"""


def convert_pcm_to_wav_bytes(
    pcm_data: bytes, channels: int, rate: int, sample_width: int
) -> bytes:
    """
    生のPCM音声データ（バイト列）をWAVフォーマットのバイト列（ヘッダ付き）に変換します。

    Args:
        pcm_data: 変換するPCM音声データ
        channels: チャンネル数（1:モノラル、2:ステレオ）
        rate: サンプリングレート（Hz）
        sample_width: サンプルあたりのバイト数

    Returns:
        bytes: WAVフォーマットに変換されたバイト列データ。変換失敗時は空のバイト列
    """
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
    """
    WAV形式のバイト列をogg形式のバイト列に変換します。

    Args:
        wav_data: 変換するWAV音声データ
        sample_rate: サンプリングレート（Hz）
        channels: チャンネル数

    Returns:
        bytes: OGG形式に変換されたバイト列データ。変換失敗時は空のバイト列
    """
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
