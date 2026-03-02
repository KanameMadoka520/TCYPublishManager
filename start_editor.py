# -*- coding: utf-8 -*-
"""
TCY Version JSON Editor & Publish Manager - 本地服务端
双击运行即可启动，浏览器自动打开编辑器。
关闭此窗口即停止服务。
端口: 19192
"""

import http.server
import json
import os
import sys
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
import hashlib
import zipfile
import shutil
import time
import ssl

PORT = 19192
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(WORK_DIR)


def file_sha256(filepath):
    """计算文件的 SHA256 哈希"""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def compare_directories(old_dir, new_dir, subdirs):
    """比较两个版本目录的差异"""
    result = {"added": [], "deleted": [], "modified": [], "unchanged": []}

    for subdir in subdirs:
        old_path = os.path.join(old_dir, subdir)
        new_path = os.path.join(new_dir, subdir)

        old_files = {}
        new_files = {}

        if os.path.exists(old_path):
            for root, dirs, files in os.walk(old_path):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, old_dir).replace("\\", "/")
                    old_files[rel] = full

        if os.path.exists(new_path):
            for root, dirs, files in os.walk(new_path):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, new_dir).replace("\\", "/")
                    new_files[rel] = full

        for rel in new_files:
            if rel not in old_files:
                result["added"].append({
                    "path": rel,
                    "size": os.path.getsize(new_files[rel]),
                    "sha256": file_sha256(new_files[rel])
                })
            else:
                new_hash = file_sha256(new_files[rel])
                old_hash = file_sha256(old_files[rel])
                if new_hash != old_hash:
                    result["modified"].append({
                        "path": rel,
                        "old_size": os.path.getsize(old_files[rel]),
                        "new_size": os.path.getsize(new_files[rel]),
                        "sha256": new_hash
                    })
                else:
                    result["unchanged"].append({"path": rel})

        for rel in old_files:
            if rel not in new_files:
                result["deleted"].append({
                    "path": rel,
                    "size": os.path.getsize(old_files[rel])
                })

    return result


def generate_manifest(diff, url_prefix, game_root_prefix):
    """从差异报告生成 manifest.json"""
    actions = []
    external_files = []

    # 处理删除的文件
    for item in diff.get("deleted", []):
        path = item["path"]
        actions.append({
            "type": "delete",
            "path": os.path.join(game_root_prefix, path).replace("\\", "/")
        })

    # 处理新增和修改的文件
    for item in diff.get("added", []) + diff.get("modified", []):
        path = item["path"]
        name = os.path.basename(path)
        size = item.get("size", item.get("new_size", 0))
        sha256 = item.get("sha256", "")

        # 判断是配置文件还是大文件
        # 配置文件（config/kubejs等非jar）用 copy_folder，大文件用 external_files
        if path.startswith("config/") or path.startswith("kubejs/") or path.startswith("defaultconfigs/"):
            # 配置类文件放入 zip 包内 copy_folder
            # 不在这里处理，在打包时处理
            pass
        else:
            # 大文件（如 mods/*.jar）用 external_files
            full_url = url_prefix.rstrip("/") + "/" + name
            external_files.append({
                "name": name,
                "url": full_url,
                "path": os.path.join(game_root_prefix, path).replace("\\", "/"),
                "size": size,
                "sha256": sha256
            })

    # 对配置类文件，生成 copy_folder actions
    config_dirs = set()
    for item in diff.get("added", []) + diff.get("modified", []):
        path = item["path"]
        if path.startswith("config/") or path.startswith("kubejs/") or path.startswith("defaultconfigs/"):
            top_dir = path.split("/")[0]
            config_dirs.add(top_dir)

    for d in sorted(config_dirs):
        actions.append({
            "type": "copy_folder",
            "src": d,
            "dest": os.path.join(game_root_prefix, d).replace("\\", "/")
        })

    manifest = {
        "actions": actions,
        "external_files": external_files
    }
    return manifest


