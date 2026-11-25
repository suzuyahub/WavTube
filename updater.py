# -*- coding: utf-8 -*-
"""
WavTube 内蔵アップデータ (tkinter 非依存)

役割
  - 旧「WavTube更新ツール」の "ライブラリ最新化" を、本体アプリ内で行えるようにしたもの。
  - 更新対象は YouTube 側の仕様変更で頻繁に壊れる yt-dlp と、その補助部品 yt-dlp-ejs。
  - PyPI から公式 wheel をダウンロード → SHA256 検証 → ユーザー領域(lib)へ展開。
  - 次回起動時から lib 内の新しい yt-dlp を優先して読み込む (管理者権限・Python 不要)。
  - 更新後に壊れて import できない場合は自動で同梱版へ戻す。
"""
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

APP_DIR_NAME = "WavTube_mp3_plus"          # 設定保存フォルダ名 (本体の config.txt と同じ場所)
PYPI_JSON_URL = "https://pypi.org/pypi/{name}/json"
ALLOWED_DOWNLOAD_HOSTS = ("files.pythonhosted.org",)
PACKAGES = ("yt-dlp", "yt-dlp-ejs")        # PyPI 上のパッケージ名 (常にセットで更新)
USER_AGENT = "WavTube-updater"
TIMEOUT = 30
_OWN_MODULES = ("yt_dlp", "yt_dlp_ejs")


class UpdateError(Exception):
    pass


# ---------------------------------------------------------------- パス関連
def get_data_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")
    return os.path.join(base, APP_DIR_NAME)


def get_lib_dir():
    return os.path.join(get_data_dir(), "lib")


