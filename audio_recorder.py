import collections
import pyaudio
import threading
import time


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
        self.audio_format = audio_format
        self.channels = channels
        self.rate = rate
        self.chunk_size = chunk_size
        self.sample_width = pyaudio.get_sample_size(self.audio_format)

        self.buffer_max_chunks = int(self.rate / self.chunk_size * buffer_seconds)
        self.audio_buffer = collections.deque(maxlen=self.buffer_max_chunks)

        self._audio_interface = None
        self._audio_stream = None
        self._recording_thread = None
        self._is_recording = False
        self._lock = threading.Lock()

    def _open_stream(self):
        """
        音声入力ストリームを開きます。
        """
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=self.audio_format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk_size,
        )

    def _close_stream(self):
        """
        音声入力ストリームを閉じ、リソースを解放します。
        """
        if self._audio_stream:
            self._audio_stream.stop_stream()
            self._audio_stream.close()
            self._audio_stream = None
        if self._audio_interface:
            self._audio_interface.terminate()
            self._audio_interface = None
        self.audio_buffer.clear()

    def _record_loop(self):
        """
        音声データを継続的に読み込み、バッファに格納するループ。
        """
        try:
            self._open_stream()
            print("録音スレッド開始。")
            while self._is_recording:
                try:
                    data = self._audio_stream.read(
                        self.chunk_size, exception_on_overflow=False
                    )
                    with self._lock:
                        self.audio_buffer.append(data)
                except IOError as e:
                    if e.errno == pyaudio.paInputOverflowed:
                        print(
                            "警告: マイク入力バッファがオーバーフローしました。一部の音声データが失われた可能性があります。"
                        )
                    else:
                        print(f"録音ループ中にIOErrorが発生しました: {e}")
                        # エラーが頻発する場合はストリームの再起動などを検討
                        time.sleep(0.1)  # 短い待機
                except Exception as e:
                    print(f"録音ループ中に予期せぬエラーが発生しました: {e}")
                    break  # ループを抜ける
        except Exception as e:
            print(f"ストリームのオープンまたは録音ループの準備中にエラー: {e}")
        finally:
            self._close_stream()
            print("録音スレッド終了。")

    def start(self):
        """
        録音を開始します。別スレッドで音声キャプチャを実行します。
        """
        if self._is_recording:
            print("既に録音中です。")
            return

        self._is_recording = True
        self._recording_thread = threading.Thread(target=self._record_loop)
        self._recording_thread.daemon = True  # メインスレッド終了時に自動終了
        self._recording_thread.start()
        print("録音を開始しました。")

    def stop(self):
        """
        録音を停止します。録音スレッドを終了し、音声ストリームを閉じます。
        """
        if not self._is_recording:
            print("録音は開始されていません。")
            return

        self._is_recording = False
        if self._recording_thread:
            self._recording_thread.join(timeout=5)  # タイムアウト付きで終了を待つ
            if self._recording_thread.is_alive():
                print("警告: 録音スレッドが正常に終了しませんでした。")
        print("録音を停止しました。")

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
        if not self._is_recording and not self.audio_buffer:
            print("録音データがありません。")
            return b""

        num_chunks_to_get = int(self.rate / self.chunk_size * duration_seconds)
        with self._lock:
            # バッファのコピーを作成して操作（イテレーション中の変更を避けるため）
            current_buffer_list = list(self.audio_buffer)

        if not current_buffer_list:
            return b""

        # 必要なチャンク数、またはバッファにある全チャンク数のうち少ない方
        chunks_to_retrieve = current_buffer_list[-num_chunks_to_get:]
        return b"".join(chunks_to_retrieve)
