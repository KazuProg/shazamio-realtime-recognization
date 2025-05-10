import asyncio
from typing import Optional, Callable, Any, Dict

import pyaudio
from shazamio import Shazam

from audio_converter import convert_pcm_to_wav_bytes, convert_wav_to_ogg_bytes
from audio_recorder import AudioRecorder


class ShazamRealtimeRecognizer:
    """
    リアルタイムで音声を録音し、Shazamを使用して楽曲を認識するクラス。

    このクラスは、指定された時間間隔で音声を録音し、Shazam APIを使用して
    楽曲を認識します。認識結果はコールバック関数を通じて通知されます。

    Attributes:
        audio_format (int): 音声フォーマット（デフォルト: pyaudio.paInt16）
        channels (int): チャンネル数（デフォルト: 1）
        rate (int): サンプリングレート（デフォルト: 16000）
        chunk_size (int): 音声データのチャンクサイズ（デフォルト: 1024）
        recognize_seconds (int): 認識に使用する音声の長さ（秒）（デフォルト: 5）
        recognize_timeout (int): 認識のタイムアウト時間（秒）（デフォルト: 5）
        recognize_interval (int): 認識の間隔（秒）（デフォルト: 1）
        recognition_callback (Optional[Callable[[Optional[Dict[str, Any]]], None]]): 認識結果を処理するコールバック関数
        stop_on_found (bool): 楽曲が認識されたら停止するかどうか（デフォルト: True）
    """

    def __init__(
        self,
        audio_format: int = pyaudio.paInt16,
        channels: int = 1,
        rate: int = 16000,
        chunk_size: int = 1024,
        recognize_seconds: int = 5,
        recognize_timeout: int = 5,
        recognize_interval: int = 1,
        recognition_callback: Optional[
            Callable[[Optional[Dict[str, Any]]], None]
        ] = None,
        stop_on_found: bool = True,
    ) -> None:
        """
        初期化メソッド。

        Args:
            audio_format (int): 音声フォーマット
            channels (int): チャンネル数
            rate (int): サンプリングレート
            chunk_size (int): 音声データのチャンクサイズ
            recognize_seconds (int): 認識に使用する音声の長さ（秒）
            recognize_timeout (int): 認識のタイムアウト時間（秒）
            recognize_interval (int): 認識の間隔（秒）
            recognition_callback (Optional[Callable[[Optional[Dict[str, Any]]], None]]): 認識結果を処理するコールバック関数
            stop_on_found (bool): 楽曲が認識されたら停止するかどうか
        """
        self.audio_format = audio_format
        self.channels = channels
        self.rate = rate
        self.chunk_size = chunk_size
        self.recognize_seconds = recognize_seconds
        self.recognize_timeout = recognize_timeout
        self.recognize_interval = recognize_interval
        self.recognition_callback = recognition_callback
        self.stop_on_found = stop_on_found

        self.shazam = Shazam()
        self.recorder = AudioRecorder(
            audio_format=self.audio_format,
            channels=self.channels,
            rate=self.rate,
            chunk_size=self.chunk_size,
            buffer_seconds=self.recognize_seconds + self.recognize_interval,
        )

        self._is_recognizing = False

    async def start_recognition(self) -> None:
        """
        音声認識を開始します。

        既に認識処理が開始されている場合は、何も行いません。
        """
        if self._is_recognizing:
            print("既に認識処理は開始されています。")
            return

        self._is_recognizing = True

        self.recorder.start()
        asyncio.create_task(self._recognition_loop())

    def stop_recognition(self) -> None:
        """
        音声認識を停止します。

        認識処理が開始されていない場合は、何も行いません。
        """
        if self._is_recognizing:
            self._is_recognizing = False
            self.recorder.stop()
            print("認識処理を停止しました。")
        else:
            print("認識処理は開始されていません。")

    async def _recognition_loop(self) -> None:
        """
        音声認識のメインループ。

        指定された間隔で音声を録音し、Shazamを使用して楽曲を認識します。
        認識結果はコールバック関数を通じて通知されます。
        """
        next_recognize_time = self.recognize_interval
        while self._is_recognizing:
            recorded_time = self.recorder.get_recorded_duration()
            if recorded_time < next_recognize_time:
                await asyncio.sleep(self.recognize_interval * 0.1)
                continue

            next_recognize_time += self.recognize_interval

            ogg_audio_data_bytes = await self._get_recent_ogg_bytes(
                self.recognize_seconds
            )
            if not ogg_audio_data_bytes:
                continue

            try:
                out = await self.shazam.recognize(ogg_audio_data_bytes)

                if out.get("track", False):
                    try:
                        self.recognition_callback(out)
                    except Exception as e:
                        print(f"コールバック関数でエラー: {e}")

                    if self.stop_on_found:
                        self.stop_recognition()
                        break
                else:
                    try:
                        self.recognition_callback(None)
                    except Exception as e:
                        print(f"コールバック関数でエラー: {e}")
            except Exception as e:
                print(f"Shazam でのエラー: {e}")

            if self.recognize_seconds <= recorded_time:
                print("指定した時間内に楽曲が認識できませんでした。")
                self.stop_recognition()
                break

            await asyncio.sleep(0.1)  # CPU使用率を下げる

        self.recorder.stop()

    async def _get_recent_ogg_bytes(self, duration_seconds: int) -> Optional[bytes]:
        """
        指定された秒数分の最新の音声データをOGG形式のバイト列として取得します。

        Args:
            duration_seconds (int): 取得する音声データの長さ（秒）

        Returns:
            Optional[bytes]: OGG形式の音声データ。取得に失敗した場合はNone
        """
        pcm_audio_data_bytes = self.recorder.get_recent_audio_bytes(duration_seconds)
        if not pcm_audio_data_bytes:
            return None

        wav_audio_data_bytes = convert_pcm_to_wav_bytes(
            pcm_audio_data_bytes,
            self.channels,
            self.rate,
            self.recorder.sample_width,
        )
        if not wav_audio_data_bytes:
            return None

        ogg_audio_data_bytes = convert_wav_to_ogg_bytes(
            wav_audio_data_bytes,
            self.rate,
            self.channels,
        )
        if not ogg_audio_data_bytes:
            return None

        return ogg_audio_data_bytes
