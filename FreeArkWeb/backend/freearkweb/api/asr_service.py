"""
api.asr_service — 语音识别服务（v1.12.0 MOD-P1208 方案B）

基于 Sherpa-ONNX + 阿里 SenseVoiceSmall，纯离线 CPU 推理。
- 模型首次使用时自动下载（~200MB，仅一次）
- 进程级单例，线程安全懒加载
- Pi 5 实测 ~2-3s/条，无需 GPU/API key

模型来源：
  https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/
    sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2

用法：
  from api.asr_service import get_recognizer
  text = get_recognizer().recognize(wav_bytes)
"""

from __future__ import annotations

import io
import logging
import os
import tarfile
import tempfile
import threading
import wave
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np

logger = logging.getLogger("api.asr_service")

# ── 模型下载配置 ──────────────────────────────────────────────────────────────
_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
)
_MODEL_DIR_NAME = "sense_voice_small"
_MODEL_FILES = ["model.onnx", "tokens.txt"]


def _default_model_dir() -> Path:
    """模型存储目录：项目根/models/sense_voice_small/，fallback ~/.freeark/models/"""
    import django.conf
    try:
        base = Path(django.conf.settings.BASE_DIR)
    except Exception:
        base = Path.home() / ".freeark"
    return base / "models" / _MODEL_DIR_NAME


# ── 模型下载 ──────────────────────────────────────────────────────────────────

def _download_model(model_dir: Path) -> None:
    """下载并解压 SenseVoiceSmall 模型到 model_dir。已存在则跳过。"""
    model_dir = Path(model_dir)
    # 检查所有必需文件是否存在
    if all((model_dir / f).exists() for f in _MODEL_FILES):
        logger.info("ASR 模型已就绪: %s", model_dir)
        return

    model_dir.mkdir(parents=True, exist_ok=True)
    logger.info("首次使用：正在下载 ASR 模型 (~200MB)…")
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=False) as tmp:
            tmp_path = tmp.name
        urlretrieve(_MODEL_URL, tmp_path)
        logger.info("模型下载完成，正在解压…")
        with tarfile.open(tmp_path, "r:bz2") as tar:
            # sherpa 模型 tar 包内通常有一层目录，将文件提取到 model_dir
            for member in tar.getmembers():
                # 跳过顶层目录名，提取文件到 model_dir
                parts = member.name.split("/", 1)
                if len(parts) < 2:
                    continue
                rel = parts[1]  # 去掉第一层目录
                if not rel:
                    continue
                dest = model_dir / rel
                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
        logger.info("ASR 模型解压完成: %s", model_dir)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── 音频解码 ──────────────────────────────────────────────────────────────────

def _decode_wav(wav_bytes: bytes) -> np.ndarray:
    """将 WAV 字节解码为 float32 归一化波形 (1D)。期望 16kHz 16-bit mono。"""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    # 16-bit signed little-endian → float32
    if sampwidth == 2:
        dtype = np.int16
    elif sampwidth == 4:
        dtype = np.int32
    else:
        raise ValueError(f"不支持的采样位宽: {sampwidth}")

    samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)

    # 多声道 → 取第一声道
    if nchannels > 1:
        samples = samples.reshape(-1, nchannels)[:, 0]

    # 归一化到 [-1, 1]
    max_val = float(np.iinfo(dtype).max)
    samples = samples / max_val

    # 重采样（简易：仅支持 16kHz，其他采样率报错）
    if framerate != 16000:
        raise ValueError(f"ASR 仅支持 16kHz 采样率，收到 {framerate}Hz")

    return samples


# ── 识别器单例 ────────────────────────────────────────────────────────────────

class VoiceRecognizer:
    """Sherpa-ONNX SenseVoiceSmall 离线识别器（进程级单例）。"""

    def __init__(self, model_dir: Path):
        import sherpa_onnx

        model_path = str(Path(model_dir) / "model.onnx")
        tokens_path = str(Path(model_dir) / "tokens.txt")

        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model_path,
            tokens=tokens_path,
            language="zh",     # 中文识别
            use_itn=True,      # 逆文本正则化（数字/日期/标点规范化）
            num_threads=4,     # Pi 5 4核，充分利用
        )
        logger.info("ASR 识别器初始化完成 (SenseVoiceSmall)")

    def recognize(self, wav_bytes: bytes) -> str:
        """识别 WAV 音频，返回文本。空结果返回空字符串。"""
        samples = _decode_wav(wav_bytes)
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16000, samples)
        self._recognizer.decode_streams()
        result = stream.result
        return (result.text or "").strip()


# ── 全局单例 ──────────────────────────────────────────────────────────────────

_recognizer: VoiceRecognizer | None = None
_lock = threading.Lock()


def get_recognizer(model_dir: str | Path | None = None) -> VoiceRecognizer | None:
    """获取 ASR 识别器单例。

    首次调用时下载模型（如未缓存）并初始化识别器（~3-10s）。后续调用直接返回。
    任何异常（网络/磁盘/OOM）均返回 None，不抛异常——调用方据此降级。

    Args:
        model_dir: 模型目录，默认自动解析（项目根/models/ 或 ~/.freeark/models/）

    Returns:
        VoiceRecognizer 或 None（初始化失败）
    """
    global _recognizer
    if _recognizer is not None:
        return _recognizer

    with _lock:
        if _recognizer is not None:
            return _recognizer
        try:
            md = Path(model_dir) if model_dir else _default_model_dir()
            _download_model(md)
            _recognizer = VoiceRecognizer(md)
            return _recognizer
        except Exception as exc:
            logger.exception("ASR 识别器初始化失败（语音输入将不可用）: %s", exc)
            return None
