import wave
import io
import logging
from typing import Optional, Final, Dict, Any

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from logger_config import setup_logger, log_exception

# このモジュール用のロガーを設定
logger = setup_logger(logger_name="audio_converter", log_level=logging.INFO)

# 定数定義
DEFAULT_WAV_BITRATE: Final[int] = 16000  # デフォルトのWAVビットレート
DEFAULT_OGG_QUALITY: Final[float] = 5.0  # oggエクスポート時の品質（0-10）

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
    # 入力チェック
    if not pcm_data:
        logger.warning("変換対象のPCMデータが空です")
        return None

    if channels <= 0 or rate <= 0 or sample_width <= 0:
        logger.error(
            f"無効なパラメータ: channels={channels}, rate={rate}, sample_width={sample_width}"
        )
        return None

    # メモリ効率のためにByteIOを使用
    wav_buffer: io.BytesIO = io.BytesIO()
    try:
        # WAVファイルとしてデータを書き込み
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm_data)

        # 結果を取得
        result = wav_buffer.getvalue()
        logger.debug(
            f"PCMからWAVへの変換成功: サイズ={len(result)}バイト, "
            f"チャンネル={channels}, サンプリングレート={rate}Hz"
        )
        return result
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
        # リソース解放を確実に行う
        wav_buffer.close()


def convert_wav_to_ogg_bytes(
    wav_data: bytes,
    sample_rate: int,
    channels: int,
    quality: float = DEFAULT_OGG_QUALITY,
) -> Optional[bytes]:
    """
    WAV形式のバイト列をogg形式のバイト列に変換します。

    Args:
        wav_data: 変換するWAV音声データ
        sample_rate: サンプリングレート（Hz）
        channels: チャンネル数
        quality: OGG変換時の品質（0.0-10.0、デフォルト: 5.0）

    Returns:
        Optional[bytes]: OGG形式に変換されたバイト列データ。変換失敗時はNone
    """
    # 入力チェック
    if not wav_data:
        logger.warning("変換対象のWAVデータが空です")
        return None

    if sample_rate <= 0 or channels <= 0:
        logger.error(
            f"無効なパラメータ: sample_rate={sample_rate}, channels={channels}"
        )
        return None

    # メモリリソース
    ogg_buffer: Optional[io.BytesIO] = None
    wav_io: Optional[io.BytesIO] = None

    try:
        wav_io = io.BytesIO(wav_data)
        ogg_buffer = io.BytesIO()

        # AudioSegmentを使用して変換
        try:
            audio_segment: AudioSegment = AudioSegment.from_wav(wav_io)

            # エクスポート設定
            export_options: Dict[str, Any] = {
                "format": "ogg",
                "bitrate": str(sample_rate),
                "parameters": ["-q:a", str(quality)],
            }

            # OGG形式にエクスポート
            audio_segment.export(ogg_buffer, **export_options)

            # 結果を取得
            result = ogg_buffer.getvalue()
            compression_ratio = len(result) / len(wav_data) * 100.0

            logger.debug(
                f"WAVからOGGへの変換成功: WAV={len(wav_data)}バイト→OGG={len(result)}バイト "
                f"(圧縮率: {compression_ratio:.1f}%)"
            )
            return result

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
        # リソース解放を確実に行う
        if wav_io:
            wav_io.close()
        if ogg_buffer:
            ogg_buffer.close()


def get_audio_format_info(
    audio_data: bytes, format_type: str = "auto"
) -> Optional[Dict[str, Any]]:
    """
    音声データのフォーマット情報を取得します。

    Args:
        audio_data: 分析する音声データ
        format_type: 音声フォーマットタイプ ("wav", "ogg", "auto"など)

    Returns:
        Optional[Dict[str, Any]]: フォーマット情報を含む辞書。解析失敗時はNone
    """
    if not audio_data:
        logger.warning("分析対象の音声データが空です")
        return None

    audio_io: Optional[io.BytesIO] = None

    try:
        audio_io = io.BytesIO(audio_data)

        # WAV形式の解析
        if format_type.lower() in ("wav", "wave", "auto"):
            try:
                with wave.open(audio_io, "rb") as wf:
                    return {
                        "format": "wav",
                        "channels": wf.getnchannels(),
                        "sample_rate": wf.getframerate(),
                        "sample_width": wf.getsampwidth(),
                        "frames": wf.getnframes(),
                        "duration": wf.getnframes() / wf.getframerate(),
                        "size_bytes": len(audio_data),
                    }
            except (wave.Error, EOFError) as e:
                if format_type.lower() != "auto":
                    logger.warning(f"WAVとして解析できませんでした: {e}")
                    return None
                # autoモードでは次の形式を試す

        # OGG/Vorbis形式の解析（pydubを使用）
        if format_type.lower() in ("ogg", "auto"):
            try:
                audio_io.seek(0)  # 先頭に戻す
                audio = AudioSegment.from_file(audio_io, format="ogg")
                return {
                    "format": "ogg",
                    "channels": audio.channels,
                    "sample_rate": audio.frame_rate,
                    "sample_width": audio.sample_width,
                    "duration": len(audio) / 1000.0,  # ミリ秒から秒に変換
                    "size_bytes": len(audio_data),
                }
            except Exception as e:
                if format_type.lower() != "auto":
                    logger.warning(f"OGGとして解析できませんでした: {e}")

        # 判別できなかった場合
        if format_type.lower() == "auto":
            logger.warning("音声フォーマットを自動判別できませんでした")
        return None

    except Exception as e:
        log_exception(
            e, f"音声データの解析中にエラーが発生しました（形式: {format_type}）"
        )
        return None
    finally:
        if audio_io:
            audio_io.close()
