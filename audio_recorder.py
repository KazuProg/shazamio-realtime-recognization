import collections
import pyaudio
import threading
import time
import logging
from typing import Deque, Optional

from logger_config import setup_logger, log_exception

# このモジュール用のロガーを設定
logger = setup_logger(logger_name="audio_recorder", log_level=logging.INFO)


class AudioRecorder:
    """
    別スレッドで音声を継続的に録音し、直近N秒の音声データを取得できるクラス。
    """

    def __init__(
        self,
        audio_format: int,
        channels: int,
        rate: int,
        chunk_size: int,
        buffer_seconds: int,
    ):
        """
        AudioRecorderの初期化を行います。

        Args:
            audio_format: 音声フォーマット（例：pyaudio.paInt16）
            channels: チャンネル数（1:モノラル、2:ステレオ）
            rate: サンプリングレート（Hz）
            chunk_size: 一度に処理する音声データのサイズ
            buffer_seconds: バッファに保持する音声の最大秒数
        """
        self.audio_format: int = audio_format
        self.channels: int = channels
        self.rate: int = rate
        self.chunk_size: int = chunk_size
        self.sample_width: int = pyaudio.get_sample_size(self.audio_format)

        # 必要なバッファサイズを計算
        self.buffer_max_chunks: int = int(self.rate / self.chunk_size * buffer_seconds)

        # メモリ効率の良いバッファ（双方向キュー）を使用
        self.audio_buffer: Deque[bytes] = collections.deque(
            maxlen=self.buffer_max_chunks
        )

        # プライベート変数
        self._audio_interface: Optional[pyaudio.PyAudio] = None
        self._audio_stream: Optional[pyaudio.Stream] = None
        self._recording_thread: Optional[threading.Thread] = None
        self._is_recording: bool = False

        # スレッド同期用のリソース
        self._lock: threading.RLock = threading.RLock()  # 再入可能ロックを使用
        self._stream_error_count: int = 0
        self._max_stream_errors: int = 5  # 連続エラー発生の最大許容回数
        self._buffer_access_count: int = 0  # バッファアクセス回数のカウンター（診断用）

        # 設定と属性のログ出力
        logger.debug(
            f"AudioRecorder初期化完了: rate={rate}Hz, channels={channels}, "
            f"buffer={buffer_seconds}秒, chunk={chunk_size}バイト"
        )

    def __del__(self) -> None:
        """
        デストラクタ - リソースを確実に解放します。
        """
        self.stop()  # 録音中であれば確実に停止
        self._close_stream()  # ストリームを閉じる

    def _open_stream(self) -> bool:
        """
        音声入力ストリームを開きます。

        Returns:
            bool: ストリームを正常に開けた場合はTrue、失敗した場合はFalse
        """
        # すでにストリームが開いている場合は何もしない
        with self._lock:
            if self._audio_stream is not None and self._audio_interface is not None:
                logger.debug("ストリームはすでに開いています")
                return True

        try:
            self._audio_interface = pyaudio.PyAudio()
            self._audio_stream = self._audio_interface.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk_size,
            )
            logger.debug("音声入力ストリームを開きました")
            return True
        except pyaudio.PyAudioError as e:
            log_exception(e, "音声ストリームの初期化に失敗しました")
            self._close_stream()  # すでに作成されたリソースをクリーンアップ
            return False
        except OSError as e:
            log_exception(e, "オーディオデバイスへのアクセス中にOSエラーが発生しました")
            self._close_stream()
            return False
        except Exception as e:
            log_exception(e, "音声ストリームのオープン中に予期せぬエラーが発生しました")
            self._close_stream()
            return False

    def _close_stream(self) -> None:
        """
        音声入力ストリームを閉じ、リソースを解放します。
        """
        with self._lock:
            try:
                if self._audio_stream:
                    try:
                        self._audio_stream.stop_stream()
                        self._audio_stream.close()
                        logger.debug("音声ストリームを閉じました")
                    except Exception as e:
                        log_exception(e, "音声ストリームの終了中にエラーが発生しました")
                    finally:
                        self._audio_stream = None

                if self._audio_interface:
                    try:
                        self._audio_interface.terminate()
                        logger.debug("PyAudioインターフェースを終了しました")
                    except Exception as e:
                        log_exception(
                            e, "PyAudioインターフェースの終了中にエラーが発生しました"
                        )
                    finally:
                        self._audio_interface = None

                # オーディオバッファのクリア（メモリ解放）
                buffer_size = len(self.audio_buffer)
                self.audio_buffer.clear()
                logger.debug(
                    f"音声バッファをクリアしました（{buffer_size}チャンクを削除）"
                )

            except Exception as e:
                log_exception(e, "ストリームのクローズ中に予期せぬエラーが発生しました")

    def _reset_stream(self) -> bool:
        """
        問題が発生した場合にストリームをリセットします。

        Returns:
            bool: ストリームのリセットに成功した場合はTrue、失敗した場合はFalse
        """
        logger.info("音声ストリームのリセットを試みています...")

        # リセット前の状態を保存
        was_recording = self._is_recording

        # 録音中であれば一時的に停止
        if was_recording:
            self._is_recording = False
            if self._recording_thread and self._recording_thread.is_alive():
                # 短い待機でスレッドの処理が進むようにする
                time.sleep(0.1)

        # ストリームを閉じる（ロック内で実行）
        self._close_stream()
        # リソース解放のための短い待機
        time.sleep(0.5)

        # 新しいストリームを開く
        result = self._open_stream()

        # 以前録音中だった場合は録音を再開
        if was_recording and result:
            self._is_recording = True

        if result:
            logger.info("音声ストリームのリセットに成功しました")
        else:
            logger.error("音声ストリームのリセットに失敗しました")
        return result

    def _record_loop(self) -> None:
        """
        音声データを継続的に読み込み、バッファに格納するループ。
        """
        if not self._open_stream():
            logger.error("録音ストリームの初期化に失敗したため、録音を中止します。")
            self._is_recording = False
            return

        self._stream_error_count = 0
        read_errors: int = 0  # 連続読み取りエラー数
        logger.info("録音スレッド開始。")

        try:
            # 最適化: 頻繁にアクセスする変数をローカルにキャッシュ
            chunk_size = self.chunk_size
            lock = self._lock
            audio_buffer = self.audio_buffer
            max_errors = self._max_stream_errors

            while self._is_recording:
                try:
                    # ストリームが有効かチェック
                    if not self._audio_stream or not self._audio_interface:
                        if not self._reset_stream():
                            logger.error(
                                "ストリームの再初期化に失敗しました。録音を停止します。"
                            )
                            break

                    # 音声データの読み取り
                    data: bytes = self._audio_stream.read(
                        chunk_size, exception_on_overflow=False
                    )

                    # バッファに追加（スレッドセーフな操作）
                    with lock:
                        audio_buffer.append(data)
                        self._buffer_access_count += 1

                    # エラーが解消されたらカウンタをリセット
                    if read_errors > 0:
                        logger.debug(
                            f"{read_errors}回のエラー後、正常に読み取りが再開しました"
                        )
                        read_errors = 0
                    self._stream_error_count = 0

                except IOError as e:
                    self._stream_error_count += 1
                    read_errors += 1

                    if e.errno == pyaudio.paInputOverflowed:
                        logger.warning(
                            "マイク入力バッファがオーバーフローしました。一部の音声データが失われた可能性があります。"
                        )
                    else:
                        log_exception(e, "録音ループ中にIOエラーが発生しました")

                    # パフォーマンス最適化: エラー頻度に応じて待機時間を調整
                    wait_time = min(0.1 * read_errors, 1.0)  # 最大1秒まで待機時間を増加

                    # 連続エラーが閾値を超えたら処理
                    if self._stream_error_count > max_errors:
                        logger.warning(
                            f"連続で{max_errors}回以上のエラーが発生したため、ストリームをリセットします。"
                        )
                        if not self._reset_stream():
                            logger.error(
                                "ストリームのリセットに失敗しました。録音を停止します。"
                            )
                            break
                        read_errors = 0  # リセット後はエラーカウントもリセット
                    else:
                        # 軽微なエラーなら待機後に再試行
                        time.sleep(wait_time)

                except Exception as e:
                    log_exception(e, "録音ループ中に予期せぬエラーが発生しました")
                    self._stream_error_count += 1
                    read_errors += 1

                    if self._stream_error_count > max_errors:
                        logger.error("複数回エラーが発生したため、録音を停止します。")
                        break

                    # 深刻でないエラーの場合は待機して再試行
                    time.sleep(0.2)

        except Exception as e:
            log_exception(e, "録音ループの実行中に予期せぬエラー")
        finally:
            with self._lock:
                # 終了時の状態確認
                logger.debug(f"録音終了時のバッファサイズ: {len(audio_buffer)}チャンク")
                logger.debug(
                    f"録音中のバッファアクセス回数: {self._buffer_access_count}回"
                )

                # リソース解放
                self._close_stream()
                self._is_recording = False
                logger.info("録音スレッド終了。")

    def start(self) -> bool:
        """
        録音を開始します。別スレッドで音声キャプチャを実行します。

        Returns:
            bool: 録音の開始に成功した場合はTrue、すでに録音中だった場合はFalse
        """
        with self._lock:
            if self._is_recording:
                logger.info("既に録音中です。")
                return False

            self._is_recording = True

            # バッファアクセス回数のリセット
            self._buffer_access_count = 0

            # 新しいスレッドで録音を開始
            self._recording_thread = threading.Thread(target=self._record_loop)
            self._recording_thread.daemon = True  # メインスレッド終了時に自動終了

        self._recording_thread.start()
        logger.info("録音を開始しました。")
        return True

    def stop(self) -> None:
        """
        録音を停止します。録音スレッドを終了し、音声ストリームを閉じます。
        """
        with self._lock:
            if not self._is_recording:
                logger.info("録音は開始されていません。")
                return

            logger.info("録音を停止しています...")
            self._is_recording = False
            recording_thread = (
                self._recording_thread
            )  # ロック外で使うためにローカル変数に保存

        # ロック外でスレッド終了を待機（デッドロック防止）
        if recording_thread:
            try:
                recording_thread.join(timeout=5)  # タイムアウト付きで終了を待つ
                if recording_thread.is_alive():
                    logger.warning("録音スレッドが正常に終了しませんでした。")
            except Exception as e:
                log_exception(e, "録音スレッド終了待機中にエラー")

        # 明示的にストリームを閉じる
        self._close_stream()
        logger.info("録音を停止しました。")

    def get_recorded_duration(self) -> float:
        """
        録音された音声データの総時間を秒単位で取得します。

        Returns:
            float: 録音された音声の長さ（秒）
        """
        with self._lock:
            return len(self.audio_buffer) * self.chunk_size / self.rate

    def get_recent_audio_bytes(self, duration_seconds: int) -> bytes:
        """
        指定された秒数分の最新の音声データをバイト列として取得します。
        バッファに十分なデータがない場合は、利用可能な全データを返します。

        Args:
            duration_seconds: 取得したい音声データの秒数

        Returns:
            bytes: 指定された秒数分の最新の音声データ
        """
        if duration_seconds <= 0:
            logger.warning("要求された音声データの長さが0秒以下です。")
            return b""

        try:
            # チャンク数を計算
            num_chunks_to_get: int = int(self.rate / self.chunk_size * duration_seconds)

            # バッファのスナップショットを取得（コピーを最小限に）
            with self._lock:
                if not self.audio_buffer:
                    logger.warning("音声バッファが空です。")
                    return b""

                buffer_len = len(self.audio_buffer)
                # 必要なチャンク数分だけをリストとして抽出
                chunks_to_retrieve = list(self.audio_buffer)[
                    -min(num_chunks_to_get, buffer_len) :
                ]

            # 取得したデータのサイズと実際の長さを計算
            result = b"".join(chunks_to_retrieve)
            result_size = len(result)
            actual_duration = len(chunks_to_retrieve) * self.chunk_size / self.rate

            if actual_duration < duration_seconds * 0.9:  # 10%以上短い場合に警告
                logger.warning(
                    f"要求された長さ（{duration_seconds}秒）よりも短いデータしか取得できませんでした"
                    f"（実際: {actual_duration:.2f}秒）"
                )
            else:
                logger.debug(
                    f"要求: {duration_seconds}秒、取得: {actual_duration:.2f}秒の音声データ"
                    f"（{result_size}バイト、{len(chunks_to_retrieve)}チャンク）"
                )

            return result

        except Exception as e:
            log_exception(e, "音声データの取得中にエラーが発生しました")
            return b""

    def is_recording(self) -> bool:
        """
        現在録音中かどうかを返します。

        Returns:
            bool: 録音中の場合はTrue、それ以外はFalse
        """
        with self._lock:
            return self._is_recording
