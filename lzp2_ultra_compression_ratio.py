import struct
import time
import sys
import os
import unicodedata
from typing import BinaryIO, Tuple, Optional


# ---------------------------------------------------------------------------
# 显示宽度与终端能力
# ---------------------------------------------------------------------------
def _display_width(s: str) -> int:
    """估算字符串在终端里的显示宽度（东亚宽字符算 2 列，组合字符 0 列）。"""
    w = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1
    return w


def _supports_ansi() -> bool:
    if os.environ.get('NO_COLOR') or os.environ.get('TERM') == 'dumb':
        return False
    if os.name == 'nt':
        return bool(os.environ.get('WT_SESSION') or
                    os.environ.get('ANSICON') or
                    os.environ.get('ConEmuANSI') == 'ON')
    return True


def _terminal_width(default: int = 100) -> int:
    try:
        return os.get_terminal_size(sys.stderr.fileno()).columns
    except (OSError, ValueError, AttributeError):
        return default


# ---------------------------------------------------------------------------
# 进度报告器
# ---------------------------------------------------------------------------
class ProgressReporter:
    """原地（\\r）刷新进度，每秒最多刷 1 次；每个文件最终只留 1 行。

    关键：进度条宽度按终端宽度和"行固定部分"的实际显示宽度自适应，
    确保每帧不会触发终端折行——折行会破坏 \\r 的原地覆盖。
    """

    def __init__(self, total: int, label: str = "压缩进度",
                 max_bar_width: int = 30, min_interval: float = 1.0):
        self.total = max(total, 1)
        self.label = label
        self.min_interval = min_interval
        self.start_time = time.monotonic()
        self.last_update_time = None
        self.current = 0
        self.use_ansi = _supports_ansi()

        # —— 用最坏情况值测出"固定部分"（不含进度条）的显示宽度 ——
        worst_fixed = (
            f"{label}: [] "
            f"{100.0:6.2f}%  "
            f"({4294967295:>11,}/{4294967295:>11,} B)  "
            f"{'999.99 MB/s':>10}  "
            f"耗时 {'9999.99s':>8}  "
            f"预计剩余 {'99h59m':>6}"
        )
        fixed_w = _display_width(worst_fixed)
        term_w = _terminal_width()
        avail = term_w - fixed_w - 1          # 预留 1 列防止折行
        self.bar_width = max(5, min(max_bar_width, avail))

    # ---- 对外接口 ----
    def update(self, current: int, force: bool = False):
        self.current = current
        now = time.monotonic()
        if (not force
                and self.last_update_time is not None
                and (now - self.last_update_time) < self.min_interval):
            return
        self.last_update_time = now
        self._write_line(self._format_line(current, now))

    def finish(self, extra: Optional[str] = None):
        now = time.monotonic()
        self.current = self.total
        self._write_line(self._format_line(self.total, now, extra), newline=True)

    # ---- 内部 ----
    def _write_line(self, line: str, newline: bool = False):
        if self.use_ansi:
            payload = '\r\033[K' + line
        else:
            payload = '\r' + line
        if newline:
            payload += '\n'
        sys.stderr.write(payload)
        sys.stderr.flush()

    def _format_line(self, current: int, now: float,
                     extra: Optional[str] = None) -> str:
        percent = current * 100.0 / self.total
        filled = min(int(self.bar_width * percent / 100.0), self.bar_width)
        bar = '█' * filled + '░' * (self.bar_width - filled)

        elapsed = now - self.start_time
        speed = current / elapsed if elapsed > 0 else 0.0

        remaining = self.total - current
        if remaining <= 0:
            eta_str = '0.0s'
        elif speed > 0:
            eta_str = self._format_time(remaining / speed)
        else:
            eta_str = '--'

        line = (f"{self.label}: [{bar}] "
                f"{percent:6.2f}%  "
                f"({current:>11,}/{self.total:>11,} B)  "
                f"{self._fmt_speed(speed):>10}  "
                f"耗时 {self._fmt_elapsed(elapsed):>8}  "
                f"预计剩余 {eta_str:>6}")
        if extra:
            line += f"  {extra}"
        return line

    @staticmethod
    def _fmt_speed(bps: float) -> str:
        if bps >= 1024 * 1024:
            return f"{bps / 1024 / 1024:6.2f} MB/s"
        if bps >= 1024:
            return f"{bps / 1024:6.2f} KB/s"
        return f"{bps:6.1f} B/s"

    @staticmethod
    def _fmt_elapsed(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.2f}s"
        if seconds < 3600:
            m, s = divmod(int(seconds), 60)
            return f"{m}m{s:02d}s"
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h{m:02d}m"

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds < 0 or seconds != seconds:
            return '--'
        if seconds < 60:
            return f"{seconds:.1f}s"
        if seconds < 3600:
            m, s = divmod(int(seconds), 60)
            return f"{m}m{s:02d}s"
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h{m:02d}m"


