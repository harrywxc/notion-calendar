# Notion Calendar to GitHub Pages

自动从 Notion 同步日程到 GitHub Pages，生成稳定的日历订阅链接。

## 设置步骤

### 1. 在 GitHub 上创建仓库

1. 访问 https://github.com/new
2. 仓库名称：`notion-calendar`
3. 设为 **Public**（公开）
4. 点击 "Create repository"

### 2. 上传文件到仓库

**方法A：通过网页上传（推荐，最简单）**

1. 在新创建的仓库页面，点击 "uploading an existing file"
2. 上传以下文件（从本地选择文件上传）：
   - `.github/workflows/update-calendar.yml`
   - `generate_ics.py`
   - `calendar.ics`
3. 点击 "Commit changes" 提交

**方法B：通过 Git 命令（如果你熟悉 Git）**

```bash
git clone https://github.com/harrywxc/notion-calendar.git
cd notion-calendar
# 复制所有文件到此目录
git add .
git commit -m "Initial commit"
git push
```

### 3. 配置 GitHub Secrets

1. 在仓库页面，点击 **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**
3. 添加以下两个 secrets：

**Secret 1: NOTION_TOKEN**
- Name: `NOTION_TOKEN`
- Value: `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`

**Secret 2: NOTION_DATABASE_ID**
- Name: `NOTION_DATABASE_ID`
- Value: `1a8cd72c84a743e0aef86dfddc558070`

### 4. 启用 GitHub Actions

1. 在仓库页面，点击 **Actions** 标签
2. 如果提示 "Workflows aren't being run on this repository yet"，点击 **I understand my workflows, go ahead and enable them**

### 5. 测试手动运行

1. 在 Actions 页面，选择 "Update Notion Calendar" 工作流
2. 点击 **Run workflow** → **Run workflow**
3. 等待运行完成（约30秒）
4. 检查 calendar.ics 文件是否更新

### 6. 启用 GitHub Pages

1. 在仓库页面，点击 **Settings** → **Pages**
2. 在 "Build and deployment" 部分：
   - Source: 选择 **Deploy from a branch**
   - Branch: 选择 **main** (或 master)，目录选择 **/(root)**
3. 点击 **Save**

等待几分钟，GitHub Pages 会自动部署。

### 7. 获取订阅链接

部署成功后，订阅链接为：
```
https://harrywxc.github.io/notion-calendar/calendar.ics
```

## 使用订阅链接

### iPhone / iPad
1. 设置 → 日历 → 账户 → 添加账户 → 其他
2. 添加订阅的日历
3. 粘贴链接并保存

### OPPO ColorOS
1. 日历 → 订阅管理 → 添加订阅
2. 粘贴链接并保存

### Android 其他品牌
1. 日历 → 设置 → 添加账户 → 订阅日历
2. 粘贴链接并保存

### macOS / Windows
- 日历应用 → 订阅 → 输入链接

## 自动更新

- GitHub Actions 每 **2小时** 自动运行一次
- 从 Notion 获取最新日程
- 自动更新 calendar.ics
- 所有设备会在下次同步时看到最新数据

## 手动触发更新

如果需要立即更新：
1. 访问仓库的 Actions 页面
2. 选择 "Update Notion Calendar" 工作流
3. 点击 **Run workflow** → **Run workflow**

## 配置说明

### 修改同步时间范围

编辑 `generate_ics.py`，修改这两个参数：

```python
start_date = now - timedelta(weeks=2)  # 过去2周
end_date = now + timedelta(weeks=2)   # 未来2周
```

### 修改更新频率

编辑 `.github/workflows/update-calendar.yml`，修改 cron 表达式：

```yaml
schedule:
  - cron: '0 */2 * * *'  # 每2小时
```

常用 cron 表达式：
- `0 * * * *` - 每小时
- `0 */2 * * *` - 每2小时
- `0 */4 * * *` - 每4小时
- `0 */6 * * *` - 每6小时
- `0 0,6,12,18 * * *` - 每天4次（0点、6点、12点、18点）

## 故障排查

### Actions 运行失败
1. 检查 Secrets 是否正确配置
2. 查看 Actions 日志获取错误信息

### Pages 部署失败
1. 确认仓库是 Public
2. 等待几分钟后刷新页面
3. 检查 Pages 设置中的分支和目录

### 订阅失败
1. 确认链接正确：`https://harrywxc.github.io/notion-calendar/calendar.ics`
2. iOS 需要信任 HTTPS 证书（GitHub Pages 自动提供）
3. 检查网络连接

## 技术说明

- **数据源**：Notion API
- **ICS 生成**：使用 icalendar 库
- **自动部署**：GitHub Actions + GitHub Pages
- **更新频率**：可配置的 cron 定时任务
- **成本**：完全免费

## 许可证

MIT License
