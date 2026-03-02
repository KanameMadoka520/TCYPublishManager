# TCY Publish Manager (更新发布管理器)

可视化编辑 `latest.json` 和 `Updater-latest.json`，并提供一站式更新发布向导。

本工具已从浏览器端工具重构为 **pywebview 独立桌面程序**（亮色毛玻璃风格），采用与 TCY Client Updater 相同的技术栈。

## 前置假设与运作前提

本工具基于 TCY Client Updater 的「骨肉分离」更新架构构建，以下是系统默认的前提，在使用前请确保你理解：

### 1. 文件托管模型：全部在 GitHub Release

所有更新文件都托管在 GitHub Release 上：

- **更新内容仓库**（如 `KanameMadoka520/TCY-Server-Updates`）：存放每次游戏内容更新的 zip 骨架包和 mod jar 等大文件
- **latest.json** 也存在同一仓库的一个特殊 Release 中（tag 名为 `versions`），作为该 Release 的 asset 存在
- **更新器仓库**（如 `KanameMadoka520/TCY-Client-Updater`）：存放更新器 exe 本体和 `Updater-latest.json`

### 2. 版本号格式

客户端内容版本使用时间戳格式：`年.月.日.时.分`（两位年份），例如 `26.02.23.11.53`。
每次发版时，Release tag 命名为 `v` + 版本号，例如 `v26.02.23.11.53`。

### 3. 下载链接的构成规则

发布后文件的下载链接遵循 GitHub Release 的固定格式：

```
https://github.com/{Owner}/{Repo}/releases/download/{Tag}/{文件名}
```

例如你的仓库是 `KanameMadoka520/TCY-Server-Updates`，本次 tag 是 `v26.03.01.12.00`，那么：
- zip 骨架包：`https://github.com/KanameMadoka520/TCY-Server-Updates/releases/download/v26.03.01.12.00/update_26.03.01.12.00.zip`
- 某个 mod jar：`https://github.com/KanameMadoka520/TCY-Server-Updates/releases/download/v26.03.01.12.00/example-mod.jar`

国内加速链接 = 镜像前缀 + 上述链接，例如：
`https://gh-proxy.org/https://github.com/KanameMadoka520/TCY-Server-Updates/releases/download/v26.03.01.12.00/update_26.03.01.12.00.zip`

### 4. 骨肉分离的更新包结构

每次更新由两部分组成：

- **骨架 zip**（小，秒级下载）：包含 `manifest.json`（描述要执行的操作）+ 需要整体覆盖的配置文件夹（config/、kubejs/ 等）
- **外部大文件**（肉）：mod jar 等大文件，不放在 zip 里，由 `manifest.json` 的 `external_files` 字段索引，玩家端单独下载

### 5. latest.json 的管理方式

`latest.json` 存放在你的更新内容仓库的一个 **固定 tag 为 `versions` 的 Release** 中，作为该 Release 的 asset。

发布新版本时，工具会：
1. 下载这个 `versions` Release 中现有的 `latest.json`
2. 在 `history` 数组头部插入本次的新版本条目
3. 更新 `latest_version` 字段
4. 删除旧的 `latest.json` asset，上传新的

如果 `versions` Release 不存在，工具会自动创建。

---

## 使用方法

### 桌面版（推荐）

1. 将 `TCYPublishManager.py` 和 `index.html` 放在与 JSON 文件同一目录下
2. 安装依赖：`pip install pywebview`
3. 双击运行 `TCYPublishManager.py`（或 `python TCYPublishManager.py`）
4. 关闭窗口即退出

**打包为 EXE：**
1. 安装 PyInstaller：`pip install pyinstaller`
2. 运行 `python build.py`
3. 在 `dist/` 目录获取 `TCYPublishManager-1.0.0.exe`

### 浏览器版（备用）

原有的浏览器版 `start_editor.py` 仍然保留，可作为备用：
1. 双击运行 `start_editor.py`（需要 Python 3，无需额外依赖）
2. 浏览器自动打开 `http://127.0.0.1:19192`

## 功能

### Tab 1：客户端版本编辑 (latest.json)

- 查看和编辑所有历史版本条目
- 一键新增版本（自动生成时间戳版本号）
- 编辑版本号、日期、更新说明、下载链接、是否可选
- 删除历史版本条目
- `latest_version` 自动同步为最新版本号
- 版本时间线可视化（红色=必选，蓝色=可选）

### Tab 2：更新器版本编辑 (Updater-latest.json)

- 编辑版本号、下载地址、更新说明
- 设置是否强制更新

### Tab 3：发布新版本（4 步手动编排向导）

手动编排 manifest 操作 → 打包 → 发布到 GitHub 的完整流程。不再使用目录对比，而是由你手动指定每个操作，完全贴合实际更新工作流。

#### 步骤 1：版本 & GitHub 配置