# ---------------------------------------------------------------------------
# LZP2 压缩器
# ---------------------------------------------------------------------------
class LZP2Compressor:
    def __init__(self):
        self.window_size = 0x800
        self.max_match_length = 18
        self.min_match_length = 3

    def compress(self, data: bytes,
                 progress: Optional[ProgressReporter] = None) -> bytes:
        compressed = bytearray()
        i = 0
        data_len = len(data)

        while i < data_len:
            match_offset, match_length = self._find_longest_match(data, i)
            rle_length = self._get_rle_length(data, i)

            if rle_length >= 4 and rle_length >= match_length:
                compressed.extend(self._encode_rle(rle_length, data[i]))
                i += rle_length
            elif match_length >= self.min_match_length:
                compressed.extend(self._encode_reference(match_offset, match_length))
                i += match_length
            else:
                gap_end = self._find_gap_end(data, i)
                gap_length = min(gap_end - i, 63)
                if gap_length > 0:
                    compressed.append(gap_length)
                    compressed.extend(data[i:i + gap_length])
                    i += gap_length
                else:
                    compressed.append(1)
                    compressed.append(data[i])
                    i += 1

            if progress is not None:
                progress.update(i)

        padding_len = (16 - (len(compressed) % 16)) % 16
        if padding_len > 0:
            compressed.extend(bytes(padding_len))

        return bytes(compressed)

    # === 以下与原代码完全一致 ===
    def _find_longest_match(self, data: bytes, current_pos: int) -> Tuple[int, int]:
        max_length = 0
        best_offset = 0
        window_start = max(0, current_pos - self.window_size)
        min_len = self.min_match_length
        for check_pos in range(window_start, current_pos):
            length = 0
            max_possible = min(self.max_match_length,
                               len(data) - current_pos,
                               current_pos - check_pos)
            while (length < max_possible and
                   data[check_pos + length] == data[current_pos + length]):
                length += 1
            if length >= min_len and length > max_length:
                max_length = length
                best_offset = current_pos - check_pos
        return best_offset, max_length

    def _get_rle_length(self, data: bytes, current_pos: int) -> int:
        if current_pos >= len(data):
            return 0
        value = data[current_pos]
        length = 1
        while (current_pos + length < len(data) and
               data[current_pos + length] == value and
               length < 0x4003):
            length += 1
        return length

    def _find_gap_end(self, data: bytes, current_pos: int) -> int:
        end_pos = current_pos
        while end_pos < len(data):
            _, match_length = self._find_longest_match(data, end_pos)
            rle_length = self._get_rle_length(data, end_pos)
            if match_length >= self.min_match_length or rle_length >= 4:
                break
            if end_pos - current_pos >= 63:
                break
            end_pos += 1
        return end_pos

    def _encode_reference(self, offset: int, length: int) -> bytes:
        if offset == 0:
            return bytes([length])
        encoded_length = min(length, self.max_match_length)
        first_byte = 0x80
        length_code = encoded_length - 3
        if length_code & 0x01: first_byte |= 0x08
        if length_code & 0x02: first_byte |= 0x10
        if length_code & 0x04: first_byte |= 0x20
        if length_code & 0x08: first_byte |= 0x40
        offset_high = (offset - 1) >> 8
        first_byte |= offset_high & 0x07
        offset_low = (offset - 1) & 0xFF
        return bytes([first_byte, offset_low])

    def _encode_rle(self, length: int, value: int) -> bytes:
        store_length = min(length, 0x4003) - 4
        first_byte = 0x40 | ((store_length >> 8) & 0x3F)
        second_byte = store_length & 0xFF
        return bytes([first_byte, second_byte, value])


# ---------------------------------------------------------------------------
# 文件头 / 入口
# ---------------------------------------------------------------------------
def create_lzp2_header(original_size: int, compressed_size: int) -> bytes:
    header = bytearray()
    header.extend([0x4C, 0x5A, 0x50, 0x32, 0xAE, 0x47, 0x81, 0x3F])
    header.extend(struct.pack('<I', original_size))
    header.extend(struct.pack('<I', compressed_size))
    return bytes(header)


def _stderr_is_tty() -> bool:
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


def compress_lzp2(in_stream: BinaryIO, out_stream: BinaryIO,
                  show_progress: Optional[bool] = None):
    if show_progress is None:
        show_progress = _stderr_is_tty()

    data = in_stream.read()
    original_size = len(data)

    progress = ProgressReporter(original_size) if show_progress else None

    compressor = LZP2Compressor()
    compressed_data = compressor.compress(data, progress=progress)

    compressed_size = len(compressed_data)
    if compressed_size % 16 != 0:
        padding = 16 - (compressed_size % 16)
        compressed_data += b'\x00' * padding
        compressed_size = len(compressed_data)

    if progress is not None:
        ratio = (compressed_size / original_size * 100) if original_size else 0.0
        progress.finish(f"压缩率 {ratio:.2f}%")

    header = create_lzp2_header(original_size, compressed_size)
    out_stream.write(header)
    out_stream.write(compressed_data)


def compress_lzp2_file(in_path: str, out_path: str,
                       show_progress: Optional[bool] = None):
    with open(in_path, 'rb') as in_file:
        with open(out_path, 'wb') as out_file:
            compress_lzp2(in_file, out_file, show_progress=show_progress)


def main():
    if len(sys.argv) < 3:
        print("使用方法: python lzp2_compress.py <输入文件> <输出文件> [--quiet]")
        print("示例: python lzp2_compress.py input.txt output.lzp2")
        sys.exit(1)

    in_path = sys.argv[1]
    out_path = sys.argv[2]
    quiet = '--quiet' in sys.argv[3:] or '-q' in sys.argv[3:]

    compress_lzp2_file(in_path, out_path, show_progress=not quiet)


if __name__ == "__main__":
    main()