def package_update_zip(manifest, new_dir, output_path):
    """打包更新 zip（骨架包：manifest.json + 配置文件夹）"""
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 写入 manifest.json
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

        # 打包 copy_folder 引用的配置文件
        for action in manifest.get("actions", []):
            if action.get("type") == "copy_folder":
                src_dir = action["src"]
                full_src = os.path.join(new_dir, src_dir)
                if os.path.exists(full_src):
                    for root, dirs, files in os.walk(full_src):
                        for f in files:
                            full_path = os.path.join(root, f)
                            arc_name = os.path.relpath(full_path, new_dir).replace("\\", "/")
                            zf.write(full_path, arc_name)

    return {
        "path": output_path,
        "size": os.path.getsize(output_path),
        "files_count": len(manifest.get("actions", [])) + 1
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


class EditorHandler(http.server.SimpleHTTPRequestHandler):
    """处理静态文件 + JSON 读写 + 发布管理 API"""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/api/list':
            files = [f for f in os.listdir(WORK_DIR)
                     if f.lower().endswith('.json') and os.path.isfile(os.path.join(WORK_DIR, f))]
            self._json_response({"files": files})
            return

        if parsed.path == '/api/read':
            qs = urllib.parse.parse_qs(parsed.query)
            filename = qs.get('file', [''])[0]
            if not filename or '..' in filename or '/' in filename or '\\' in filename:
                self._json_response({"error": "无效文件名"}, 400)
                return
            filepath = os.path.join(WORK_DIR, filename)
            if not os.path.exists(filepath):
                self._json_response({"error": f"文件不存在: {filename}"}, 404)
                return
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._json_response({"filename": filename, "data": data})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/api/save':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length).decode('utf-8'))
                filename = body.get('filename', '')
                data = body.get('data')
                if not filename or '..' in filename or '/' in filename or '\\' in filename:
                    self._json_response({"error": "无效文件名"}, 400)
                    return
                if data is None:
                    self._json_response({"error": "缺少 data 字段"}, 400)
                    return
                filepath = os.path.join(WORK_DIR, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self._json_response({"ok": True, "filename": filename})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if parsed.path == '/api/compare-dirs':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length).decode('utf-8'))
                old_dir = body.get('old_dir', '')
                new_dir = body.get('new_dir', '')
                subdirs = body.get('subdirs', [])
                if not old_dir or not new_dir:
                    self._json_response({"error": "缺少 old_dir 或 new_dir"}, 400)
                    return
                if not os.path.isdir(old_dir):
                    self._json_response({"error": f"旧版本目录不存在: {old_dir}"}, 400)
                    return
                if not os.path.isdir(new_dir):
                    self._json_response({"error": f"新版本目录不存在: {new_dir}"}, 400)
                    return
                result = compare_directories(old_dir, new_dir, subdirs)
                self._json_response({
                    "ok": True,
                    "diff": result,
                    "summary": {
                        "added": len(result["added"]),
                        "deleted": len(result["deleted"]),
                        "modified": len(result["modified"]),
                        "unchanged": len(result["unchanged"])
                    }
                })
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if parsed.path == '/api/generate-manifest':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length).decode('utf-8'))
                diff = body.get('diff', {})
                url_prefix = body.get('url_prefix', '')
                game_root_prefix = body.get('game_root_prefix', '.minecraft/versions/异界战斗幻想/')
                manifest = generate_manifest(diff, url_prefix, game_root_prefix)
                self._json_response({"ok": True, "manifest": manifest})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if parsed.path == '/api/package-zip':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length).decode('utf-8'))
                manifest = body.get('manifest', {})
                new_dir = body.get('new_dir', '')
                output_name = body.get('output_name', 'update.zip')
                if '..' in output_name or '/' in output_name or '\\' in output_name:
                    self._json_response({"error": "无效的输出文件名"}, 400)
                    return
                output_path = os.path.join(WORK_DIR, output_name)
                result = package_update_zip(manifest, new_dir, output_path)
                self._json_response({"ok": True, **result})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if parsed.path == '/api/github/create-release':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length).decode('utf-8'))
                token = body['token']
                owner = body['owner']
                repo = body['repo']
                tag = body['tag']
                name = body.get('name', tag)
                release_body = body.get('body', '')

                url = f"https://api.github.com/repos/{owner}/{repo}/releases"
                result = github_api_request(url, token, 'POST', {
                    "tag_name": tag,
                    "name": name,
                    "body": release_body,
                    "draft": False,
                    "prerelease": False
                })
                self._json_response({
                    "ok": True,
                    "release_id": result.get("id"),
                    "upload_url": result.get("upload_url"),
                    "html_url": result.get("html_url")
                })
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if parsed.path == '/api/github/upload-asset':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length).decode('utf-8'))
                token = body['token']
                upload_url = body['upload_url']
                file_path = body['file_path']

                if not os.path.exists(file_path):
                    self._json_response({"error": f"文件不存在: {file_path}"}, 400)
                    return

                result = github_upload_asset(token, upload_url, file_path)
                self._json_response({
                    "ok": True,
                    "name": result.get("name"),
                    "size": result.get("size"),
                    "browser_download_url": result.get("browser_download_url")
                })
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if parsed.path == '/api/github/update-latest-json':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length).decode('utf-8'))
                token = body['token']
                owner = body['owner']
                repo = body['repo']
                tag = body.get('tag', 'versions')
                new_entry = body['new_entry']

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
                                    'User-Agent': 'TCYVersionEditor/1.0',
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
                local_path = os.path.join(WORK_DIR, "latest.json")
                with open(local_path, 'w', encoding='utf-8') as f:
                    json.dump(latest_data, f, indent=2, ensure_ascii=False)

                upload_url = release.get("upload_url", "")
                upload_result = github_upload_asset(token, upload_url, local_path)

                self._json_response({
                    "ok": True,
                    "latest_version": latest_data['latest_version'],
                    "history_count": len(latest_data['history']),
                    "download_url": upload_result.get("browser_download_url")
                })
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        self.send_error(404)

    def _json_response(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(data))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


def main():
    print("=" * 50)
    print("  TCY Version JSON Editor & Publish Manager")
    print(f"  工作目录: {WORK_DIR}")
    print(f"  端口: {PORT}")
    print("=" * 50)
    print()

    json_files = [f for f in os.listdir(WORK_DIR)
                  if f.lower().endswith('.json') and os.path.isfile(os.path.join(WORK_DIR, f))]
    if json_files:
        print(f"  检测到 {len(json_files)} 个 JSON 文件:")
        for f in json_files:
            print(f"    - {f}")
    else:
        print("  当前目录下未检测到 JSON 文件。")
        print("  你可以在浏览器中拖拽 JSON 文件到页面中加载。")
    print()

    server = http.server.HTTPServer(('127.0.0.1', PORT), EditorHandler)
    url = f'http://127.0.0.1:{PORT}'
    print(f"  编辑器已启动: {url}")
    print()
    print("  关闭此窗口即可停止服务。")
    print("=" * 50)

    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
        server.server_close()


if __name__ == '__main__':
    main()
