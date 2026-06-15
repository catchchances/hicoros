**简便教程见最后**

Hi COROS

将华为 HiTrack 运动数据转换为 FIT 文件的命令行工具。

## 安装

推荐在虚拟环境中安装：

```bash
uv sync --extra test --frozen
```

## 最小 uv 工作流（本地开发/测试）

统一使用这一套命令：

```bash
# 安装运行时 + 测试依赖
uv sync --extra test --frozen

# 运行命令行工具
uv run hicoros --help
uv run hicoros-fit-check path/to/activity.fit

# 运行测试
uv run pytest -q
```

## Naive JavaScript 网页工具（纯 HTML + 原生 JS）

如果你想用更“naive”的 JS 方式，可以使用仓库中的 `web/`：

- 前端：纯静态页面（无打包、无框架）
- 后端：Node.js + Express（上传文件并调用现有 `uv run hicoros`）

### 1) 安装前端/服务依赖

```bash
cd web
npm install
```

### 2) 启动网页工具

```bash
npm start
```

启动后访问：

```text
http://localhost:8080
```

### 3) 使用方式

1. 上传 `.json` 或 `.zip`。
2. 可选填写 `jsonSportFilter`（空格或逗号分隔）。
3. 点击“开始转换并下载”。

说明：

- 该工具内部仍复用当前 Python CLI（`hicoros`）进行转换。
- 如果转换得到多个 FIT，网页会自动下载一个 ZIP 包。

## 使用 GitHub Pages 部署 `web` 前端

> 注意：GitHub Pages 只能部署静态网页，不能直接运行 Node/Python 转换服务。
> 因此推荐架构是：Pages 托管前端，转换 API 部署在你自己的服务器（VPS/Render/Railway 等）。

仓库已提供工作流：

- [`.github/workflows/deploy-web-pages.yml`](.github/workflows/deploy-web-pages.yml)

### 步骤

1. 在 GitHub 仓库开启 Pages：
	- `Settings -> Pages -> Build and deployment -> Source` 选择 `GitHub Actions`。
2. 在仓库变量中设置后端 API 地址（无尾斜杠）：
	- `Settings -> Secrets and variables -> Actions -> Variables`
	- 新建变量名：`HICOROS_API_BASE_URL`
	- 变量值示例：`https://your-api.example.com`
3. 推送 `main` 分支中 `web/**` 相关改动后，Actions 会自动发布页面。

工作流会把 `web/public` 发布到 Pages，并在发布时自动写入 `config.js`：

- `window.HICOROS_API_BASE_URL = "<你的后端地址>"`

如果你不设置该变量，前端会默认请求相对地址（`./api/convert`），适合本地联调。

## 全部使用 GitHub 的运行方式（Pages + Actions）

如果你希望环境尽量都在 GitHub 内，可以使用：

- Pages：托管前端页面
- Actions：监听 `input/` 上传文件并自动转换 FIT

仓库已提供工作流：

- [`.github/workflows/convert-on-upload.yml`](.github/workflows/convert-on-upload.yml)

目录约定：

- 上传目录：`input/`（放 `.json` 或 `.zip`）
- 转换结果目录：`web/public/results/`（生成 `.fit`）

### 操作步骤

1. 开启仓库 Pages（`Source: GitHub Actions`）。
2. 把待转换文件提交到 `input/` 目录（网页上传或本地 git push 都可以）。
3. 等待 `Convert Uploaded Activities` 工作流执行完成。
4. 结果会提交到 `web/public/results/`，并由 Pages 自动发布。

发布后可直接在 Pages 地址下载，例如：

- `https://<your-org-or-user>.github.io/<repo>/results/<fit-file-name>.fit`

说明：

- `push` 到 `input/**` 时仅转换本次变更中的 `.json/.zip` 文件。
- 手动触发（`workflow_dispatch`）时会扫描 `input/` 下所有 `.json/.zip` 文件。

## 主要命令

### 1) HiTrack 转 FIT

```bash
uv run hicoros --help
```

常见示例：

```bash
uv run hicoros --json "/path/to/your/motion path detail data.json" --output_dir output --json_sport_filter Run Hike Mountain_Hike
```

