#!/bin/bash
# 统一的测试运行脚本
# 主要用于验证虚拟环境和提供便捷的测试运行方式
# 推荐方式：手动激活虚拟环境后直接使用 pytest 命令
#
# 用法:
#   ./tests/run_tests.sh [选项] [pytest参数...]
#
# 选项:
#   --check-env         仅检查虚拟环境（不运行测试）
#   --forked            使用 fork 模式运行（避免 gevent monkey patching 冲突）
#   --e2e               运行端到端测试
#   --output-file FILE  将输出保存到文件（同时输出到终端）
#   --help              显示帮助信息
#
# 示例:
#   ./tests/run_tests.sh --check-env                    # 仅检查虚拟环境
#   ./tests/run_tests.sh tests/unit/ -v                 # 运行单元测试
#   ./tests/run_tests.sh --forked tests/e2e/ -v         # 使用 fork 模式运行 e2e 测试
#   ./tests/run_tests.sh --forked -m dify_plugin -v     # 运行标记为 dify_plugin 的测试
#   ./tests/run_tests.sh --e2e test_01 --output-file log.txt  # 运行 e2e 测试并保存输出

set -e

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 切换到项目根目录
cd "$PROJECT_ROOT"

# 默认选项
CHECK_ENV_ONLY=false
USE_FORKED=false
E2E_MODE=false
OUTPUT_FILE=""
PYTEST_ARGS=()

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --check-env)
            CHECK_ENV_ONLY=true
            shift
            ;;
        --forked)
            USE_FORKED=true
            shift
            ;;
        --e2e)
            E2E_MODE=true
            shift
            ;;
        --output-file)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --help)
            cat << EOF
统一的测试运行脚本

用法:
  ./tests/run_tests.sh [选项] [pytest参数...]

选项:
  --check-env         仅检查虚拟环境（不运行测试）
  --forked            使用 fork 模式运行（避免 gevent monkey patching 冲突）
  --e2e               运行端到端测试（自动使用 fork 模式）
  --output-file FILE  将输出保存到文件（同时输出到终端）
  --help              显示帮助信息

示例:
  ./tests/run_tests.sh --check-env
  ./tests/run_tests.sh tests/unit/ -v
  ./tests/run_tests.sh --forked tests/e2e/ -v
  ./tests/run_tests.sh --forked -m dify_plugin -v
  ./tests/run_tests.sh --e2e test_01_verify_dify_connectivity --output-file log.txt

推荐方式:
  手动激活虚拟环境后直接使用 pytest 命令：
    source .venv/bin/activate
    pytest tests/unit/ -v
    pytest --forked tests/e2e/ -v
EOF
            exit 0
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# 检查虚拟环境
check_venv() {
    if [ ! -d ".venv" ]; then
        echo "❌ 错误: 虚拟环境 .venv 不存在"
        echo ""
        echo "请先创建虚拟环境:"
        echo "  uv venv"
        echo "  或"
        echo "  python -m venv .venv"
        echo ""
        return 1
    fi
    
    # 检查是否已激活
    if [[ -z "$VIRTUAL_ENV" ]]; then
        echo "⚠️  虚拟环境未激活"
        echo "   虚拟环境路径: $PROJECT_ROOT/.venv"
        echo ""
        echo "建议手动激活虚拟环境:"
        echo "  source .venv/bin/activate"
        echo ""
    else
        echo "✅ 虚拟环境已激活: $VIRTUAL_ENV"
        echo ""
    fi
    
    # 检查 pytest 是否可用
    if [ -f ".venv/bin/pytest" ]; then
        echo "✅ pytest 已安装: .venv/bin/pytest"
    else
        echo "⚠️  pytest 未找到，请安装依赖:"
        echo "  source .venv/bin/activate"
        echo "  uv sync"
        echo "  或"
        echo "  pip install -r requirements-dev.txt"
        echo ""
        return 1
    fi
    
    # 如果使用 fork 模式，检查 pytest-forked
    if [ "$USE_FORKED" = true ] || [ "$E2E_MODE" = true ]; then
        if ! .venv/bin/python -c "import pytest_forked" 2>/dev/null; then
            echo "⚠️  pytest-forked 未安装（fork 模式需要）"
            echo "   请运行: uv add --dev pytest-forked"
            echo "   或: pip install pytest-forked"
            echo ""
            return 1
        else
            echo "✅ pytest-forked 已安装"
        fi
    fi
    
    echo ""
    return 0
}

