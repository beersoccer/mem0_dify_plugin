#!/bin/bash

# Mem0 Dify Plugin - GitHub 准备脚本
# 此脚本帮助你准备插件并上传到 GitHub

set -e

echo "🚀 准备 Mem0 Dify Plugin 上传到 GitHub..."
echo ""

# 1. 替换 README
if [ -f "README_NEW.md" ]; then
    echo "📝 更新 README.md..."
    mv README.md README_OLD.md
    mv README_NEW.md README.md
    echo "   ✅ README.md 已更新"
else
    echo "   ℹ️  README_NEW.md 不存在，跳过"
fi

# 2. 创建 LICENSE
if [ ! -f "LICENSE" ]; then
    echo "📄 创建 LICENSE 文件..."
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
    echo "   ✅ LICENSE 已创建"
else
    echo "   ℹ️  LICENSE 已存在，跳过"
fi

# 3. 初始化 Git（如果需要）
if [ ! -d ".git" ]; then
    echo "📦 初始化 Git 仓库..."
    git init
    echo "   ✅ Git 仓库已初始化"
else
    echo "   ℹ️  Git 仓库已存在"
fi

# 4. 添加所有文件
echo "📂 添加文件到 Git..."
git add .
echo "   ✅ 文件已添加"

# 5. 创建提交
echo "💾 创建 Git 提交..."
git commit -m "feat: Mem0 Dify Plugin v0.0.8

- 8 complete memory management tools
- Full Mem0 API v2 support
- Advanced filters (AND/OR logic)
- Multi-entity support (user/agent/app/run)
- Metadata system
- 4 language support (en/zh/pt/ja)
- 100% backward compatible" || echo "   ℹ️  没有新的更改需要提交"

echo ""
echo "✅ 准备完成！"
echo ""
echo "📋 下一步操作："
echo ""
echo "1. 在 GitHub 创建新仓库："
echo "   访问: https://github.com/new"
echo "   名称: dify-plugin-mem0"
echo "   ❌ 不要添加 README、.gitignore 或 LICENSE"
echo ""
echo "2. 添加远程仓库并推送（替换 yourusername）："
echo "   git remote add origin https://github.com/yourusername/dify-plugin-mem0.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "3. 在 Dify 中安装："
echo "   Settings → Plugins → Install from GitHub"
echo "   输入: yourusername/dify-plugin-mem0"
echo ""
echo "🎉 完成！"
