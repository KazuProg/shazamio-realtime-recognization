import asyncio
import os
import sys
import logging
import signal
import webbrowser
import requests
import dotenv
from typing import (
    Dict,
    Any,
    Optional,
    Final,
    NoReturn,
    Literal,
)
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

dotenv.load_dotenv()

from shazam_realtime_recognizer import ShazamRealtimeRecognizer
from logger_config import setup_logger, log_exception

# このモジュール用のロガーを設定
logger = setup_logger(logger_name="main", log_level=logging.INFO)

# 定数定義
MAX_RECOGNITION_ATTEMPTS: Final[int] = 3  # 認識試行の最大回数
EXIT_SUCCESS: Final[int] = 0  # 正常終了コード
EXIT_ERROR: Final[int] = 1  # エラー終了コード
YOUTUBE_API_KEY: Final[str] = os.environ.get("YOUTUBE_API_KEY", "")  # YouTube Data API キー

# Seleniumドライバーをグローバル変数として保持
_chrome_driver: Optional[webdriver.Chrome] = None

# 認識開始時間を記録するグローバル変数
_recognition_start_time: Optional[float] = None

def search_youtube(query: str) -> Optional[str]:
    """
    YouTube Data APIを使用して検索クエリに基づいて動画を検索し、
    最初の検索結果の動画IDを返します。

    Args:
        query: 検索クエリ文字列

    Returns:
        Optional[str]: 見つかった場合は動画ID、見つからない場合はNone
    """
    try:
        if not YOUTUBE_API_KEY:
            logger.error("YouTube API キーが設定されていません。環境変数 YOUTUBE_API_KEY を設定してください。")
            print("YouTube API キーが設定されていません。環境変数 YOUTUBE_API_KEY を設定してください。")
            return None

        # YouTube Data API v3 検索エンドポイント
        url = "https://www.googleapis.com/youtube/v3/search"
        
        # パラメータ設定
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": 1,
            "key": YOUTUBE_API_KEY
        }
        
        print(f"API リクエスト実行: URL={url}, クエリ={query}")
        
        # リクエスト実行
        response = requests.get(url, params=params)
        
        # レスポンスの詳細をログと画面に出力
        print(f"APIレスポンスステータス: {response.status_code}")
        logger.info(f"APIレスポンスステータス: {response.status_code}")
        
        # エラー時はレスポンス本文も出力
        if response.status_code != 200:
            error_text = response.text
            print(f"APIエラー詳細: {error_text}")
            logger.error(f"APIエラー詳細: {error_text}")
            response.raise_for_status()  # エラーを発生させる
        
        # レスポンス処理
        data = response.json()
        
        # デバッグ用に結果の概要を出力
        print(f"API結果: {len(data.get('items', []))}件の動画が見つかりました")
        
        # 検索結果がない場合
        if not data.get("items"):
            logger.info(f"「{query}」の検索結果が見つかりませんでした。")
            print(f"「{query}」の検索結果が見つかりませんでした。")
            return None
            
        # 最初の結果から動画IDを取得
        video_id = data["items"][0]["id"]["videoId"]
        print(f"見つかった動画ID: {video_id}")
        return video_id
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"YouTube API リクエスト中にHTTPエラーが発生しました: {e}"
        log_exception(e, error_msg)
        print(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"YouTube API リクエスト中にエラーが発生しました: {e}"
        log_exception(e, error_msg)
        print(error_msg)
    except KeyError as e:
        error_msg = f"YouTube APIレスポンスの解析中にエラーが発生しました: {e}"
        log_exception(e, error_msg)
        print(error_msg)
    except Exception as e:
        error_msg = f"YouTube検索中に予期せぬエラーが発生しました: {e}"
        log_exception(e, error_msg)
        print(error_msg)
    
    return None


def open_youtube_video(video_id: str, method: Literal["browser", "selenium"] = "browser", 
                      target_url: Optional[str] = None, 
                      input_selector: Optional[str] = None) -> bool:
    """
    指定されたYouTube動画IDを利用してブラウザで表示します。
    
    method="browser": 通常のブラウザでYouTubeを開く
    method="selenium": Seleniumを使用して指定URLのinput要素に動画IDを入力

    Args:
        video_id: YouTube動画ID
        method: 開く方法（"browser"または"selenium"）
        target_url: seleniumモードで開くURL
        input_selector: input要素のCSS/XPathセレクタ

    Returns:
        bool: 成功した場合はTrue、失敗した場合はFalse
    """
    global _chrome_driver
    
    try:
        if method == "browser":
            # 通常のブラウザでYouTubeを開く
            url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"YouTubeビデオを開きます: {url}")
            return webbrowser.open(url)
        
        elif method == "selenium":
            # seleniumを使用して特定のページのinput要素に入力
            if not target_url or not input_selector:
                logger.error("Seleniumモードではtarget_urlとinput_selectorが必要です")
                print("SeleniumモードではターゲットURLとinput要素のセレクタが必要です")
                return False
            
            # ドライバーがまだ初期化されていないか、既に閉じられている場合は新しく作成
            driver_needs_init = False
            
            if _chrome_driver is None:
                driver_needs_init = True
            else:
                # ドライバーが生きているか確認
                try:
                    # 簡単な操作を試して生きているか確認
                    _chrome_driver.current_url
                except (WebDriverException, Exception) as e:
                    logger.info(f"既存のブラウザセッションが終了しています。新しく開始します: {e}")
                    driver_needs_init = True
                    # 古いドライバーが残っている場合はクリーンアップ
                    try:
                        if _chrome_driver:
                            _chrome_driver.quit()
                    except:
                        pass
                    _chrome_driver = None
            
            if driver_needs_init:
                logger.info(f"新しいChromeセッションを開始します: {target_url}")
                print(f"Chromeを起動して {target_url} を開きます...")
                
                # Chromeオプション設定
                chrome_options = Options()
                # 以下の行をコメント解除するとヘッドレスモードになります
                # chrome_options.add_argument("--headless")
                
                # WebDriverの初期化
                _chrome_driver = webdriver.Chrome(options=chrome_options)
                _chrome_driver.get(target_url)
                print(f"新しいブラウザでページを読み込みました: {target_url}")
            else:
                # 既存のドライバーを使用、必要に応じてURLを更新
                current_url = _chrome_driver.current_url
                if current_url != target_url:
                    logger.info(f"既存のブラウザで新しいURLに移動します: {target_url}")
                    print(f"既存のブラウザで新しいURLに移動します: {target_url}")
                    _chrome_driver.get(target_url)
                else:
                    logger.info(f"既存のブラウザでinput要素を更新します: {input_selector}")
                    print(f"既存のブラウザでinput要素を更新します")
            
            try:
                # input要素が見つかるまで待機（最大10秒）
                wait = WebDriverWait(_chrome_driver, 10)
                input_element = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, input_selector))
                )
                load_button = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".load button"))
                )
                
                # 入力欄をクリアして動画IDを入力
                input_element.clear()
                input_element.send_keys(video_id)
                print(f"入力フォームに動画ID ({video_id}) を入力しました")
                
                load_button.click()

                # ブラウザは開いたままにし、制御を返す（待機しない）
                print("Chromeブラウザは開いたままになっています。続行するには再度Enterを押してください。")
                
                # ブラウザクローズのロジックは削除し、すぐに制御を返す
                return True
                
            except Exception as e:
                logger.error(f"Selenium操作中にエラーが発生しました: {e}")
                print(f"ブラウザ操作中にエラーが発生しました: {e}")
                # エラー時のみドライバーをクリーンアップし、グローバル変数をリセット
                if _chrome_driver:
                    _chrome_driver.quit()
                    _chrome_driver = None
                return False
        
        else:
            logger.error(f"未対応のメソッドが指定されました: {method}")
            print(f"未対応の開き方が指定されました: {method}")
            return False
            
    except Exception as e:
        log_exception(e, "動画を開く際にエラーが発生しました")
        print(f"動画を開く際にエラーが発生しました: {e}")
        # 重大なエラー時はドライバーをリセット
        if method == "selenium" and _chrome_driver:
            try:
                _chrome_driver.quit()
            except:
                pass
            _chrome_driver = None
        return False


