"""离线 tiktoken 编码器。"""

import os
from hashlib import sha1
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir
from threading import Lock

import tiktoken

_ENCODING_RESOURCE_DIR = Path(__file__).parents[1] / "resources" / "tiktoken"
_ENCODING_URLS = {
    "cl100k_base": "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
    "o200k_base": "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken",
}
_VALIDATED_CACHE_PATHS: set[Path] = set()
_CACHE_LOCK = Lock()


def _cache_dir() -> Path:
    configured_dir = os.getenv("TIKTOKEN_CACHE_DIR") or os.getenv("DATA_GYM_CACHE_DIR")
    return Path(configured_dir) if configured_dir else Path(gettempdir()) / "data-gym-cache"


def _cache_path(encoding_name: str) -> Path:
    source_url = _ENCODING_URLS.get(encoding_name)
    if source_url is None:
        raise ValueError(f"不支持的 tiktoken 编码: {encoding_name}")
    return _cache_dir() / sha1(source_url.encode()).hexdigest()


def seed_bundled_encodings() -> None:
    """每个缓存路径只校验一次，缺失或损坏时从内置词表原子修复。"""
    with _CACHE_LOCK:
        for encoding_name in _ENCODING_URLS:
            cache_path = _cache_path(encoding_name).resolve()
            if cache_path in _VALIDATED_CACHE_PATHS:
                continue
            resource_path = _ENCODING_RESOURCE_DIR / f"{encoding_name}.tiktoken"
            bundled = resource_path.read_bytes()
            try:
                valid = cache_path.read_bytes() == bundled
            except OSError:
                valid = False
            if not valid:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                # 独立临时文件避免并发进程互相覆盖，关闭后再替换以兼容 Windows。
                temporary = NamedTemporaryFile(dir=cache_path.parent, delete=False)
                temporary_path = Path(temporary.name)
                try:
                    with temporary:
                        temporary.write(bundled)
                    os.replace(temporary_path, cache_path)
                finally:
                    temporary_path.unlink(missing_ok=True)
            _VALIDATED_CACHE_PATHS.add(cache_path)


def get_encoding(encoding_name: str = "o200k_base") -> tiktoken.Encoding:
    """将内置词表预置到 tiktoken 缓存后加载编码器。"""
    if encoding_name not in _ENCODING_URLS:
        raise ValueError(f"不支持的 tiktoken 编码: {encoding_name}")
    seed_bundled_encodings()
    return tiktoken.get_encoding(encoding_name)


def count_tokens(text: str, encoding_name: str = "o200k_base") -> int:
    """统计文本的 token 数量。"""
    if not text:
        return 0
    return len(get_encoding(encoding_name).encode(text))
