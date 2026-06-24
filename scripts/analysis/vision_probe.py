"""
vision_probe —— 最小验证：当前聊天主模型（LANGGRAPH_MODEL，默认 deepseek-v4-flash）
是否接受 OpenAI 兼容的多模态 image_url 输入，并且是否"真的看了图"。

零三方依赖：纯标准库（urllib + zlib 手搓 PNG），可直接在 Pi 上跑。

用法（Pi 上，先把生产 .env 注入环境）：
  set -a; . /path/to/FreeArkWeb/backend/.env; set +a
  python3 scripts/analysis/vision_probe.py

读取的环境变量（与 orchestrator._make_llm 完全一致）：
  DEEPSEEK_BASE_URL  默认 https://api.deepseek.com/v1
  DEEPSEEK_API_KEY   生产 .env 注入
  LANGGRAPH_MODEL    默认 deepseek-v4-flash

判读：
  [A] HTTP 200 且答复正确说出颜色(blue) → 模型吃图且真的"看"了 → 路线B可直接用主模型
  [B] HTTP 200 但答非所问/自称看不到图   → 接受字段但无视觉能力 → 需独立 VLM
  [C] HTTP 4xx（400/422/不支持 content 数组）→ 直接拒绝 image_url → 需独立 VLM 或走 OCR
本脚本不打印任何密钥，只打印 base_url、model、HTTP 状态与答复正文。
"""
import base64
import json
import os
import struct
import urllib.error
import urllib.request
import zlib


def make_solid_png(w: int, h: int, rgb: tuple) -> bytes:
    """纯标准库生成 WxH 纯色 PNG（8-bit RGB，color type 2）。"""
    def chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xffffffff))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * w           # 每行前置 filter 字节 0
    idat = zlib.compress(row * h, 9)
    return (sig + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def main() -> None:
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    model = os.environ.get("LANGGRAPH_MODEL", "deepseek-v4-flash")

    if not api_key:
        print("✗ 环境无 DEEPSEEK_API_KEY —— 请先 source 生产 .env 再跑")
        return

    # 纯蓝 64x64：纯文本模型无从"猜"出颜色，能答 blue 即证明真的看了图。
    png = make_solid_png(64, 64, (0, 0, 255))
    data_url = "data:image/png;base64," + base64.b64encode(png).decode()

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": "图中纯色方块是什么颜色？只回一个词。"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "max_tokens": 30,
        "temperature": 0,
    }

    url = base_url.rstrip("/") + "/chat/completions"
    print(f"endpoint = {url}")
    print(f"model    = {model}")
    print("发送多模态请求（text + image_url）…\n")

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status = r.status
            body = json.loads(r.read())
        print(f"HTTP {status}  ✓ 端点接受了 content 数组（未因 image_url 报错）")
        try:
            answer = body["choices"][0]["message"]["content"]
        except Exception:
            answer = json.dumps(body, ensure_ascii=False)[:500]
        print(f"模型答复: {answer!r}")
        low = (answer or "").lower()
        if "蓝" in answer or "blue" in low:
            print("\n判读 → [A] 真的看到了图（答对蓝色）。主模型具备视觉，路线B可直接用主模型。")
        else:
            print("\n判读 → [B] 接受了字段但没答对颜色 → 大概率无真实视觉能力，需独立 VLM。")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace")[:800]
        print(f"HTTP {e.code}  ✗ 端点拒绝了请求")
        print(f"错误正文: {err_body}")
        print("\n判读 → [C] 主模型/网关不接受 image_url → 需引入独立 VLM（如 doubao-vision）或走 OCR。")
    except Exception as e:
        print(f"✗ 请求异常: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