| 输入框 | 含义 | 示例 |
|--------|------|------|
| 版本号 | 时间戳格式 `YY.MM.DD.HH.MM`，点击"当前时间"自动填写。同时用作 Release Tag（自动加 `v` 前缀）和 ZIP 文件名 | `26.03.02.14.30` |
| GitHub Token | Personal Access Token (`ghp_` 开头)，需 `repo` 权限 | `ghp_xxxxxxxxxxxxxxxxxxxx` |
| Owner / Repo | 存放更新文件的仓库（不是更新器仓库） | `KanameMadoka520` / `TCY-Server-Updates` |
| 更新说明 | 同时用于 Release 描述和 `latest.json` 的 `desc` 字段 | `📦 [更新] 替换 Tritium 模组` |
| 更新类型 | 必选 = 所有玩家必须安装；可选 = 玩家可跳过（如纯汉化） | 一般选必选 |

#### 步骤 2：编排操作 & 外部文件

这是核心步骤。你手动逐条添加本次更新要执行的操作和需要下载的文件。

**添加操作**（更新器支持 3 种类型）：

| 操作类型 | 用途 | 需要填写 | 使用场景 |
|---------|------|---------|---------|
| `delete_keyword` | 按关键词批量删除文件 | `folder`（目录路径）+ `keyword`（关键词） | 替换 mod 时删除旧版本（如 keyword=`tritium` 删除所有含 tritium 的 jar） |
| `delete` | 删除指定的单个文件 | `path`（完整相对路径） | 删除 servers.dat、特定配置文件等 |
| `copy_folder` | 将 ZIP 内文件夹覆盖到游戏目录 | `src`（ZIP 内文件夹名）+ `dest`（目标路径）+ 选择本地文件夹 | 更新配置文件（config/、kubejs/） |

**添加外部文件**：

点击"浏览"选择本地文件后，工具自动：
- 计算 SHA256 和文件大小
- 根据扩展名推荐游戏内路径（.jar → `mods/`，.dat → 根目录）
- 从 GitHub 配置自动生成下载 URL

外部文件不放入 ZIP，单独上传到 GitHub Release，由更新器独立下载。

#### 步骤 3：预览 & 打包

- 展示完整的 `manifest.json`（可直接编辑 JSON）
- 输出文件名默认为 `update_{版本号}.zip`
- 打包后 ZIP 包含：`manifest.json` + 所有 `copy_folder` 引用的本地文件夹

#### 步骤 4：发布到 GitHub

显示发布摘要后，点击"开始发布"，工具按顺序执行：
1. **创建 Release**（tag = `v` + 版本号）
2. **上传 ZIP** 到 Release
3. **上传外部文件**（从步骤 2 中浏览选择的本地路径）
4. **更新 latest.json**（CN 镜像 URL 自动添加 `gh-proxy.org` 前缀）

### 自动加载与拖拽

- 启动后自动扫描同目录下的 JSON 文件
- 检测到 `latest.json` 和 `Updater-latest.json` 时自动加载
- 支持将 JSON 文件直接拖拽到页面加载，自动识别类型

### 保存

- 点击「全部保存到磁盘」直接写入原文件
- 底部状态栏实时显示操作结果
- GitHub 发布完成后 latest.json 也会同步保存到本地

---

## JSON 格式参考

### latest.json

描述所有客户端内容版本的历史记录，更新器根据此文件判断玩家需要哪些更新。

```json
{
  "latest_version": "26.02.23.11.53",
  "history": [
    {
      "version": "26.02.23.11.53",
      "date": "2026/02/23 11:53",
      "desc": "✨ [线路新增] 添加阿里云杭州BGP新线路\n🔌 [服务器] 同步更新服务器列表",
      "opt_update": false,
      "download_urls": {
        "cn": "https://gh-proxy.org/https://github.com/KanameMadoka520/TCY-Server-Updates/releases/download/v26.02.23.11.53/update_26.02.23.11.53.zip",
        "global": "https://github.com/KanameMadoka520/TCY-Server-Updates/releases/download/v26.02.23.11.53/update_26.02.23.11.53.zip"
      }
    }
  ]
}
```

**字段说明：**

| 字段 | 说明 |
|------|------|
| `latest_version` | 最新版本号（自动同步为 history 第一条的 version） |
| `history[].version` | 版本号，时间戳格式 `YY.MM.DD.HH.MM` |
| `history[].date` | 发布日期，格式 `YYYY/MM/DD HH:MM` |
| `history[].desc` | 更新说明，支持 `\n` 换行 |
| `history[].opt_update` | `false` = 必选更新（玩家必须安装），`true` = 可选更新（玩家可跳过） |
| `history[].download_urls.cn` | 国内加速下载链接（镜像前缀 + 原始链接） |
| `history[].download_urls.global` | 国际下载链接（GitHub Release 原始链接） |

### Updater-latest.json