def recognition_callback(result: Optional[Dict[str, Any]]) -> None:
    """認識結果を処理するコールバック関数です。"""
    global _recognition_start_time
    
    recognition_succeeded = False  # 認識成功フラグ
    
    try:
        logger.info(f"認識コールバック開始時点での_recognition_start_time: {_recognition_start_time}")
        print(f"コールバック時の認識開始時間: {_recognition_start_time}")
        
        if result is None:
            logger.info("認識できませんでした。")
            print("認識できませんでした。")  # ユーザーへの表示として残す
            return

        recognition_succeeded = True  # 認識が成功した
        
        offset = int(result["matches"][0]["offset"])

        # 結果から情報を抽出
        track_info = result.get("track", {})
        title: str = track_info.get("title", "タイトル不明")
        artist: str = track_info.get("subtitle", "アーティスト不明")

        # 認識結果をログに記録
        logger.info(f"認識結果: {title} / {artist}")

        # ユーザーへの表示
        #clear_console()
        print(f"\n  {title} / {artist}\n")

        # YouTube検索クエリを作成
        search_query = f"{title} {artist} official"
        print(f"YouTubeで検索中: {search_query}")
        
        # YouTube検索を実行
        video_id = search_youtube(search_query)
        
        # フォーム入力直前に全体の経過時間を計算
        total_elapsed_time = 0
        if _recognition_start_time is not None:
            total_elapsed_time = time.time() - _recognition_start_time
            logger.info(f"認識開始からここまでの総経過時間: {total_elapsed_time:.2f}秒")
            print(f"処理時間: {total_elapsed_time:.2f}秒")
        else:
            logger.warning("認識開始時間が記録されていません")
            print("警告: 認識開始時間が記録されていません")
        
        # offsetに総経過時間を加算
        offset += total_elapsed_time
        
        # 最終的なoffsetを小数点第1位まで保持
        final_offset = round(offset, 2)
        
        logger.info(f"最終調整後のoffset: {final_offset}秒 (元のoffset + 処理時間{total_elapsed_time:.2f}秒 = {offset:.2f}秒を小数第1位まで)")
        print(f"最終offset: {final_offset}秒")
        
        if video_id:
            # 動画を開くメソッドを選択（browser/selenium）
            # ★ 以下を環境に合わせて変更してください ★
            # 例: method="selenium", target_url="https://example.com/form", input_selector="#videoIdInput"
            method = "selenium"  # または "selenium"
            target_url = "https://n100-ubuntu.kazuprog.work/youtube-vj/"  # seleniumモードで開くURL
            input_selector = "#input-videoId"  # input要素のセレクタ
            if open_youtube_video(f"{video_id}@{final_offset}", method, target_url, input_selector):
                if method == "browser":
                    print(f"YouTubeで動画を開きました: https://www.youtube.com/watch?v={video_id}")
                else:
                    print(f"Chrome で {target_url} を開き、入力フォームに動画ID ({video_id}@{final_offset}) を入力しました")
            else:
                print("YouTubeで動画を開けませんでした。")
        else:
            print("YouTubeで関連動画が見つかりませんでした。")

        # 処理が完了したら、3秒後に次の認識の準備を促すメッセージを表示
        print("\n3秒後に次の認識の準備が整います...")
        time.sleep(3)
        print("\n楽曲認識を開始するにはEnterキーを押してください。Ctrl+Cで終了します。")

    except Exception as e:
        log_exception(e, "認識結果の処理中にエラーが発生しました")
    finally:
        # 認識が成功した場合のみ認識開始時間をリセット
        if recognition_succeeded:
            _recognition_start_time = None
            logger.info("認識成功のため認識開始時間をリセットしました")


