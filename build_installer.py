# -*- coding: utf-8 -*-
"""
WavTube mp3+ ビルド & インストーラー作成スクリプト
(旧「WavTube更新ツール」の 初回セットアップ/再ビルド を、このスクリプトが引き継ぎます)

処理の流れ
  1. 必要ファイルの確認 (ffmpeg.exe / ffprobe.exe / アイコン など)
  2. ライブラリのインストール・最新化  (yt-dlp[default] = yt-dlp + yt-dlp-ejs ほか)
  3. deno.exe の取得  (YouTube 用 JavaScript ランタイム。無ければ自動ダウンロード)
  4. PyInstaller で WavTube 本体をビルド  (dist\\WavTube\\)
  5. Inno Setup でインストーラー作成      (installer_output\\WavTube_Setup_<版>.exe)

使い方:  build_installer.bat をダブルクリック (Python 3.12 / Inno Setup が無ければ winget で自動導入)
オプション:  --skip-pip   ライブラリ更新を省略 (再ビルドだけ速くしたいとき)
"""
import glob
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

REQUIRED_FILES = [
    "youtube_to_wav_gui.py", "audio_analyzer.py", "updater.py", "app_version.py",
    "icon.png", "WavTube.ico", "ffmpeg.exe", "ffprobe.exe", "installer.iss",
]
# 元の更新ツールとの違い: yt-dlp -> yt-dlp[default]  (YouTube に必須の yt-dlp-ejs も入る)
LIBRARIES = ["yt-dlp[default]", "librosa", "scipy", "soundfile", "numpy", "pyinstaller"]
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"


def step(n, total, text):
    print(f"\n==== [{n}/{total}] {text} ====", flush=True)


def fail(msg):
    print(f"\n[ERROR] {msg}", flush=True)
    sys.exit(1)


def run(cmd):
    print("> " + " ".join(cmd), flush=True)
    if subprocess.run(cmd).returncode != 0:
        fail("コマンドが失敗しました。上のログを確認してください。")


def check_files():
    missing = [f for f in REQUIRED_FILES if not os.path.isfile(f)]
    if missing:
        fail("次のファイルがこのフォルダにありません:\n  " + "\n  ".join(missing) +
             "\n(ffmpeg.exe / ffprobe.exe / icon.png / WavTube.ico は元の WavTube フォルダのものを使います)")
    print("必要ファイル: OK")


def install_libraries():
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir"] + LIBRARIES)


def ensure_deno():
    if os.path.isfile("deno.exe"):
        print("deno.exe: 既存のものを使用します (最新版にしたい場合は deno.exe を削除して再実行)")
        return
    print("deno.exe をダウンロードします...")
    tmp = "deno_download.zip"
    try:
        urllib.request.urlretrieve(DENO_URL, tmp)
        with zipfile.ZipFile(tmp) as z:
            z.extract("deno.exe", HERE)
    except Exception as e:
        print(f"[WARN] deno.exe を取得できませんでした: {e}")
        print("       手動で https://github.com/denoland/deno/releases から deno-x86_64-pc-windows-msvc.zip を取得し、")
        print("       deno.exe をこのフォルダに置いて再実行してください。(無くてもビルドは続行しますが、YouTube の一部形式が取れない可能性があります)")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def build_exe():
    for d in ("build", "dist"):
        shutil.rmtree(d, ignore_errors=True)
    run([
        sys.executable, "-m", "PyInstaller",
        "--clean", "--noconfirm", "--noconsole", "--onedir",
        "--name", "WavTube",
        "--add-data", "icon.png;.",
        "--icon=WavTube.ico",
        "--collect-all", "yt_dlp_ejs",
        "youtube_to_wav_gui.py",
        "audio_analyzer.py",
    ])
    if not os.path.isfile(os.path.join("dist", "WavTube", "WavTube.exe")):
        fail("dist\\WavTube\\WavTube.exe が生成されていません。")


def find_iscc():
    cands = [shutil.which("ISCC")]
    for env in ("LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if not base:
            continue
        cands.append(os.path.join(base, "Inno Setup 6", "ISCC.exe"))
        cands.append(os.path.join(base, "Programs", "Inno Setup 6", "ISCC.exe"))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def ensure_inno():
    iscc = find_iscc()
    if iscc:
        return iscc
    print("Inno Setup が見つからないため winget でインストールします...")
    subprocess.run(["winget", "install", "--id", "JRSoftware.InnoSetup", "-e", "--silent",
                    "--accept-source-agreements", "--accept-package-agreements"])
    iscc = find_iscc()
    if not iscc:
        fail("Inno Setup を準備できませんでした。https://jrsoftware.org/isdl.php から Inno Setup 6 を\n"
             "インストールしてから、もう一度 build_installer.bat を実行してください。")
    return iscc


def build_installer(version):
    iscc = ensure_inno()
    for old in glob.glob(os.path.join("installer_output", "WavTube_Setup_*.exe")):
        os.remove(old)
    run([iscc, f"/DMyAppVersion={version}", "installer.iss"])


def main():
    from app_version import APP_VERSION
    skip_pip = "--skip-pip" in sys.argv
    total = 5
    print(f"WavTube mp3+ v{APP_VERSION} ビルドを開始します (数分〜十数分かかります)")
    step(1, total, "必要ファイルの確認"); check_files()
    step(2, total, "ライブラリのインストール/最新化")
    if skip_pip:
        print("--skip-pip 指定のため省略します")
    else:
        install_libraries()
    step(3, total, "deno.exe (YouTube用JSランタイム) の準備"); ensure_deno()
    step(4, total, "PyInstaller で WavTube 本体をビルド"); build_exe()
    step(5, total, "インストーラーの作成"); build_installer(APP_VERSION)

    out = os.path.join(HERE, "installer_output", f"WavTube_Setup_{APP_VERSION}.exe")
    if not os.path.isfile(out):
        fail("インストーラーが生成されていません。上のログを確認してください。")
    print("\n====================================================")
    print("完了! インストーラーを作成しました:")
    print("  " + out)
    print("====================================================")


if __name__ == "__main__":
    main()