描述更新器自身的最新版本，更新器启动时检查此文件判断是否需要自我更新。

```json
{
  "version": "1.0.3",
  "url": "https://github.com/KanameMadoka520/TCY-Client-Updater/releases/download/v1.0.3/TCYClientUpdater-1.0.3.exe",
  "desc": "1. SHA256 文件完整性校验\n2. 更新回滚机制\n3. 并行下载\n4. 镜像自动测速",
  "force": true
}
```

**字段说明：**

| 字段 | 说明 |
|------|------|
| `version` | 更新器版本号，语义化版本格式（如 `1.0.3`） |
| `url` | 新版更新器 exe 的下载地址 |
| `desc` | 更新说明 |
| `force` | `true` = 强制更新（弹窗提醒且无法跳过），`false` = 可选更新 |

### manifest.json（更新包内）

位于每个更新 zip 骨架包内部，描述本次更新要执行的操作和需要下载的文件。

```json
{
  "version": "26.02.07.20.14",
  "actions": [
    {
      "type": "delete_keyword",
      "folder": ".minecraft/versions/异界战斗幻想/mods",
      "keyword": "tritium"
    },
    {
      "type": "delete",
      "path": ".minecraft/versions/异界战斗幻想/config/tritium/tritium_config.toml"
    },
    {
      "type": "copy_folder",
      "src": "config",
      "dest": ".minecraft/versions/异界战斗幻想/config"
    }
  ],
  "external_files": [
    {
      "name": "20260204tritium-forge-1.20.1-26.5.jar",
      "url": "https://github.com/KanameMadoka520/TCY-Server-Updates/releases/download/v26.02.07.20.14/20260204tritium-forge-1.20.1-26.5.jar",
      "path": ".minecraft/versions/异界战斗幻想/mods/20260204tritium-forge-1.20.1-26.5.jar",
      "size": 0
    }
  ]
}
```

**actions 类型：**

| type | 说明 | 字段 |
|------|------|------|
| `delete_keyword` | 按关键词批量删除文件（大小写不敏感） | `folder`: 目录路径, `keyword`: 文件名匹配关键词 |
| `delete` | 删除指定文件 | `path`: 要删除的文件相对路径 |
| `copy_folder` | 将 zip 内的文件夹复制到目标位置 | `src`: zip 内的源路径, `dest`: 目标路径 |

**external_files 字段：**

| 字段 | 说明 |
|------|------|
| `name` | 文件名（用于显示） |
| `url` | 下载地址 |
| `path` | 安装到玩家电脑的目标路径 |
| `size` | 文件大小（字节），用于进度显示和校验 |
| `sha256` | （可选）SHA256 哈希，用于完整性校验。没有此字段时退回 size 检查 |

---

## 完整发布流程示例

假设你要发布一个更新：替换 Tritium 模组为新版本，同时更新其配置文件。

1. **步骤 1（版本信息）**：
   - 点击"当前时间"自动填写版本号（如 `26.03.02.14.30`）
   - 填入 GitHub Token、Owner (`KanameMadoka520`)、Repo (`TCY-Server-Updates`)
   - 写更新说明、选择必选更新

2. **步骤 2（编排操作）**：
   - 添加操作 `delete_keyword`：folder = `.minecraft/versions/异界战斗幻想/mods`，keyword = `tritium`（删除旧版 mod）
   - 添加操作 `delete`：path = `.minecraft/versions/异界战斗幻想/config/tritium/tritium_config.toml`（删除旧配置）
   - 添加操作 `copy_folder`：浏览选择本地的新 config 文件夹（src = `config`，dest 自动填充）
   - 添加外部文件：浏览选择新版 `20260302tritium-forge-xxx.jar`（SHA256 自动计算，URL 自动生成）

3. **步骤 3（预览 & 打包）**：
   - 检查 manifest.json 预览，确认无误
   - 点击"打包 ZIP"生成 `update_26.03.02.14.30.zip`

4. **步骤 4（发布）**：
   - 点击"开始发布"，自动完成：创建 Release → 上传 ZIP → 上传 jar → 更新 latest.json

发布完成后，日志会显示每一步的结果和 GitHub Release URL。

---

## 纠错方式

- 每步都可以点击上一步回退修改
- 步骤 3 的 manifest 预览框可以直接手动编辑 JSON
- 发布到 GitHub 后，可在 GitHub Release 页面手动删除/替换文件
- 手动编辑标签页（Tab 1/2）始终可用，可随时修正 JSON 后保存到磁盘
- GitHub Token 和仓库配置保存在 localStorage，关闭后不丢失

## 注意事项

- 桌面版需要 Python 3 + `pywebview`
- 浏览器备用版需要 Python 3，无额外依赖，端口固定为 19192
- 建议编辑前先备份原始 JSON 文件
- GitHub Token 仅存储在本地，不会发送到除 GitHub API 以外的任何地方
