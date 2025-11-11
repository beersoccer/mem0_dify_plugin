# 📦 GitHub 上传和 Dify 安装指南

## 🎯 重要结论

### ✅ 从 GitHub 安装 Dify 插件**不需要**打包 `.difypkg` 文件！

Dify 可以直接从 GitHub 仓库读取源代码并安装插件。这意味着：
- ✅ 不需要运行 `build_package.sh`
- ✅ 不需要上传 `.difypkg` 文件
- ✅ 直接推送源代码到 GitHub 即可
- ✅ Dify 会自动处理打包和安装

---

## 🚀 步骤 1：初始化 Git 仓库

```bash
cd /Users/howsun/Warp/dify/mem0-plugin-update

# 初始化 Git 仓库
git init

# 添加所有文件
git add .

# 创建初始提交
git commit -m "feat: Mem0 Dify Plugin v0.0.3 - Full v2 API support with 8 tools"
```

---

## 🚀 步骤 2：创建 GitHub 仓库

### 方法 A：使用 GitHub CLI（推荐）

```bash
# 如果已安装 gh CLI
gh repo create dify-plugin-mem0 --public --source=. --remote=origin --push

# 或者创建私有仓库
gh repo create dify-plugin-mem0 --private --source=. --remote=origin --push
```

### 方法 B：通过 GitHub 网站

1. **访问 GitHub**: https://github.com/new
2. **创建仓库**:
   - Repository name: `dify-plugin-mem0`
   - Description: `Mem0 AI integration for Dify - 8 tools with full v2 API support`
   - Public/Private: 选择 Public（推荐）
   - ❌ **不要**勾选 "Add a README file"（我们已经有了）
   - ❌ **不要**选择 .gitignore 或 license（我们已经有了）
3. **点击 "Create repository"**

4. **推送到 GitHub**:
```bash
# 添加远程仓库（替换 yourusername 为你的 GitHub 用户名）
git remote add origin https://github.com/yourusername/dify-plugin-mem0.git

# 推送代码
git branch -M main
git push -u origin main
```

---

## 🚀 步骤 3：在 Dify 中安装

### 从 GitHub 安装（推荐）

1. **登录 Dify**
   - 访问你的 Dify 实例
   - 进入 `Settings` → `Plugins`

2. **安装插件**
   - 点击 `Install from GitHub` 或类似按钮
   - 输入你的 GitHub 仓库 URL:
     ```
     https://github.com/yourusername/dify-plugin-mem0
     ```
     或者简写格式:
     ```
     yourusername/dify-plugin-mem0
     ```

3. **Dify 会自动**:
   - ✅ 从 GitHub 克隆代码
   - ✅ 读取 `manifest.yaml`
   - ✅ 安装 `requirements.txt` 中的依赖
   - ✅ 加载所有 8 个工具
   - ✅ 注册插件

4. **配置 API Key**
   - 安装完成后，在插件设置中输入 Mem0 API Key
   - 从 https://app.mem0.ai/dashboard/api-keys 获取

5. **开始使用**
   - 所有 8 个工具现在可以在 Workflow 和 Agent 中使用！

---

## 📁 需要上传到 GitHub 的文件

### ✅ 必须包含的文件

```
dify-plugin-mem0/
├── manifest.yaml           # 插件配置（必需）
├── main.py                 # 入口文件（必需）
├── requirements.txt        # Python 依赖（必需）
├── README.md              # 项目说明（推荐）
├── PRIVACY.md             # 隐私政策（推荐）
├── LICENSE                # 许可证（推荐）
├── provider/
│   ├── mem0.yaml         # Provider 配置（必需）
│   └── mem0.py           # Provider 实现（必需）
├── tools/
│   ├── add_memory.yaml
│   ├── add_memory.py
│   ├── search_memory.yaml
│   ├── search_memory.py
│   ├── get_all_memories.yaml
│   ├── get_all_memories.py
│   ├── get_memory.yaml
│   ├── get_memory.py
│   ├── update_memory.yaml
│   ├── update_memory.py
│   ├── delete_memory.yaml
│   ├── delete_memory.py
│   ├── delete_all_memories.yaml
│   ├── delete_all_memories.py
│   ├── get_memory_history.yaml
│   └── get_memory_history.py
└── _assets/
    ├── mem0.png           # 图标
    └── ...                # 其他资源
```

