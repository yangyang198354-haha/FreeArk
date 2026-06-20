"""
test_memory_skeleton_guard_sh.py — skeleton_guard.sh 子进程测试

测试目标（GROUP_D / PHASE_07）：
  - init 命令：在临时目录中计算骨架文件哈希，写入 HASH_FILE
  - verify 命令：哈希未变时 exit 0 + 输出 PASS；文件被修改时 exit 1 + 输出 FAIL
  - verify 命令：HASH_FILE 不存在时 exit 1
  - status 命令：列出骨架文件状态，不崩溃
  - 无效命令：输出用法提示

策略：
  使用 subprocess + 临时目录（tempfile.mkdtemp）；覆盖 SKELETON_FILES 指向
  临时文件；通过 env 注入自定义 HOME 使脚本路径指向可控目录。
  脚本依赖 bash（Windows 测试环境通过 Git Bash / WSL 调用），
  若 bash 不可用则 skip 整组测试（不 fail）。

需求引用: REQ-FUNC-015, REQ-NFR-012
US: US-MEM-010
AC: AC-NFR-012-01（verify exit 0=PASS, exit 1=FAIL）
"""
import os
import platform
import subprocess
import sys
import stat
import tempfile
import shutil
import unittest
from django.test import tag
from pathlib import Path

# 找到 skeleton_guard.sh 的绝对路径
_REPO_ROOT = Path(__file__).resolve().parents[5]  # 从 api/tests/ 向上 5 层到达仓库根
_SCRIPT_PATH = _REPO_ROOT / 'scripts' / 'skeleton_guard.sh'

# skeleton_guard.sh 是 Linux 运维脚本（生产在树莓派 Debian 13 上运行），
# Windows 上 Git Bash 缺 sha256sum / 路径转换问题导致 stdout=None，整组 skip。
_IS_LINUX = platform.system() == 'Linux'


def _bash_available():
    """检测 bash 是否可用（Windows 上可能是 Git Bash）。"""
    try:
        result = subprocess.run(
            ['bash', '--version'],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _sha256sum_available():
    """检测 sha256sum 在 bash 中是否可用（Windows Git Bash 可能无此命令）。"""
    if not _bash_available():
        return False
    try:
        result = subprocess.run(
            ['bash', '-c', 'echo test | sha256sum'],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


_SCRIPT_RUNNABLE = _IS_LINUX and _bash_available() and _sha256sum_available() and _SCRIPT_PATH.exists()


def _run_script(args, env=None, cwd=None, timeout=15):
    """运行 skeleton_guard.sh <args>，返回 CompletedProcess。"""
    cmd = ['bash', str(_SCRIPT_PATH)] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=timeout,
    )


@unittest.skipUnless(_SCRIPT_RUNNABLE, 'bash/sha256sum 不可用或脚本不存在，跳过 skeleton_guard.sh 测试')
@tag('unit')
class SkeletonGuardInitTest(unittest.TestCase):
    """init 命令：写入哈希基准文件。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='sgtest_')
        # 创建模拟骨架目录和文件
        workspace = Path(self.tmpdir) / '.openclaw' / 'workspace'
        workspace.mkdir(parents=True)
        self.workspace = workspace

        # 创建骨架文件
        for name in ('AGENTS.md', 'SOUL.md', 'TOOLS.md', 'USER.md'):
            (workspace / name).write_text(f'# {name} skeleton content\n', encoding='utf-8')

        self.hash_file = workspace / '.skeleton_hashes'
        # 设置 HOME 指向临时目录，使脚本的 $HOME/.openclaw/... 路径指向可控位置
        self.env = {**os.environ, 'HOME': self.tmpdir}

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_creates_hash_file(self):
        """init 命令应在 $HOME/.openclaw/workspace/.skeleton_hashes 写入哈希基准。"""
        result = _run_script(['init'], env=self.env)
        self.assertEqual(result.returncode, 0,
                         f'init 应 exit 0，实际 returncode={result.returncode}\n'
                         f'stdout: {result.stdout}\nstderr: {result.stderr}')
        self.assertTrue(self.hash_file.exists(), 'init 后 .skeleton_hashes 应存在')

    def test_init_hash_file_contains_all_skeleton_files(self):
        """init 写入的哈希基准应包含所有 4 个骨架文件。"""
        _run_script(['init'], env=self.env)
        content = self.hash_file.read_text(encoding='utf-8')
        for name in ('AGENTS.md', 'SOUL.md', 'TOOLS.md', 'USER.md'):
            self.assertIn(name, content,
                          f'哈希基准文件应包含 {name}')

    def test_init_output_mentions_ok(self):
        """init 输出包含 [OK] 标记。"""
        result = _run_script(['init'], env=self.env)
        self.assertIn('[OK]', result.stdout)


@unittest.skipUnless(_SCRIPT_RUNNABLE, 'bash/sha256sum 不可用或脚本不存在，跳过 skeleton_guard.sh 测试')
@tag('unit')
class SkeletonGuardVerifyTest(unittest.TestCase):
    """verify 命令：哈希比对行为验证。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='sgverify_')
        workspace = Path(self.tmpdir) / '.openclaw' / 'workspace'
        workspace.mkdir(parents=True)
        self.workspace = workspace

        for name in ('AGENTS.md', 'SOUL.md', 'TOOLS.md', 'USER.md'):
            (workspace / name).write_text(f'# {name} original\n', encoding='utf-8')

        self.hash_file = workspace / '.skeleton_hashes'
        self.env = {**os.environ, 'HOME': self.tmpdir}
        # 先 init 建立基准
        _run_script(['init'], env=self.env)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_verify_pass_when_files_unchanged(self):
        """文件未修改时 verify exit 0，输出 PASS（AC-NFR-012-01）。"""
        result = _run_script(['verify'], env=self.env)
        self.assertEqual(result.returncode, 0,
                         f'文件未变时 verify 应 exit 0\nstdout: {result.stdout}\nstderr: {result.stderr}')
        self.assertIn('PASS', result.stdout)

    def test_verify_fail_when_file_modified(self):
        """骨架文件被修改时 verify exit 1，输出 FAIL（AC-NFR-012-01）。"""
        # 修改一个骨架文件
        (self.workspace / 'SOUL.md').write_text('# SOUL.md MODIFIED!\n', encoding='utf-8')
        result = _run_script(['verify'], env=self.env)
        self.assertEqual(result.returncode, 1,
                         f'文件被修改时 verify 应 exit 1\nstdout: {result.stdout}\nstderr: {result.stderr}')
        self.assertIn('FAIL', result.stdout)

    def test_verify_fail_when_hash_file_missing(self):
        """HASH_FILE 不存在时 verify exit 1。"""
        self.hash_file.unlink()
        result = _run_script(['verify'], env=self.env)
        self.assertEqual(result.returncode, 1,
                         'HASH_FILE 不存在时 verify 应 exit 1')

    def test_verify_output_per_file_pass_markers(self):
        """verify PASS 时，输出包含各文件的 [PASS] 标记。"""
        result = _run_script(['verify'], env=self.env)
        self.assertIn('[PASS]', result.stdout)

    def test_verify_fail_shows_changed_file(self):
        """verify FAIL 时，输出包含被修改文件的 FAIL 标记。"""
        (self.workspace / 'TOOLS.md').write_text('tampered\n', encoding='utf-8')
        result = _run_script(['verify'], env=self.env)
        self.assertIn('[FAIL]', result.stdout)