# 如果仅检查环境，执行检查后退出
if [ "$CHECK_ENV_ONLY" = true ]; then
    echo "======================================"
    echo "检查虚拟环境"
    echo "======================================"
    echo ""
    check_venv
    exit $?
fi

# 执行环境检查
if ! check_venv; then
    exit 1
fi

# E2E 模式自动启用 fork 模式
if [ "$E2E_MODE" = true ]; then
    USE_FORKED=true
    # 如果没有指定测试文件，默认使用 e2e 测试文件
    if [[ ${#PYTEST_ARGS[@]} -eq 0 ]] || [[ ! "${PYTEST_ARGS[*]}" =~ tests/e2e/ ]]; then
        # 检查是否有测试名称参数
        if [[ ${#PYTEST_ARGS[@]} -gt 0 ]] && [[ "${PYTEST_ARGS[0]}" =~ ^test_ ]]; then
            # 第一个参数是测试名称
            TEST_NAME="${PYTEST_ARGS[0]}"
            PYTEST_ARGS=("tests/e2e/test_e2e_session_memory.py::TestE2ESessionMemory::$TEST_NAME" "${PYTEST_ARGS[@]:1}")
        else
            PYTEST_ARGS=("tests/e2e/test_e2e_session_memory.py" "${PYTEST_ARGS[@]}")
        fi
    fi
fi

# 检查 tests/.env 文件（E2E 和集成测试需要）
if [ "$E2E_MODE" = true ] || [[ "${PYTEST_ARGS[*]}" =~ tests/(e2e|integration)/ ]]; then
    if [ ! -f "tests/.env" ]; then
        echo "❌ 错误: 未找到 tests/.env 文件"
        echo "   端到端测试和集成测试需要配置文件"
        echo "   请创建 tests/.env 文件并填写配置"
        echo ""
        exit 1
    fi
fi

# 激活虚拟环境（如果未激活）
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "自动激活虚拟环境..."
    source .venv/bin/activate
fi

# 构建 pytest 命令
PYTEST_CMD=("pytest")

# 添加 fork 模式参数
if [ "$USE_FORKED" = true ]; then
    PYTEST_CMD+=("--forked")
    # macOS 上需要设置环境变量以避免 fork() 在多线程环境下的崩溃
    # 这允许在 fork 子进程中使用 Objective-C 运行时
    export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
fi

# 添加用户提供的参数
PYTEST_CMD+=("${PYTEST_ARGS[@]}")

# 显示运行信息
echo "======================================"
if [ "$E2E_MODE" = true ]; then
    echo "运行端到端测试"
elif [ "$USE_FORKED" = true ]; then
    echo "使用 fork 模式运行测试"
else
    echo "运行测试"
fi
echo "======================================"
if [ -n "$OUTPUT_FILE" ]; then
    echo "输出将保存到: $OUTPUT_FILE"
fi
echo ""
echo "执行命令: ${PYTEST_CMD[*]}"
echo ""

# 运行测试
if [ -n "$OUTPUT_FILE" ]; then
    # 保存输出到文件（同时输出到终端）
    "${PYTEST_CMD[@]}" 2>&1 | tee "$OUTPUT_FILE"
    EXIT_CODE=${PIPESTATUS[0]}
else
    # 只输出到终端
    "${PYTEST_CMD[@]}"
    EXIT_CODE=$?
fi

echo ""
echo "======================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 测试完成"
else
    echo "❌ 测试失败（退出码: $EXIT_CODE）"
fi
if [ -n "$OUTPUT_FILE" ]; then
    echo "输出已保存到: $OUTPUT_FILE"
fi
echo "======================================"

exit $EXIT_CODE