### ❌ 不需要上传的文件（已在 .gitignore）

```
*.difypkg                  # 打包文件
__pycache__/              # Python 缓存
.env                      # 环境变量
*.pyc                     # 编译文件
.DS_Store                 # macOS 文件
temp_package/             # 临时打包目录
mem0-api-docs/            # API 文档
*.py[cod]                 # Python 临时文件
```

---

## 📝 推荐的文件准备

### 1. 更新 README.md

```bash
# 替换旧的 README
mv README_NEW.md README.md
```

### 2. 创建 LICENSE 文件

```bash
cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2025 yevanchen
Modified and Enhanced by: beersoccer
Copyright (c) 2025 beersoccer

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
```

---

## 🔄 更新插件

当你修改代码后，只需：

```bash
# 1. 提交更改
git add .
git commit -m "feat: add new feature"

# 2. 推送到 GitHub
git push origin main

# 3. 在 Dify 中
# - 方法 A: 重新安装插件
# - 方法 B: 如果 Dify 支持，点击 "Update" 按钮
```

---

## 🎯 完整的上传命令

```bash
cd /Users/howsun/Warp/dify/mem0-plugin-update

# 1. 替换 README
mv README_NEW.md README.md

# 2. 初始化 Git（如果还没有）
git init

# 3. 添加所有文件
git add .

# 4. 创建提交
git commit -m "feat: Mem0 Dify Plugin v0.0.8

- 8 complete memory management tools
- Full Mem0 API v2 support
- Advanced filters (AND/OR logic)
- Multi-entity support (user/agent/app/run)
- Metadata system
- 4 language support (en/zh/pt/ja)
- 100% backward compatible"

# 5. 添加远程仓库（替换 yourusername）
git remote add origin https://github.com/yourusername/dify-plugin-mem0.git

# 6. 推送到 GitHub
git branch -M main
git push -u origin main
```

---

## ✅ 验证清单

推送到 GitHub 后，检查：

- [ ] README.md 在 GitHub 上正确显示
- [ ] manifest.yaml 存在
- [ ] 所有 tools/*.yaml 和 tools/*.py 文件存在
- [ ] provider/mem0.yaml 和 provider/mem0.py 存在
- [ ] _assets/ 目录包含图标
- [ ] .gitignore 正常工作（没有 .difypkg 或 __pycache__）

---

## 🐛 故障排查

### 问题 1: Dify 安装失败

**检查**:
- manifest.yaml 语法是否正确
- requirements.txt 是否包含 dify_plugin
- 所有工具文件是否存在

### 问题 2: 工具无法加载

**检查**:
- provider/mem0.yaml 中是否正确引用了所有工具
- tools/*.yaml 文件语法是否正确
- Python 文件中的类名是否正确

### 问题 3: GitHub Push 失败

**解决**:
```bash
# 检查远程仓库
git remote -v

# 重新设置远程仓库
git remote set-url origin https://github.com/yourusername/dify-plugin-mem0.git

# 强制推送（谨慎使用）
git push -f origin main
```

---

## 📚 参考资源

- **Dify 插件文档**: https://docs.dify.ai/docs/plugins
- **Mem0 文档**: https://docs.mem0.ai
- **GitHub 文档**: https://docs.github.com

---

## 🎉 完成！

现在你的插件已经：
- ✅ 上传到 GitHub
- ✅ 可以从 Dify 直接安装
- ✅ 不需要手动打包 .difypkg
- ✅ 支持自动更新

享受使用吧！ 🚀