def initialize_browser(target_url: str, input_selector: str) -> bool:
    """
    Seleniumブラウザを初期化します。プログラム起動時に呼び出されます。

    Args:
        target_url: 開くURLのアドレス
        input_selector: 入力要素のCSSセレクタ

    Returns:
        bool: 初期化が成功したらTrue、失敗したらFalse
    """
    global _chrome_driver

    if _chrome_driver is not None:
        # 既にブラウザが初期化されている場合は何もしない
        logger.info("ブラウザは既に初期化されています")
        return True

    try:
        logger.info(f"プログラム起動時にChromeブラウザを初期化します: {target_url}")
        print(f"Chromeブラウザを起動しています: {target_url}...")

        # Chromeオプション設定
        chrome_options = Options()
        # 以下の行をコメント解除するとヘッドレスモードになります
        # chrome_options.add_argument("--headless")

        # WebDriverの初期化
        _chrome_driver = webdriver.Chrome(options=chrome_options)
        _chrome_driver.get(target_url)
        
        # input要素が存在するか確認（初期化の確認）
        try:
            wait = WebDriverWait(_chrome_driver, 10)
            input_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, input_selector))
            )
            logger.info("ブラウザの初期化に成功しました")
            print("ブラウザの初期化が完了しました。認識を開始するとフォームに動画IDが入力されます。")
            return True
        except Exception as e:
            logger.error(f"ブラウザ初期化時に入力要素が見つかりませんでした: {e}")
            print(f"ページの読み込みに問題があります: {e}")
            _chrome_driver.quit()
            _chrome_driver = None
            return False
            
    except Exception as e:
        logger.error(f"ブラウザの初期化に失敗しました: {e}")
        print(f"ブラウザの初期化に失敗しました: {e}")
        if _chrome_driver:
            try:
                _chrome_driver.quit()
            except:
                pass
            _chrome_driver = None
        return False