### 2) 导出后 FIT 自检

```bash
uv run hicoros-fit-check path/to/activity.fit
```

如果你希望“有告警也返回非 0”，可加：

```bash
uv run hicoros-fit-check path/to/activity.fit --fail-on-warning
```

## 自检退出码

- `0`：无错误（有告警但未开启 `--fail-on-warning` 也返回 0）
- `1`：存在错误（例如完整性校验失败）
- `2`：仅有告警，且开启了 `--fail-on-warning`

## 时间字段说明

华为手表导出的运动数据中存在三层时间，含义各不相同，转换时需要分别对应到 FIT 的不同字段：

```
3:21:09  总挂钟时间（按开始 → 按停止的真实时长）
   │
   │  差值 = 手动暂停时间
   │  用户主动按暂停键，HiTrack 以 (90, -80) 标记坐标编码，
   │  在 GPS 分段（segment）之间形成空白，代码可识别并
   │  在 FIT 中写入 timer STOP_ALL / START 事件
   ▼
2:44:00  GPS 分段时长之和（sum of segment durations）
   │
   │  差值 = 自动暂停（auto-pause）时间
   │  用户未按暂停键，但在分段内停下（等红灯、休息等），
   │  手表检测到速度低于阈值后静默停计时，GPS 轨迹仍在
   │  同一分段内推进，这段时间在 GPS 数据中完全不可见
   ▼
2:25:40  华为 totalTime（手表实际计入的主动运动时间）
```

对应到 FIT 字段：

| 含义 | 来源 | FIT 字段 |
|---|---|---|
| 总挂钟时间 | GPS 分段首尾时间戳差 | `session.total_elapsed_time` |
| GPS 分段时长之和 | 各分段 stop - start 累加（按比例缩放后写入每圈） | `lap.total_timer_time`（缩放后） |
| 主动运动时间 | 华为 JSON `totalTime` | `session.total_timer_time` |

> 自动暂停时间无法从 GPS 数据中还原，因此各 lap 的 `total_timer_time`
> 会按 `totalTime / GPS分段之和` 的比例统一缩放，使圈时之和与 session 主动运动时间保持一致。

## 依赖

- `fit-tool`：生成 FIT
- `garmin-fit-sdk`：FIT 解码与完整性校验

## 完整流程示例（JSON → FIT → Garmin）

下面给一个可直接照做的最小流程：

1. 准备华为导出的运动明细 JSON 文件（例如 `motion path detail data.json`）。
2. 进入项目目录并安装：

	```bash
	uv sync --extra test --frozen
	```

3. 执行转换（会把 FIT 输出到 `./output`）：

	```bash
	uv run hicoros --json "/path/to/your/motion path detail data.json" --output_dir output --json_sport_filter Run Hike Mountain_Hike
	```

4. 选择一个生成的 FIT 文件做自检：

	```bash
	uv run hicoros-fit-check ./output/HiTrack_20260101_063000.fit
	```

5. 若你希望 CI/脚本在出现告警时也失败：

	```bash
	uv run hicoros-fit-check ./output/HiTrack_20260101_063000.fit --fail-on-warning
	```

6. 自检通过后，将 FIT 文件导入 Garmin Connect（网页端“导入数据”）。

> 提示：如果你一次导出多条运动，可对 `./output/*.fit` 批量执行 `uv run hicoros-fit-check`，先过滤掉异常文件再导入。


**简便教程**(只考虑windows)**

基础环境准备:

安装Python:官方下载python3最新版本即可

安装uv：winget install uv

安装node:官方下载最新node

项目基本准备：

uv安装部分依赖:

uv sync --extra test --frozen

node安装依赖:

进入web文件夹后使用:npm install

食用方式：

网页使用:

得先执行命令启动网页服务器(web目录执行):npm start，然后访问: http://localhost:8080

依次上传华为导出的json文件后点击"开始转换并下载"

命令行使用（项目根目录运行）:

uv run hicoros --json "path/华为运动导出的json文件.json" --output_dir output --json_sport_filter Run Hike Mountain_Hike

