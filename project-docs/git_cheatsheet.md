# Git 常用命令速查（本项目专用）

> 远端仓库：`https://github.com/python-yyds/VeteranDev.git`
> 主分支：`main`
> 工作目录：`C:\Users\GUDGA\Desktop\简历\super-biz-agent-py`

---

## 0. 一次性配置（已完成，仅作记录）

```powershell
git config --global user.name  "python-yyds"
git config --global user.email "446412120@qq.com"

# 查看当前配置
git config --global --list
```

---

## 1. 日常开发三连（最常用）

```powershell
git status                    # 看哪些文件改了
git add .                     # 全部暂存（或 git add <file>）
git commit -m "feat: 新增 xxx"
git push                      # 推送到 GitHub
```

### 推荐 commit 前缀（Conventional Commits）

| 前缀 | 含义 |
|---|---|
| `feat` | 新功能 |
| `fix` | 修 bug |
| `docs` | 仅文档 |
| `refactor` | 重构（不改功能） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建/依赖/杂项 |
| `style` | 格式（空格、分号…）|

---

## 2. 查看状态与历史

```powershell
git status                       # 工作区状态
git status -s                    # 简短模式
git diff                         # 未暂存的改动
git diff --staged                # 已暂存的改动
git log --oneline -n 20          # 最近 20 条提交（一行一条）
git log --oneline --graph --all  # 带分支图
git show <commit_hash>           # 查看某次提交的详情和 diff
```

---

## 3. 撤销 & 回退（核心）

### 3.1 还没 commit

```powershell
# 撤销工作区某文件的改动（恢复到最近一次 commit）
git checkout -- <file>
# 或新写法
git restore <file>

# 取消 git add（把文件从暂存区拿回工作区）
git restore --staged <file>

# 一键丢弃所有未提交改动 ⚠️
git reset --hard
```

### 3.2 已 commit 但**还没 push**

```powershell
# 软回退：撤销最近 1 次 commit，改动保留在暂存区
git reset --soft HEAD~1

# 混合回退（默认）：撤销 commit，改动保留在工作区
git reset HEAD~1

# 硬回退：撤销 commit 并丢弃所有改动 ⚠️
git reset --hard HEAD~1
```

### 3.3 已 commit **并已 push**（推荐方式）

```powershell
# 用一个新提交来"反向撤销"指定提交，历史不被改写
git revert <commit_hash>
git push
```

如果**一定**要改写远端历史（独自一人开发可用，团队慎用）：

```powershell
git reset --hard <commit_hash>
git push --force-with-lease       # 比 --force 更安全
```

### 3.4 回到历史某个版本（只是查看，不动主线）

```powershell
git checkout <commit_hash>        # 进入"游离 HEAD"状态查看
git checkout main                 # 返回最新
```

---

## 4. 分支操作

```powershell
git branch                        # 查看本地分支
git branch -a                     # 包含远端
git switch -c feature/xxx         # 新建并切换分支（新写法）
git checkout -b feature/xxx       # 同上（旧写法）
git switch main                   # 切回 main

# 合并分支
git switch main
git merge feature/xxx

# 删除已合并分支
git branch -d feature/xxx
git push origin --delete feature/xxx   # 删远端

# 推送新分支并设置跟踪
git push -u origin feature/xxx
```

---

## 5. 同步远端

```powershell
git fetch                         # 只拉取，不合并
git pull                          # = fetch + merge
git pull --rebase                 # 拉取并把本地提交"叠"到远端最新之上（更线性）
```

---

## 6. 暂存改动（切分支前救命）

```powershell
git stash                         # 暂存当前改动
git stash list                    # 查看暂存列表
git stash pop                     # 恢复最近一次并删除记录
git stash apply stash@{0}         # 恢复指定且保留记录
git stash drop stash@{0}          # 删除指定
git stash clear                   # 全清
```

---

## 7. 标签（发版）

```powershell
git tag v1.0.0 -m "首个可用版本"
git push origin v1.0.0            # 推送单个 tag
git push --tags                   # 推送所有 tag
git tag -d v1.0.0                 # 删本地
git push origin :refs/tags/v1.0.0 # 删远端
```

---

## 8. 远端管理

```powershell
git remote -v                                          # 查看远端
git remote add origin <url>                            # 添加
git remote set-url origin <new_url>                    # 改地址
git remote remove origin                               # 移除
```

---

## 9. 紧急场景速查

| 我想… | 命令 |
|---|---|
| 误把 `.env` 提交了 | `git rm --cached .env` → 加入 `.gitignore` → commit |
| 改错了上一次 commit message | `git commit --amend -m "新信息"`（未 push 时） |
| 上次 commit 漏了文件 | `git add <file>` → `git commit --amend --no-edit` |
| 找回硬重置丢失的 commit | `git reflog` 找 hash → `git reset --hard <hash>` |
| 看某行代码是谁/何时改的 | `git blame <file>` |
| 比较两次提交差异 | `git diff <hash1> <hash2>` |
| 清理未跟踪文件 ⚠️ | `git clean -fd`（先用 `-n` 预演） |

---

## 10. 本项目首次推送回顾（已完成）

```powershell
git init
git branch -M main
git remote add origin https://github.com/python-yyds/VeteranDev.git
git add .
git commit -m "chore: initial commit of SuperBizAgent"
git push -u origin main
```

---

## 11. 安全红线 ⚠️

1. **永远不要提交 `.env`、API Key、密码、私钥**。本项目 `.gitignore` 已忽略 `.env`，新建任何带密钥的文件请先确认被忽略。
2. `git reset --hard` / `git clean -fd` / `git push --force` 都会**不可逆删除**改动，执行前先 `git status` 确认。
3. 若不慎把密钥推到了 GitHub：**立即去服务商后台吊销该 Key**，再用 `git filter-repo` 或 BFG 清理历史，最后 `--force` 推送。仅删除最新提交是无效的，历史里仍能查到。