async def main() -> int:
    """
    メイン実行関数です。ユーザー入力に基づいて楽曲認識を繰り返し実行します。

    Returns:
        int: 終了コード。正常終了は0、エラー終了は1
    """
    # シグナルハンドラの設定
    setup_signal_handlers()

    recognizer: Optional[ShazamRealtimeRecognizer] = None

    try:
        # Seleniumブラウザの初期化（プログラム起動時）
        # 認識コールバックで使用するのと同じURL・セレクタを使用
        target_url = "https://n100-ubuntu.kazuprog.work/youtube-vj/"
        input_selector = "#input-videoId"
        browser_initialized = initialize_browser(target_url, input_selector)
        
        if not browser_initialized:
            logger.warning("ブラウザの初期化に失敗しましたが、プログラムは続行します")
            print("ブラウザの初期化に失敗しましたが、認識処理は使用可能です。")
            # ブラウザ初期化失敗でもプログラムは継続（認識時に再試行される）

        logger.info("ShazamRealtimeRecognizerを初期化しています...")
        recognizer = ShazamRealtimeRecognizer(
            recognition_callback=recognition_callback,
            stop_on_found=True,
        )
        logger.info("初期化完了。認識準備完了。")

        # メインループ
        while True:
            try:
                # このメッセージはユーザーのためのものなのでprint()を使用
                print(
                    "\n楽曲認識を開始するにはEnterキーを押してください。Ctrl+Cで終了します。"
                )
                input()

                # 開始前の確認
                logger.info("楽曲認識を開始します...")

                # 認識開始時間を記録
                global _recognition_start_time
                _recognition_start_time = time.time()
                logger.info(f"認識開始時間を記録しました: {_recognition_start_time}")
                print(f"認識開始時間を記録: {_recognition_start_time}")

                # 認識開始
                await recognizer.start_recognition()

                # 認識処理が完了するまで待機
                await wait_for_recognition_complete(recognizer)

                logger.info("楽曲認識が完了しました")

                # 認識コールバックが実行されるまで少し待機
                # この部分は認識コールバックの処理が非同期で実行される場合に必要
                await asyncio.sleep(0.5)

            except KeyboardInterrupt:
                # 録音中なら停止
                if recognizer and recognizer._is_recognizing:
                    recognizer.stop_recognition()
                    logger.info("キーボード割り込みにより認識処理をキャンセルしました")
                    print("\n認識処理をキャンセルしました。")
                    # 停止処理が完了するまで少し待つ
                    await asyncio.sleep(0.5)
                else:
                    logger.info("キーボード割り込みによりプログラムを終了します")
                    print("\nプログラムを終了します。")
                    break
            except asyncio.CancelledError:
                logger.info("非同期処理がキャンセルされました")
                print("\n非同期処理がキャンセルされました。")
                break
            except Exception as e:
                log_exception(e, "楽曲認識中に予期せぬエラーが発生しました")
                # ユーザーへのエラー表示
                print(f"\n楽曲認識中にエラーが発生しました: {type(e).__name__} - {e}")
                logger.info("プログラムを終了します")
                print("\nプログラムを終了します。")
                break

    except KeyboardInterrupt:
        logger.info("キーボード割り込みによりプログラムを終了します")
        print("\nプログラムを終了します。")
    except Exception as e:
        log_exception(e, "メイン処理中に重大なエラーが発生しました")
        print(f"\nエラーが発生しました: {type(e).__name__} - {e}")
        return EXIT_ERROR
    finally:
        # 確実にリソースを解放
        await cleanup_resources(recognizer)

    logger.info("プログラムが正常に終了しました")
    return EXIT_SUCCESS


