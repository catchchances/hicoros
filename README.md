Hi COROS

将华为 HiTrack 运动数据转换为 FIT 文件的命令行工具。

## 安装

推荐在虚拟环境中安装：

```bash
pip install -e .
```

## 主要命令

### 1) HiTrack 转 FIT

```bash
hicoros --help
```

常见示例：

```bash
hicoros --zip-file com.huawei.health-*.zip --output-fit-directory ./output
```

### 2) 导出后 FIT 自检

```bash
hicoros-fit-check path/to/activity.fit
```

如果你希望“有告警也返回非 0”，可加：

```bash
hicoros-fit-check path/to/activity.fit --fail-on-warning
```

## 自检退出码

- `0`：无错误（有告警但未开启 `--fail-on-warning` 也返回 0）
- `1`：存在错误（例如完整性校验失败）
- `2`：仅有告警，且开启了 `--fail-on-warning`

## 依赖

- `fit-tool`：生成 FIT
- `garmin-fit-sdk`：FIT 解码与完整性校验

## 完整流程示例（华为健康 → FIT → Garmin）

下面给一个可直接照做的最小流程：

1. 在华为健康 App 中导出数据，拿到 `com.huawei.health-xxxx.zip`。
2. 进入项目目录并安装：

	```bash
	pip install -e .
	```

3. 执行转换（会把 FIT 输出到 `./output`）：

	```bash
	hicoros --zip-file ./com.huawei.health-xxxx.zip --output-fit-directory ./output
	```

4. 选择一个生成的 FIT 文件做自检：

	```bash
	hicoros-fit-check ./output/HiTrack_20260101_063000.fit
	```

5. 若你希望 CI/脚本在出现告警时也失败：

	```bash
	hicoros-fit-check ./output/HiTrack_20260101_063000.fit --fail-on-warning
	```

6. 自检通过后，将 FIT 文件导入 Garmin Connect（网页端“导入数据”）。

> 提示：如果你一次导出多条运动，可对 `./output/*.fit` 批量执行 `hicoros-fit-check`，先过滤掉异常文件再导入。