def get_app_dir():
    """exe (または .py) があるフォルダ。ffmpeg.exe / deno.exe はここに置く。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_binary(name):
    """同梱バイナリ(ffmpeg.exe 等)を探す: アプリ直下 → PyInstaller 展開先 → カレント → PATH"""
    candidates = [get_app_dir()]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(meipass)
    candidates.append(os.path.abspath("."))
    for d in candidates:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return shutil.which(name)


def setup_runtime_path():
    """アプリ直下を PATH の先頭へ。yt-dlp が同梱の deno.exe を自動検出できるようにする。"""
    app = get_app_dir()
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if app not in parts:
        os.environ["PATH"] = app + os.pathsep + os.environ.get("PATH", "")


def find_js_runtime():
    return shutil.which("deno")


# ------------------------------------------------- 外部 lib の有効化 / 隔離
def activate_external_libs():
    """yt_dlp を import する『前』に呼ぶ。更新済みの yt-dlp があれば最優先で読み込む。"""
    lib = get_lib_dir()
    if os.path.isfile(os.path.join(lib, "yt_dlp", "__init__.py")):
        if lib not in sys.path:
            sys.path.insert(0, lib)
        return True
    return False


def quarantine_external_libs():
    """更新版が壊れていた場合: lib を退避(.broken)し、同梱版で読み直せる状態に戻す。"""
    import importlib
    lib = get_lib_dir()
    while lib in sys.path:
        sys.path.remove(lib)
    for name in list(sys.modules):
        if name in _OWN_MODULES or name.split(".")[0] in _OWN_MODULES:
            del sys.modules[name]
    importlib.invalidate_caches()
    if os.path.isdir(lib):
        broken = lib + ".broken"
        shutil.rmtree(broken, ignore_errors=True)
        try:
            os.replace(lib, broken)
        except OSError:
            shutil.rmtree(lib, ignore_errors=True)


# ------------------------------------------------------------ バージョン
def parse_version(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def _versions_file():
    return os.path.join(get_lib_dir(), "versions.json")


def read_recorded_versions():
    try:
        with open(_versions_file(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_recorded_versions(d):
    with open(_versions_file(), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def get_current_versions():
    """現在動いている yt-dlp / yt-dlp-ejs のバージョン (不明なら None)。"""
    cur = {}
    try:
        import yt_dlp.version as _v
        cur["yt-dlp"] = _v.__version__
    except Exception:
        cur["yt-dlp"] = None
    rec = read_recorded_versions() if get_lib_dir() in sys.path else {}
    ejs = rec.get("yt-dlp-ejs")
    if not ejs:
        try:
            from importlib.metadata import version as _md_version
            ejs = _md_version("yt-dlp-ejs")
        except Exception:
            ejs = None
    cur["yt-dlp-ejs"] = ejs
    return cur


# ---------------------------------------------------------------- PyPI
def _open(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def fetch_latest(name):
    """PyPI から最新版の universal wheel 情報を取得。"""
    with _open(PYPI_JSON_URL.format(name=name)) as r:
        data = json.load(r)
    version = data["info"]["version"]
    for f in data.get("urls", []):
        fn = f.get("filename", "")
        if f.get("packagetype") == "bdist_wheel" and fn.endswith("py3-none-any.whl") and not f.get("yanked"):
            return {"name": name, "version": version, "url": f["url"],
                    "sha256": f["digests"]["sha256"], "filename": fn}
    raise UpdateError(f"{name} の配布ファイル(wheel)が見つかりません。")


def check_for_updates():
    """
    戻り値: {"current": {...}, "latest": {name: info}, "outdated": [name,...]}
    outdated が空でなければ更新あり。
    """
    current = get_current_versions()
    latest = {n: fetch_latest(n) for n in PACKAGES}
    outdated = []
    for n in PACKAGES:
        cur = current.get(n)
        if cur and parse_version(latest[n]["version"]) > parse_version(cur):
            outdated.append(n)
    return {"current": current, "latest": latest, "outdated": outdated}


# ------------------------------------------------------- ダウンロード/展開
def download_verified(info, dest_dir, progress=None):
    url = info["url"]
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise UpdateError(f"許可されていないダウンロード先です: {url}")
    path = os.path.join(dest_dir, info["filename"])
    sha = hashlib.sha256()
    with _open(url) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    if sha.hexdigest().lower() != info["sha256"].lower():
        raise UpdateError(f"{info['name']} のチェックサムが一致しません。ダウンロードが破損しています。")
    return path


def _safe_extract(zip_path, dest):
    dest_real = os.path.realpath(dest)
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            target = os.path.realpath(os.path.join(dest, m.filename))
            if target != dest_real and not target.startswith(dest_real + os.sep):
                raise UpdateError("不正なパスを含むファイルが検出されました。")
        z.extractall(dest)


def _dist_info_glob(lib, name):
    norm = name.replace("-", "_")
    return glob.glob(os.path.join(lib, norm + "-*.dist-info"))


def install_updates(infos, progress=None):
    """
    infos: fetch_latest() の結果リスト。
    ダウンロード→検証→展開→入れ替え。途中で失敗したら元に戻す。
    progress(percent, message) で進捗通知。
    """
    def report(p, msg):
        if progress:
            progress(p, msg)

    lib = get_lib_dir()
    os.makedirs(lib, exist_ok=True)
    work = tempfile.mkdtemp(prefix="wavtube_upd_", dir=os.path.dirname(lib))
    backup = os.path.join(work, "backup")
    stage = os.path.join(work, "stage")
    os.makedirs(backup)
    os.makedirs(stage)
    try:
        n = len(infos)
        for i, info in enumerate(infos):
            base = 90.0 * i / n
            span = 90.0 / n
            report(base, f"{info['name']} {info['version']} をダウンロード中...")
            wheel = download_verified(
                info, work, lambda f, b=base, s=span: report(b + s * f, f"{info['name']} をダウンロード中... {f*100:.0f}%"))
            sub = os.path.join(stage, info["name"])
            os.makedirs(sub)
            _safe_extract(wheel, sub)
            if not os.path.isdir(os.path.join(sub, info["name"].replace("-", "_"))):
                raise UpdateError(f"{info['name']} の内容が想定と異なります。")

        report(92, "更新を適用中...")
        moved = []      # (配置先, 退避先 or None)
        try:
            for info in infos:
                sub = os.path.join(stage, info["name"])
                new_entries = [e for e in os.listdir(sub) if not e.endswith(".data")]
                # 旧版の dist-info も退避 (古い版数のメタデータが残らないように)
                displace = set(os.path.join(lib, e) for e in new_entries)
                displace.update(_dist_info_glob(lib, info["name"]))
                for dest in sorted(displace):
                    if os.path.exists(dest):
                        bk = os.path.join(backup, os.path.basename(dest))
                        os.replace(dest, bk)
                        moved.append((dest, bk))
                for e in new_entries:
                    dest = os.path.join(lib, e)
                    os.replace(os.path.join(sub, e), dest)
                    moved.append((dest, None))
            if not os.path.isfile(os.path.join(lib, "yt_dlp", "__init__.py")):
                raise UpdateError("更新後の yt_dlp が見つかりません。")
            rec = read_recorded_versions()
            for info in infos:
                rec[info["name"]] = info["version"]
            _write_recorded_versions(rec)
        except Exception:
            for dest, bk in reversed(moved):
                if bk is None and os.path.exists(dest):
                    shutil.rmtree(dest, ignore_errors=True) if os.path.isdir(dest) else os.remove(dest)
                elif bk is not None and os.path.exists(bk):
                    os.replace(bk, dest)
            raise
        report(100, "更新が完了しました。")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def apply_updates(check_result, progress=None):
    """check_for_updates() の結果から更新を適用 (yt-dlp と yt-dlp-ejs は常に同時に更新)。"""
    infos = [check_result["latest"][n] for n in PACKAGES]
    install_updates(infos, progress)