async def wait_for_recognition_complete(recognizer: ShazamRealtimeRecognizer) -> None:
    """
    認識処理が完了するまで待機します。

    Args:
        recognizer: 楽曲認識インスタンス
    """
    retry_count = 0
    retry_limit = 3
    retry_interval = 0.1  # 秒

    while recognizer._is_recognizing:
        try:
            await asyncio.sleep(retry_interval)
        except asyncio.CancelledError:
            logger.warning("認識待機中に処理がキャンセルされました")
            break
        except Exception as e:
            log_exception(e, "認識待機中にエラーが発生しました")
            retry_count += 1
            if retry_count >= retry_limit:
                logger.error(f"{retry_limit}回のエラーが発生したため待機を中断します")
                break


async def cleanup_resources(recognizer: Optional[ShazamRealtimeRecognizer]) -> None:
    """
    プログラム終了時にリソースを解放します。

    Args:
        recognizer: 楽曲認識インスタンス
    """
    if recognizer and recognizer._is_recognizing:
        try:
            logger.info("録音認識を停止しています...")
            recognizer.stop_recognition()
            # 停止処理が完了するまで少し待つ
            await asyncio.sleep(0.5)
            logger.info("録音認識を停止しました")
        except Exception as e:
            log_exception(e, "リソース解放中にエラーが発生しました")
    
    # Seleniumリソースもクリーンアップ
    cleanup_all_resources()


def setup_signal_handlers() -> None:
    """
    シグナルハンドラを設定します。Windows/Unix両対応。
    """
    # Windowsではシグナルの種類が限られるため、対応を分ける
    try:
        # SIGTERM: プロセス終了リクエスト (Unix/Linux)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, lambda sig, frame: handle_termination())

        # SIGINT: キーボード割り込み (Ctrl+C) - 全プラットフォーム
        signal.signal(signal.SIGINT, lambda sig, frame: handle_termination())

        logger.debug("シグナルハンドラを設定しました")
    except Exception as e:
        log_exception(e, "シグナルハンドラの設定に失敗しました")


def handle_termination() -> NoReturn:
    """
    終了シグナル受信時の処理。
    """
    logger.info("終了シグナルを受信しました")
    print("\n終了シグナルを受信しました。プログラムを終了します。")
    
    # すべてのリソースをクリーンアップ
    cleanup_all_resources()
    
    sys.exit(0)


def clear_console() -> None:
    """
    コンソールをクリアします。OSに応じて適切なコマンドを実行します。

    Returns:
        None
    """
    try:
        os_name: str = os.name
        if os_name == "posix":  # macOS, Linux, Unix系
            os.system("clear")
        elif os_name == "nt":  # Windows
            os.system("cls")
        else:
            logger.warning(
                f"OS '{os_name}' ではコンソールクリアがサポートされていません"
            )
            print(
                f"お使いのオペレーティングシステム ({os_name}) では、コンソールのクリアはサポートされていません。"
            )
    except Exception as e:
        log_exception(e, "コンソールのクリア中にエラーが発生しました")
        # コンソールクリアは重要な機能ではないので、失敗しても続行