@unittest.skipUnless(_SCRIPT_RUNNABLE, 'bash/sha256sum 不可用或脚本不存在，跳过 skeleton_guard.sh 测试')
@tag('unit')
class SkeletonGuardStatusTest(unittest.TestCase):
    """status 命令：输出骨架文件状态，不崩溃。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='sgstatus_')
        workspace = Path(self.tmpdir) / '.openclaw' / 'workspace'
        workspace.mkdir(parents=True)
        self.workspace = workspace
        for name in ('AGENTS.md', 'SOUL.md', 'TOOLS.md', 'USER.md'):
            (workspace / name).write_text(f'# {name}\n', encoding='utf-8')
        self.env = {**os.environ, 'HOME': self.tmpdir}

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_status_exits_zero(self):
        """status 命令应 exit 0（文件存在情况下）。"""
        result = _run_script(['status'], env=self.env)
        self.assertEqual(result.returncode, 0,
                         f'status 应 exit 0\nstdout: {result.stdout}\nstderr: {result.stderr}')

    def test_status_lists_skeleton_files(self):
        """status 输出包含骨架文件名。"""
        result = _run_script(['status'], env=self.env)
        for name in ('AGENTS.md', 'SOUL.md', 'TOOLS.md', 'USER.md'):
            self.assertIn(name, result.stdout,
                          f'status 输出应包含 {name}')


@unittest.skipUnless(_SCRIPT_RUNNABLE, 'bash/sha256sum 不可用或脚本不存在，跳过 skeleton_guard.sh 测试')
@tag('unit')
class SkeletonGuardInvalidCommandTest(unittest.TestCase):
    """无效命令：输出用法提示，exit 0（脚本设计如此）。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='sginvalid_')
        self.env = {**os.environ, 'HOME': self.tmpdir}

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_invalid_command_shows_usage(self):
        """无效命令时，输出用法提示（init|verify|lock|unlock|status）。"""
        result = _run_script(['invalid_command_xyz'], env=self.env)
        # 脚本在无效命令时 exit 0（case '*' 分支）
        self.assertIn('init', result.stdout + result.stderr,
                      '无效命令应输出用法提示，包含 init')

    def test_no_args_shows_usage(self):
        """不传参数时（默认 help），输出用法。"""
        result = _run_script([], env=self.env)
        # CMD="${1:-help}" → 走 *) 分支
        self.assertIn('verify', result.stdout + result.stderr,
                      '无参数应输出用法提示，包含 verify')
