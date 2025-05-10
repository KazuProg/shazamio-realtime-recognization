import wave
import io
from typing import Optional

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

"""
音声フォーマット変換ユーティリティモジュール。
様々な音声フォーマット間の変換機能を提供します。
"""


def convert_pcm_to_wav_bytes(
    pcm_data: bytes, channels: int, rate: int, sample_width: int
) -> Optional[bytes]:
    """
    生のPCM音声データ（バイト列）をWAVフォーマットのバイト列（ヘッダ付き）に変換します。

    Args:
        pcm_data: 変換するPCM音声データ
        channels: チャンネル数（1:モノラル、2:ステレオ）
        rate: サンプリングレート（Hz）
        sample_width: サンプルあたりのバイト数

    Returns:
        Optional[bytes]: WAVフォーマットに変換されたバイト列データ。変換失敗時はNone
    """
    if not pcm_data:
        return None

    wav_buffer: io.BytesIO = io.BytesIO()
    try:
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm_data)
        return wav_buffer.getvalue()
    except wave.Error as e:
        print(f"WAVフォーマットへの変換中にエラー発生: {e}")
        return None
    except OSError as e:
        print(f"WAVファイル書き込み中にI/Oエラー発生: {e}")
        return None
    except ValueError as e:
        print(f"不正なパラメータ - PCMからWAVへの変換中にエラー: {e}")
        return None
    except Exception as e:
        print(
            f"PCMからWAVへの変換中に予期せぬエラーが発生しました: {type(e).__name__} - {e}"
        )
        return None
    finally:
        wav_buffer.close()


def convert_wav_to_ogg_bytes(
    wav_data: bytes, sample_rate: int, channels: int
) -> Optional[bytes]:
    """
    WAV形式のバイト列をogg形式のバイト列に変換します。

    Args:
        wav_data: 変換するWAV音声データ
        sample_rate: サンプリングレート（Hz）
        channels: チャンネル数

    Returns:
        Optional[bytes]: OGG形式に変換されたバイト列データ。変換失敗時はNone
    """
    if not wav_data:
        return None

    ogg_buffer: io.BytesIO = io.BytesIO()
    wav_io: Optional[io.BytesIO] = None

    try:
        wav_io = io.BytesIO(wav_data)
        try:
            audio_segment: AudioSegment = AudioSegment.from_wav(wav_io)
            audio_segment.export(ogg_buffer, format="ogg")
            return ogg_buffer.getvalue()
        except CouldntDecodeError as e:
            print(f"WAVデータのデコードエラー: {e}")
            return None
        except OSError as e:
            print(f"OGGエクスポート中にI/Oエラー発生: {e}")
            return None
        except Exception as e:
            print(f"WAVからOGGへの変換中に予期せぬエラー: {type(e).__name__} - {e}")
            return None
    finally:
        if wav_io:
            wav_io.close()
        ogg_buffer.close()