async def run_app() -> int:
    """
    アプリケーションを実行し、適切なエラーハンドリングを行います。

    Returns:
        int: 終了コード。正常終了は0、エラー終了は1
    """
    try:
        return await main()
    except Exception as e:
        log_exception(e, "アプリケーション実行中に回復不能なエラーが発生しました")
        return EXIT_ERROR


def run_with_event_loop() -> int:
    """
    イベントループを作成し、アプリケーションを実行します。

    Returns:
        int: 終了コード
    """
    exit_code = EXIT_SUCCESS
    loop = None

    try:
        logger.info("プログラムを開始します")
        # 明示的にイベントループを作成
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # アプリケーションを実行
        exit_code = loop.run_until_complete(run_app())

    except KeyboardInterrupt:
        logger.info("プログラムが中断されました")
        print("\nプログラムが中断されました。")
        exit_code = EXIT_SUCCESS  # キーボード割り込みによる終了は正常終了として扱う
    except RuntimeError as e:
        # イベントループに関するエラー処理
        if "Event loop is closed" in str(e) and isinstance(e, RuntimeError):
            logger.warning(
                "イベントループが既に閉じられています。新しいループで再試行します"
            )
            print("イベントループが既に閉じられています。新しいループで再試行します。")

            # 新しいループで再試行
            exit_code = retry_with_new_loop()
        else:
            log_exception(e, "ランタイムエラーが発生しました")
            print(f"ランタイムエラーが発生しました: {e}")
            exit_code = EXIT_ERROR
    except Exception as e:
        log_exception(e, "予期せぬエラーが発生しました")
        print(f"予期せぬエラーが発生しました: {type(e).__name__} - {e}")
        exit_code = EXIT_ERROR
    finally:
        # メインループのクリーンアップ
        if loop:
            try:
                # ループのクリーンアップ
                cleanup_event_loop(loop)
                logger.debug("イベントループをクリーンアップしました")
            except Exception as e:
                log_exception(e, "ループのクリーンアップ中にエラーが発生しました")

        logger.info(f"プログラムを終了します（終了コード: {exit_code}）")

    return exit_code


def retry_with_new_loop() -> int:
    """
    新しいイベントループでアプリケーションを再試行します。

    Returns:
        int: 終了コード
    """
    new_loop = None
    try:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        return new_loop.run_until_complete(run_app())
    except KeyboardInterrupt:
        logger.info("新しいループ実行中にプログラムが中断されました")
        print("\nプログラムが中断されました。")
        return EXIT_SUCCESS
    except Exception as e2:
        log_exception(e2, "新しいイベントループでもエラーが発生しました")
        print(f"新しいイベントループでもエラーが発生しました: {e2}")
        return EXIT_ERROR
    finally:
        # 新しいループのクリーンアップ
        if new_loop:
            cleanup_event_loop(new_loop)


def cleanup_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """
    イベントループをクリーンアップします。

    Args:
        loop: クリーンアップするイベントループ
    """
    try:
        if loop.is_running():
            loop.stop()

        # 未完了のタスクをキャンセル
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()

        # すべてのタスクが完了するのを待つ
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        # ループを閉じる
        loop.close()
    except Exception:
        # クリーンアップ中のエラーは無視
        pass


def cleanup_all_resources():
    """
    終了時にすべてのリソースを解放します。
    """
    global _chrome_driver
    
    if _chrome_driver:
        try:
            logger.info("Chromeブラウザを終了しています...")
            _chrome_driver.quit()
            logger.info("Chromeブラウザを終了しました")
        except Exception as e:
            log_exception(e, "Chromeブラウザの終了中にエラーが発生しました")
        finally:
            _chrome_driver = None


if __name__ == "__main__":
    try:
        # アプリケーションを実行し、終了コードを設定
        sys.exit(run_with_event_loop())
    finally:
        # 最終的なクリーンアップを確実に実行
        cleanup_all_resources()
