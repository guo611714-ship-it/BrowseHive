#!/bin/bash
#
# GitHub 镜像加速器 - 配置脚本
# 自动检测并配置最快的 GitHub 镜像站
#

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 镜像站列表（按推荐顺序）
MIRRORS=(
    "https://cdn.gh-proxy.org/https://github.com/"
    "https://ghproxy.net/https://github.com/"
    "https://mirror.ghproxy.com/https://github.com/"
    "https://github.com.cnpmjs.org/https://github.com/"
    "https://gitclone.com/https://github.com/"
    "https://hub.nuaa.cf/https://github.com/"
)

echo "=== GitHub 镜像加速配置工具 ==="
echo ""

# 检查是否已经配置
CURRENT_MIRROR=$(git config --global --get url."https://github.com/".insteadOf 2>/dev/null || echo "")
if [ -n "$CURRENT_MIRROR" ]; then
    echo "当前已配置镜像: $CURRENT_MIRROR"
    read -p "是否要重新配置? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "取消操作。"
        exit 0
    fi
fi

# 如果指定了特定镜像
if [ "$1" = "--mirror" ] || [ "$1" = "-m" ]; then
    MIRROR_NAME="$2"
    # 查找对应的镜像地址
    SELECTED_MIRROR=""
    for m in "${MIRRORS[@]}"; do
        if [[ "$m" == *"$MIRROR_NAME"* ]]; then
            SELECTED_MIRROR="$m"
            break
        fi
    done
    if [ -z "$SELECTED_MIRROR" ]; then
        echo "错误: 找不到镜像 $MIRROR_NAME"
        echo "可用镜像: ${MIRRORS[*]}"
        exit 1
    fi
else
    # 自动测试模式
    echo "正在测试可用镜像站速度..."
    echo ""
    BEST_MIRROR=""
    BEST_TIME=999999
    RESULTS="/tmp/mirror-test-$$.txt"

    for mirror in "${MIRRORS[@]}"; do
        echo -n "测试 $mirror ... "
        # 使用 curl 测试连接时间，最多 5 秒
        TIME=$(curl -sk -o /dev/null -w "%{time_total}" --connect-timeout 3 "${mirror}/" 2>/dev/null || echo "timeout")
        if [[ "$TIME" == "timeout" ]] || (( $(echo "$TIME > 5" | bc -l 2>/dev/null || echo "1") )); then
            echo -e "${RED}超时${NC}"
        else
            echo -e "${GREEN}${TIME}s${NC}"
            echo "$mirror $TIME" >> "$RESULTS"
            if (( $(echo "$TIME < $BEST_TIME" | bc -l 2>/dev/null || echo "0") )); then
                BEST_TIME=$TIME
                BEST_MIRROR="$mirror"
            fi
        fi
    done
    echo ""

    if [ -z "$BEST_MIRROR" ]; then
        echo -e "${RED}错误: 所有镜像站都无法访问${NC}"
        echo "请检查网络连接或稍后重试。"
        rm -f "$RESULTS"
        exit 1
    fi

    echo "最快镜像: $BEST_MIRROR (${BEST_TIME}s)"
    echo ""
    SELECTED_MIRROR="$BEST_MIRROR"
    rm -f "$RESULTS"
fi

# 确认操作
echo "即将配置 Git 镜像加速:"
echo "  原地址: https://github.com/"
echo "  镜像地址: $SELECTED_MIRROR"
echo ""
read -p "确认配置? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "操作已取消"
    exit 1
fi

# 执行配置
echo "[1/1] 配置 Git 全局设置..."
git config --global url."$SELECTED_MIRROR".insteadOf "https://github.com/"

# 验证
echo ""
echo "=== 配置完成 ==="
CONFIRM=$(git config --global --get url."https://github.com/".insteadOf)
if [ "$CONFIRM" = "$SELECTED_MIRROR" ]; then
    echo -e "${GREEN}✓ 配置成功${NC}"
    echo "当前配置: $CONFIRM"
else
    echo -e "${RED}✗ 配置失败${NC}"
    exit 1
fi

echo ""
echo "=== 使用说明 ==="
echo "现在运行任何 git clone https://github.com/xxx 命令时，"
echo "Git 会自动使用镜像加速。"
echo ""
echo "=== 测试命令 ==="
echo "git clone --depth 1 https://github.com/NousResearch/hermes-agent.git"
echo ""
echo "=== 取消加速 ==="
echo "git config --global --unset url.\"https://github.com/\".insteadOf"