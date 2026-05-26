#!/usr/bin/env bash
# skeleton_guard.sh — 方舟龙虾人格骨架文件保护脚本
#
# ADR-011 方案 11-B（chattr +i）+ 11-C（Git 哈希追踪）
# REQ-FUNC-015, REQ-NFR-012
#
# 用法：
#   bash skeleton_guard.sh init     — 计算骨架文件哈希基准，写入 HASH_FILE
#   bash skeleton_guard.sh verify   — 比对当前哈希与基准，输出 PASS/FAIL，exit 0/1
#   bash skeleton_guard.sh lock     — sudo chattr +i 骨架文件（需要 sudo）
#   bash skeleton_guard.sh unlock   — sudo chattr -i 骨架文件（授权修改前使用）
#   bash skeleton_guard.sh status   — 显示骨架文件的 chattr 属性和当前哈希
#
# 注意：
#   - lock/unlock 需要 sudo（yangyang 账号生产环境有 NOPASSWD）
#   - 本脚本不自动执行到生产；由管理员手动运行
#   - verify 命令的 exit code 可接入 CI/CD 或 cron 巡检

set -euo pipefail

# ---------------------------------------------------------------------------
# 骨架文件清单（修改此处以调整保护范围）
# ---------------------------------------------------------------------------
SKELETON_FILES=(
    "$HOME/.openclaw/workspace/AGENTS.md"
    "$HOME/.openclaw/workspace/SOUL.md"
    "$HOME/.openclaw/workspace/TOOLS.md"
    "$HOME/.openclaw/workspace/USER.md"
)

HASH_FILE="$HOME/.openclaw/workspace/.skeleton_hashes"

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
_check_files_exist() {
    local missing=0
    for f in "${SKELETON_FILES[@]}"; do
        if [[ ! -f "$f" ]]; then
            echo "[WARN] 文件不存在: $f" >&2
            missing=$((missing + 1))
        fi
    done
    return $missing
}

_sha256() {
    sha256sum "$1" | awk '{print $1}'
}

# ---------------------------------------------------------------------------
# init：计算并写入哈希基准
# ---------------------------------------------------------------------------
cmd_init() {
    echo "计算骨架文件哈希基准..."
    _check_files_exist || true   # 警告但继续
    : > "$HASH_FILE"             # 清空/创建
    for f in "${SKELETON_FILES[@]}"; do
        if [[ -f "$f" ]]; then
            hash=$(_sha256 "$f")
            echo "$hash  $f" >> "$HASH_FILE"
            echo "[OK] $f => $hash"
        fi
    done
    echo "哈希基准已写入: $HASH_FILE"
}

# ---------------------------------------------------------------------------
# verify：比对当前哈希与基准（满足 AC-NFR-012-01）
# ---------------------------------------------------------------------------
cmd_verify() {
    if [[ ! -f "$HASH_FILE" ]]; then
        echo "[FAIL] 哈希基准文件不存在: $HASH_FILE（请先运行 init）" >&2
        exit 1
    fi

    fail=0
    while IFS='  ' read -r expected_hash filepath; do
        [[ -z "$filepath" ]] && continue
        if [[ ! -f "$filepath" ]]; then
            echo "[FAIL] $filepath 文件不存在"
            fail=$((fail + 1))
            continue
        fi
        current_hash=$(_sha256 "$filepath")
        if [[ "$current_hash" == "$expected_hash" ]]; then
            echo "[PASS] $(basename "$filepath") OK"
        else
            echo "[FAIL] $(basename "$filepath") CHANGED (expected: ${expected_hash:0:16}... got: ${current_hash:0:16}...)"
            fail=$((fail + 1))
        fi
    done < "$HASH_FILE"

    if [[ $fail -gt 0 ]]; then
        echo "验证结果: FAIL（$fail 个文件异常）"
        exit 1
    else
        echo "验证结果: PASS"
        exit 0
    fi
}

# ---------------------------------------------------------------------------
# lock：chattr +i（需要 sudo，防止任何进程修改，含 LLM 工具调用）
# ---------------------------------------------------------------------------
cmd_lock() {
    echo "对骨架文件设置 chattr +i..."
    for f in "${SKELETON_FILES[@]}"; do
        if [[ -f "$f" ]]; then
            sudo chattr +i "$f"
            echo "[LOCKED] $f"
        else
            echo "[SKIP] 文件不存在: $f"
        fi
    done
    echo "完成。使用 'unlock' 命令解除锁定后才能修改。"
}

# ---------------------------------------------------------------------------
# unlock：chattr -i（授权修改前使用）
# ---------------------------------------------------------------------------
cmd_unlock() {
    echo "解除骨架文件 chattr +i..."
    for f in "${SKELETON_FILES[@]}"; do
        if [[ -f "$f" ]]; then
            sudo chattr -i "$f"
            echo "[UNLOCKED] $f"
        else
            echo "[SKIP] 文件不存在: $f"
        fi
    done
    echo "完成。修改后请重新运行 'init' 更新哈希基准，再运行 'lock'。"
}

# ---------------------------------------------------------------------------
# status：显示 chattr 属性和当前哈希（快速诊断）
# ---------------------------------------------------------------------------
cmd_status() {
    echo "骨架文件状态："
    for f in "${SKELETON_FILES[@]}"; do
        if [[ -f "$f" ]]; then
            attrs=$(lsattr "$f" 2>/dev/null | awk '{print $1}' || echo "?")
            hash=$(_sha256 "$f")
            locked="NO"
            [[ "$attrs" == *i* ]] && locked="YES"
            echo "  $(basename "$f"): chattr_immutable=$locked  hash=${hash:0:16}..."
        else
            echo "  $(basename "$f"): 文件不存在"
        fi
    done
}

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
CMD="${1:-help}"
case "$CMD" in
    init)   cmd_init ;;
    verify) cmd_verify ;;
    lock)   cmd_lock ;;
    unlock) cmd_unlock ;;
    status) cmd_status ;;
    *)
        echo "用法: bash skeleton_guard.sh <init|verify|lock|unlock|status>"
        echo ""
        echo "  init    计算骨架文件哈希基准，写入 $HASH_FILE"
        echo "  verify  比对当前哈希与基准，exit 0=PASS  exit 1=FAIL"
        echo "  lock    sudo chattr +i 骨架文件"
        echo "  unlock  sudo chattr -i 骨架文件（授权修改前使用）"
        echo "  status  显示骨架文件 chattr 属性和当前哈希"
        exit 0
        ;;
esac
