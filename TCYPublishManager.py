# -*- coding: utf-8 -*-
"""
TCY Publish Manager - pywebview Desktop Application
Replaces the HTTP-based start_editor.py with a native desktop window.
"""

import sys
import os
import json
import hashlib
import zipfile
import shutil
import threading
import ssl
import time
import logging
import urllib.request
import urllib.error
import urllib.parse

import ctypes
from ctypes import windll

from multiprocessing import freeze_support

global_window = None

# === Frozen-mode detection ===
if getattr(sys, 'frozen', False):
    current_dir = os.path.dirname(sys.executable)
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))


def get_resource_path(relative_path):
    """Get resource path for PyInstaller _MEIPASS compatibility."""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# === Simple logging setup ===
log_file_path = os.path.join(current_dir, "publish_manager.log")
logger = logging.getLogger("TCYPublishManager")
logger.setLevel(logging.DEBUG)
_fh = logging.FileHandler(log_file_path, encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(_fh)

try:
    import webview
except Exception as e:
    logger.error(f"Failed to import webview: {e}")
    sys.exit(1)


# =============================================================================
# Utility functions (identical logic from start_editor.py)
# =============================================================================

def file_sha256(filepath):
    """计算文件的 SHA256 哈希"""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def package_update_zip(manifest, copy_sources, output_path):
    """打包更新 zip（manifest.json + copy_folder 引用的本地文件夹）
    copy_sources: [{"src": "config", "local_path": "C:\\...\\config"}, ...]
    """
    src_map = {cs["src"]: cs["local_path"] for cs in copy_sources}
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

        for action in manifest.get("actions", []):
            if action.get("type") == "copy_folder":
                local_path = src_map.get(action["src"])
                if local_path and os.path.exists(local_path):
                    for root, dirs, files in os.walk(local_path):
                        for f in files:
                            full = os.path.join(root, f)
                            arc = os.path.join(action["src"],
                                               os.path.relpath(full, local_path)).replace("\\", "/")
                            zf.write(full, arc)

    file_list = zipfile.ZipFile(output_path).namelist()
    return {
        "path": output_path,
        "size": os.path.getsize(output_path),
        "files_count": len(file_list)
    }


def github_api_request(url, token, method='GET', data=None, content_type='application/json'):
    """通用 GitHub API 请求"""
    headers = {
        'Authorization': f'token {token}',
        'User-Agent': 'TCYVersionEditor/1.0',
        'Accept': 'application/vnd.github.v3+json'
    }
    if content_type:
        headers['Content-Type'] = content_type

    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode('utf-8')
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode('utf-8')

    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    ctx = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        raise Exception(f"GitHub API 错误 {e.code}: {error_body}")


def github_upload_asset(token, upload_url, filepath):
    """上传文件到 GitHub Release"""
    filename = os.path.basename(filepath)
    # upload_url 格式: https://uploads.github.com/repos/.../releases/123/assets{?name,label}
    url = upload_url.replace('{?name,label}', '') + f'?name={urllib.parse.quote(filename)}'

    with open(filepath, 'rb') as f:
        file_data = f.read()

    headers = {
        'Authorization': f'token {token}',
        'User-Agent': 'TCYVersionEditor/1.0',
        'Content-Type': 'application/octet-stream',
        'Content-Length': str(len(file_data))
    }
    req = urllib.request.Request(url, data=file_data, method='POST', headers=headers)
    ctx = ssl._create_unverified_context()

    with urllib.request.urlopen(req, context=ctx, timeout=300) as resp:
        return json.loads(resp.read().decode('utf-8'))


# =============================================================================
# Api class - pywebview JS API (converts HTTP endpoints to direct methods)
# =============================================================================

class Api:
    # -------------------------------------------------------------------------
    # Window controls
    # -------------------------------------------------------------------------
    def min_window(self):
        if global_window:
            global_window.minimize()

    def close_window(self):
        if global_window:
            global_window.destroy()

    def mark_ready(self):
        """Called by frontend when DOM is ready"""
        threading.Thread(target=self._init_app, daemon=True).start()

    def _init_app(self):
        """Background thread: scan JSON files, push initial data to frontend"""
        try:
            files = [f for f in os.listdir(current_dir)
                     if f.lower().endswith('.json') and os.path.isfile(os.path.join(current_dir, f))]
        except Exception as e:
            logger.error(f"Failed to list directory {current_dir}: {e}")
            files = []
        init_data = {"files": files}

        # Try to read latest.json and Updater-latest.json
        for fname in files:
            fpath = os.path.join(current_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                if fname.lower() == 'latest.json':
                    init_data['client_data'] = data
                    init_data['client_filename'] = fname
                elif fname.lower() == 'updater-latest.json':
                    init_data['updater_data'] = data
                    init_data['updater_filename'] = fname
            except Exception as e:
                logger.error(f"Failed to read {fname}: {e}")

        if global_window:
            try:
                js_data = json.dumps(init_data, ensure_ascii=True)
                global_window.evaluate_js(f"initApp({js_data})")
            except Exception as e:
                logger.error(f"Failed to push initApp: {e}")

    # -------------------------------------------------------------------------
    # JSON file operations (converted from HTTP endpoints)
    # -------------------------------------------------------------------------
    def list_json_files(self):
        files = [f for f in os.listdir(current_dir)
                 if f.lower().endswith('.json') and os.path.isfile(os.path.join(current_dir, f))]
        return {"files": files}

    def read_json_file(self, filename):
        if not filename or '..' in filename or '/' in filename or '\\' in filename:
            return {"error": "无效文件名"}
        filepath = os.path.join(current_dir, filename)
        if not os.path.exists(filepath):
            return {"error": f"文件不存在: {filename}"}
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            return {"filename": filename, "data": data}
        except Exception as e:
            logger.error(f"read_json_file({filename}): {e}")
            return {"error": str(e)}

    def save_json_file(self, filename, data_json):
        if not filename or '..' in filename or '/' in filename or '\\' in filename:
            return {"error": "无效文件名"}
        try:
            data = json.loads(data_json) if isinstance(data_json, str) else data_json
            filepath = os.path.join(current_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return {"ok": True, "filename": filename}
        except Exception as e:
            return {"error": str(e)}

    # -------------------------------------------------------------------------
    # Publish workflow
    # -------------------------------------------------------------------------
    def do_package_zip(self, manifest_json, copy_sources_json, output_name):
        """打包更新 ZIP: manifest + copy_folder 引用的本地文件夹"""
        try:
            manifest = json.loads(manifest_json) if isinstance(manifest_json, str) else manifest_json
            copy_sources = json.loads(copy_sources_json) if isinstance(copy_sources_json, str) else copy_sources_json
            if not output_name or '..' in output_name:
                return {"error": "无效的输出文件名"}
            output_path = os.path.join(current_dir, output_name)
            result = package_update_zip(manifest, copy_sources or [], output_path)
            return {"ok": True, **result}
        except Exception as e:
            return {"error": str(e)}

    def calc_sha256(self, filepath):
        """计算文件的 SHA256、大小和文件名"""
        try:
            if not os.path.exists(filepath):
                return {"error": f"文件不存在: {filepath}"}
            return {"ok": True, "sha256": file_sha256(filepath),
                    "size": os.path.getsize(filepath), "name": os.path.basename(filepath)}
        except Exception as e:
            return {"error": str(e)}

    def gh_create_release(self, token, owner, repo, tag, name, body):
        """Run in background thread"""
        threading.Thread(target=self._gh_create_release_thread, args=(token, owner, repo, tag, name, body), daemon=True).start()

    def _gh_create_release_thread(self, token, owner, repo, tag, name, body):
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/releases"
            result = github_api_request(url, token, 'POST', {
                "tag_name": tag, "name": name, "body": body,
                "draft": False, "prerelease": False
            })
            self._push_callback("onReleaseCreated", {
                "ok": True, "release_id": result.get("id"),
                "upload_url": result.get("upload_url"), "html_url": result.get("html_url")
            })
        except Exception as e:
            self._push_callback("onReleaseCreated", {"error": str(e)})

    def gh_upload_asset(self, token, upload_url, file_path):
        """Synchronous upload - called sequentially from JS"""
        try:
            if not os.path.exists(file_path):
                return {"error": f"文件不存在: {file_path}"}
            result = github_upload_asset(token, upload_url, file_path)
            return {"ok": True, "name": result.get("name"), "size": result.get("size"),
                    "browser_download_url": result.get("browser_download_url")}
        except Exception as e:
            return {"error": str(e)}

    def gh_update_latest(self, token, owner, repo, tag, new_entry_json):
        """Run in background thread"""
        new_entry = json.loads(new_entry_json) if isinstance(new_entry_json, str) else new_entry_json
        threading.Thread(target=self._gh_update_latest_thread, args=(token, owner, repo, tag or 'versions', new_entry), daemon=True).start()

    def _gh_update_latest_thread(self, token, owner, repo, tag, new_entry):
        try:
            # 1. 获取 release by tag
            rel_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
            try:
                release = github_api_request(rel_url, token)
            except:
                # 如果 release 不存在，创建一个
                release = github_api_request(
                    f"https://api.github.com/repos/{owner}/{repo}/releases",
                    token, 'POST',
                    {"tag_name": tag, "name": "Version Files", "body": "Auto-managed version files"}
                )

            # 2. 查找现有的 latest.json asset
            latest_data = {"latest_version": "", "history": []}
            assets = release.get("assets", [])
            existing_asset = None
            for asset in assets:
                if asset.get("name") == "latest.json":
                    existing_asset = asset
                    # 下载现有内容
                    dl_url = asset.get("browser_download_url", "")
                    if dl_url:
                        try:
                            req = urllib.request.Request(dl_url, headers={
                                'User-Agent': 'TCYPublishManager/1.0',
                                'Authorization': f'token {token}'
                            })
                            ctx = ssl._create_unverified_context()
                            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                                latest_data = json.loads(resp.read().decode('utf-8'))
                        except:
                            pass
                    break

            # 3. 追加新条目
            if 'history' not in latest_data:
                latest_data['history'] = []
            latest_data['history'].insert(0, new_entry)
            latest_data['latest_version'] = new_entry.get('version', '')

            # 4. 如果已有 latest.json asset，先删除
            if existing_asset:
                try:
                    del_url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{existing_asset['id']}"
                    github_api_request(del_url, token, 'DELETE')
                except:
                    pass

            # 5. 保存到本地并上传
            local_path = os.path.join(current_dir, "latest.json")
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(latest_data, f, indent=2, ensure_ascii=False)

            upload_url = release.get("upload_url", "")
            upload_result = github_upload_asset(token, upload_url, local_path)

            self._push_callback("onLatestJsonUpdated", {
                "ok": True, "latest_version": latest_data['latest_version'],
                "history_count": len(latest_data['history']),
                "download_url": upload_result.get("browser_download_url")
            })
        except Exception as e:
            self._push_callback("onLatestJsonUpdated", {"error": str(e)})

    # -------------------------------------------------------------------------
    # Native dialogs (NEW)
    # -------------------------------------------------------------------------
    def select_directory(self):
        if global_window:
            result = global_window.create_file_dialog(webview.FOLDER_DIALOG)
            if result and len(result) > 0:
                return result[0]
        return None

    def select_file(self, file_types_str):
        if global_window:
            result = global_window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=('JSON files (*.json)', 'All files (*.*)')
            )
            if result and len(result) > 0:
                return result[0]
        return None

    def select_any_file(self):
        """打开文件选择对话框（任意文件类型，用于选择外部文件）"""
        if global_window:
            result = global_window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=('All files (*.*)',)
            )
            if result and len(result) > 0:
                return result[0]
        return None

    # -------------------------------------------------------------------------
    # Helper to push callbacks to frontend
    # -------------------------------------------------------------------------
    def _push_callback(self, func_name, data):
        if global_window:
            try:
                global_window.evaluate_js(f"{func_name}({json.dumps(data, ensure_ascii=True)})")
            except Exception as e:
                logger.error(f"_push_callback({func_name}): {e}")


# =============================================================================
# Main entry point
# =============================================================================

def main():
    freeze_support()
    global global_window
    api = Api()
    html_file = get_resource_path("index.html")
    if not os.path.exists(html_file):
        print(f"错误: 找不到 index.html: {html_file}")
        return
    html_url = f"file:///{os.path.abspath(html_file).replace(os.sep, '/')}"
    global_window = webview.create_window(
        title='TCY Publish Manager',
        url=html_url,
        js_api=api,
        width=1050, height=720,
        resizable=False,
        frameless=True,
        easy_drag=False,
        transparent=True,
        background_color='#000000'
    )
    webview.start(debug=False)


if __name__ == '__main__':
    main()
