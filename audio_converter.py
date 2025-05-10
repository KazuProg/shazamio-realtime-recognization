import wave
import io
import logging
from typing import Optional

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from logger_config import setup_logger, log_exception

# このモジュール用のロガーを設定
logger = setup_logger(logger_name="audio_converter", log_level=logging.INFO)

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
        logger.warning("変換対象のPCMデータが空です")
        return None

    wav_buffer: io.BytesIO = io.BytesIO()
    try:
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm_data)
        logger.debug(
            f"PCMからWAVへの変換成功: サイズ={len(wav_buffer.getvalue())}バイト"
        )
        return wav_buffer.getvalue()
    except wave.Error as e:
        log_exception(e, "WAVフォーマットへの変換中にエラー発生")
        return None
    except OSError as e:
        log_exception(e, "WAVファイル書き込み中にI/Oエラー発生")
        return None
    except ValueError as e:
        log_exception(e, "不正なパラメータ - PCMからWAVへの変換中にエラー")
        return None
    except Exception as e:
        log_exception(e, "PCMからWAVへの変換中に予期せぬエラーが発生しました")
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
        logger.warning("変換対象のWAVデータが空です")
        return None

    ogg_buffer: io.BytesIO = io.BytesIO()
    wav_io: Optional[io.BytesIO] = None

    try:
        wav_io = io.BytesIO(wav_data)
        try:
            audio_segment: AudioSegment = AudioSegment.from_wav(wav_io)
            audio_segment.export(ogg_buffer, format="ogg")
            logger.debug(
                f"WAVからOGGへの変換成功: サイズ={len(ogg_buffer.getvalue())}バイト"
            )
            return ogg_buffer.getvalue()
        except CouldntDecodeError as e:
            log_exception(e, "WAVデータのデコードエラー")
            return None
        except OSError as e:
            log_exception(e, "OGGエクスポート中にI/Oエラー発生")
            return None
        except Exception as e:
            log_exception(e, "WAVからOGGへの変換中に予期せぬエラー")
            return None
    finally:
        if wav_io:
            wav_io.close()
        ogg_buffer.close()
