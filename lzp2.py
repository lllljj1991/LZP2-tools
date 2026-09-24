import sys
import struct
import os
import time
import argparse
from typing import BinaryIO, Dict, Tuple, List
from pathlib import Path

# -------------------------- 进度显示模块 --------------------------
_progress_enabled = True
_progress_mode = 'auto'   # auto / tty / none

_progress_start_time: float = None
_progress_last_time: float = None
_progress_last_current: int = 0
_smoothed_speed: float = 0.0


def set_progress_enabled(enabled: bool) -> None:
    global _progress_enabled
    _progress_enabled = bool(enabled)


def set_progress_mode(mode: str) -> None:
    global _progress_mode
    _progress_mode = mode


def is_progress_enabled() -> bool:
    return _progress_enabled


def reset_progress() -> None:
    global _progress_start_time, _progress_last_time, _progress_last_current, _smoothed_speed
    _progress_start_time = None
    _progress_last_time = None
    _progress_last_current = 0
    _smoothed_speed = 0.0


def _can_inline() -> bool:
    """能否原地刷新（用 \\r + ANSI 清行）"""
    if _progress_mode == 'none':
        return False
    if _progress_mode == 'tty':
        return True
    # auto
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False


def _format_speed(bps: float) -> str:
    if bps <= 0:
        return "  --.-- B/s"
    if bps < 1024:
        return f"{bps:6.2f} B/s"
    if bps < 1024 * 1024:
        return f"{bps / 1024:6.2f} KB/s"
    if bps < 1024 * 1024 * 1024:
        return f"{bps / (1024 * 1024):6.2f} MB/s"
    return f"{bps / (1024 * 1024 * 1024):6.2f} GB/s"


def _format_time(seconds: float) -> str:
    if seconds is None or seconds < 0 or seconds > 86400 * 100:
        return "--:--"
    seconds = int(seconds + 0.5)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _short(name: str, max_len: int = 28) -> str:
    if len(name) <= max_len:
        return name
    head = max_len // 2 - 2
    tail = max_len - head - 3
    return name[:head] + '...' + name[-tail:]


def print_progress(current: int, total: int, label: str = '',
                   bar_length: int = 36) -> None:
    """
    在一行内原地刷新进度条（\\r + ANSI 清行）。
    完成时输出换行，让这一行定格。
    """
    global _progress_start_time, _progress_last_time, _progress_last_current, _smoothed_speed

    if not _progress_enabled or not _can_inline():
        return

    if total <= 0:
        percent = 100.0
    else:
        percent = current / total * 100.0
    percent = max(0.0, min(100.0, percent))

    now = time.time()
    if _progress_start_time is None:
        _progress_start_time = now
        _progress_last_time = now
        _progress_last_current = 0

    # EMA 平滑速度
    dt = now - _progress_last_time
    if dt > 0.001:
        inst_speed = (current - _progress_last_current) / dt
        if _smoothed_speed <= 0:
            _smoothed_speed = inst_speed
        else:
            alpha = 0.3
            _smoothed_speed = (1 - alpha) * _smoothed_speed + alpha * inst_speed
        _progress_last_time = now
        _progress_last_current = current

    speed_str = _format_speed(_smoothed_speed)
    if current >= total:
        eta_str = "00:00"
    elif _smoothed_speed > 1e-6:
        eta_str = _format_time((total - current) / _smoothed_speed)
    else:
        eta_str = "--:--"

    filled = int(bar_length * percent / 100)
    bar = '█' * filled + '░' * (bar_length - filled)

    body = (f'{label} |{bar}| {percent:6.2f}%  '
            f'({current}/{total} 字节)  '
            f'{speed_str}  ETA {eta_str}')

    # \r 回车 + \x1b[2K 清除整行；再写新内容
    sys.stdout.write('\r\x1b[2K' + body)
    if current >= total:
        sys.stdout.write('\n')
    sys.stdout.flush()


# -------------------------- 解压模块 --------------------------
def decompress_lzp2(in_stream: BinaryIO, out_path):
    bytesIn = in_stream.read()
    total_size = len(bytesIn)

    magic = bytesIn[0:8]
    original_size = struct.unpack('<I', bytesIn[8:12])[0]
    compressed_size = struct.unpack('<I', bytesIn[12:16])[0]

    if magic != bytes.fromhex('4C5A5032AE47813F'):
        raise ValueError("Invalid LZP2 file format")

    buffer = bytearray()
    iterator = 0x10
    gap = 0

    reset_progress()
    label = f'解压 {_short(os.path.basename(out_path))}'
    report_step = max(1, total_size // 100)  # 1% 节流
    last_report = 0

    while iterator < len(bytesIn):
        if gap == 0:
            if iterator >= len(bytesIn):
                break
            current_byte = bytesIn[iterator]

            if current_byte & 0x80:
                gap, iterator = handle_reference(iterator, buffer, bytesIn)
            elif current_byte & 0x40:
                gap, iterator = handle_rle(iterator, buffer, bytesIn)
            else:
                gap = current_byte
                iterator += 1
        else:
            copy_len = min(gap, len(bytesIn) - iterator)
            buffer.extend(bytesIn[iterator:iterator + copy_len])
            iterator += copy_len
            gap -= copy_len

        if iterator - last_report >= report_step:
            print_progress(iterator, total_size, label=label)
            last_report = iterator

    with open(out_path, 'wb') as f:
        f.write(buffer[:original_size])

    print_progress(total_size, total_size, label=label)


def handle_reference(iterator, buffer, bytesIn):
    if iterator + 1 >= len(bytesIn):
        return 0, iterator

    cmd_byte = bytesIn[iterator]
    offset_low = bytesIn[iterator + 1]

    length = ((cmd_byte >> 3) & 0x0F) + 3
    offset_high = cmd_byte & 0x07
    offset = (offset_high << 8) | offset_low
    offset += 1

    if offset > len(buffer):
        raise ValueError("Invalid offset in compressed data")

    for _ in range(length):
        buffer.append(buffer[-offset] if offset else buffer[-1])

    return 0, iterator + 2


def handle_rle(iterator, buffer, bytesIn):
    if iterator + 2 >= len(bytesIn):
        return 0, iterator

    cmd_byte = bytesIn[iterator]
    count_low = bytesIn[iterator + 1]
    value = bytesIn[iterator + 2]

    count = ((cmd_byte & 0x3F) << 8) | count_low
    count += 4

    buffer.extend(bytes([value]) * count)
    return 0, iterator + 3


def decompress_lzp2_file(in_path, out_path):
    with open(in_path, 'rb') as in_file:
        decompress_lzp2(in_file, out_path)


# -------------------------- 压缩模块 --------------------------
def compress_lzp2(input_data: bytes) -> bytes:
    compressed = bytearray()
    compressed.extend(bytes.fromhex('4C5A5032AE47813F'))
    original_size = len(input_data)
    compressed.extend(struct.pack('<I', original_size))
    compressed.extend(b'\x00' * 4)

    output_buffer = bytearray()
    hash_table: Dict[int, List[int]] = {}
    pos = 0

    reset_progress()
    report_step = max(1, original_size // 100)
    last_report = 0

    while pos < len(input_data):
        rle_len = get_rle_length(input_data, pos)
        best_len, best_offset = find_best_match(output_buffer, input_data, pos, hash_table)

        if rle_len >= 4 and rle_len >= best_len:
            cmd = 0x40 | ((rle_len - 4) >> 8 & 0x3F)
            low_byte = (rle_len - 4) & 0xFF
            compressed.append(cmd)
            compressed.append(low_byte)
            compressed.append(input_data[pos])
            original_len = len(output_buffer)
            output_buffer.extend([input_data[pos]] * rle_len)
            update_hash_table_batch(output_buffer, hash_table, original_len, len(output_buffer))
            pos += rle_len
        elif best_len >= 3:
            offset_code = best_offset - 1
            offset_high = (offset_code >> 8) & 0x07
            offset_low = offset_code & 0xFF
            incr = best_len - 3
            cmd = 0x80 | (incr << 3) | offset_high
            compressed.append(cmd)
            compressed.append(offset_low)
            original_len = len(output_buffer)
            for i in range(best_len):
                ref_pos = original_len - best_offset + i
                if ref_pos < 0 or ref_pos >= original_len:
                    output_buffer.append(input_data[pos + i])
                else:
                    output_buffer.append(output_buffer[ref_pos])
            update_hash_table_batch(output_buffer, hash_table, original_len, len(output_buffer))
            pos += best_len
        else:
            max_literal_len = min(63, len(input_data) - pos)
            literal_len = 1
            while literal_len < max_literal_len:
                next_pos = pos + literal_len
                if (get_rle_length(input_data, next_pos) >= 4 or
                        find_best_match(output_buffer, input_data, next_pos, hash_table)[0] >= 3):
                    if literal_len >= 1:
                        break
                literal_len += 1

            compressed.append(literal_len)
            compressed.extend(input_data[pos:pos + literal_len])
            original_len = len(output_buffer)
            output_buffer.extend(input_data[pos:pos + literal_len])
            update_hash_table_batch(output_buffer, hash_table, original_len, len(output_buffer))
            pos += literal_len

        if pos - last_report >= report_step:
            print_progress(pos, original_size, label='压缩')
            last_report = pos

    data_size = len(compressed) - 16
    padding = (16 - (data_size % 16)) % 16
    total_data_size = data_size + padding
    compressed[12:16] = struct.pack('<I', total_data_size)
    compressed.extend(b'\x00' * padding)

    print_progress(original_size, original_size, label='压缩')

    return bytes(compressed)


def update_hash_table_batch(buffer: bytearray, hash_table: dict, start_pos: int, end_pos: int):
    for i in range(max(start_pos - 2, 0), end_pos - 2):
        if i + 2 >= len(buffer):
            continue
        current_triple = buffer[i:i + 3]
        key = (current_triple[0] << 16) | (current_triple[1] << 8) | current_triple[2]
        if key not in hash_table:
            hash_table[key] = []
        candidates = hash_table[key]

        candidates.append(i)

        valid_candidates = []
        for c in candidates:
            if len(buffer) - c <= 2048:
                valid_candidates.append(c)

        if len(valid_candidates) > 100:
            valid_candidates = valid_candidates[-100:]

        hash_table[key] = valid_candidates


def get_rle_length(data: bytes, pos: int) -> int:
    if pos >= len(data):
        return 0

    value = data[pos]
    max_len = min(pos + 16387, len(data))
    length = 1

    while pos + length < max_len and data[pos + length] == value:
        length += 1

    return length if length >= 4 else 0


def find_best_match(output_buffer: bytearray, input_data: bytes, pos: int,
                    hash_table: dict) -> Tuple[int, int]:
    max_offset = 2048
    max_len = 18

    if pos + 2 >= len(input_data):
        return 0, 0

    current_triple = input_data[pos:pos + 3]
    key = (current_triple[0] << 16) | (current_triple[1] << 8) | current_triple[2]

    candidates = hash_table.get(key, [])

    best_len, best_offset = 0, 0

    for candidate in reversed(candidates[-100:]):
        if candidate >= len(output_buffer):
            continue

        offset = len(output_buffer) - candidate
        if offset > max_offset:
            continue

        max_possible_len = min(max_len, len(input_data) - pos, len(output_buffer) - candidate)

        if candidate + 2 >= len(output_buffer):
            continue
        if output_buffer[candidate:candidate + 3] != current_triple:
            continue

        match_len = 3
        while (match_len < max_possible_len and
               pos + match_len < len(input_data) and
               candidate + match_len < len(output_buffer) and
               input_data[pos + match_len] == output_buffer[candidate + match_len]):
            match_len += 1

        if match_len > best_len:
            best_len = match_len
            best_offset = offset
            if best_len == max_len:
                break

    return (best_len, best_offset) if best_len >= 3 else (0, 0)


def compress_lzp2_file(input_path: str, output_path: str):
    with open(input_path, 'rb') as f:
        data = f.read()
    reset_progress()
    compressed = compress_lzp2(data)
    with open(output_path, 'wb') as f:
        f.write(compressed)


# -------------------------- 参数解析 --------------------------
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="LZP2压缩工具 v2.6（每文件单行原地刷新的进度条）",
        formatter_class=argparse.RawTextHelpFormatter
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-c", "--compress", metavar=("INPUT", "OUTPUT"), nargs=2,
                       help="单文件压缩模式")
    group.add_argument("-d", "--decompress", metavar=("INPUT", "OUTPUT"), nargs=2,
                       help="单文件解压模式")
    group.add_argument("-bc", "--batch-compress", metavar=("INPUTS", "OUTPUT_DIR"), nargs='+',
                       help="批量压缩模式")
    group.add_argument("-bd", "--batch-decompress", metavar=("INPUTS", "OUTPUT_DIR"), nargs='+',
                       help="批量解压模式")

    parser.add_argument("-p", "--progress", default="auto",
                        choices=["auto", "tty", "none"],
                        help=("进度显示模式：\n"
                              "  auto  自动：交互终端显示进度条，非终端不打进度（默认）\n"
                              "  tty   强制进度条（用 \\r+ANSI 原地刷新；IDE 里建议试这个）\n"
                              "  none  不显示进度"))

    return parser.parse_args()


# -------------------------- 批量处理 --------------------------
def process_batch(mode: str, inputs: List[str], output_dir: str):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    tasks: List[Path] = []
    for input_path in inputs:
        input_file = Path(input_path)
        if input_file.is_dir():
            for root, _, files in os.walk(input_file):
                for file in files:
                    if mode == "d" and not file.endswith(".lzp2"):
                        continue
                    tasks.append(Path(root) / file)
        else:
            tasks.append(input_file)

    total = len(tasks)
    processed = 0
    for idx, task in enumerate(tasks, start=1):
        if is_progress_enabled() and _can_inline():
            # 每个文件开始前，换行把上一个文件的进度条行“封口”
            sys.stdout.write(f"[{idx}/{total}] {task.name}\n")
            sys.stdout.flush()
        process_single(mode, task, output_path)
        processed += 1

    print(f"\n操作完成！成功处理 {processed} 个文件")


def process_single(mode: str, input_file: Path, output_dir: Path):
    try:
        if mode == "c":
            output = output_dir / f"{input_file.name}.lzp2"
            compress_lzp2_file(str(input_file), str(output))
        elif mode == "d":
            if input_file.suffix != ".lzp2":
                return
            output = output_dir / input_file.stem
            decompress_lzp2_file(str(input_file), str(output))

        print(f"[✓] {input_file} -> {output.relative_to(output_dir)}")
    except PermissionError:
        print(f"[✗] 权限拒绝: {input_file}")
    except Exception as e:
        print(f"[✗] 处理失败 {input_file}: {str(e)}")


# -------------------------- 主程序 --------------------------
def main():
    args = parse_arguments()
    set_progress_enabled(args.progress != 'none')
    set_progress_mode(args.progress)

    if args.compress:
        input_file, output_file = args.compress
        compress_lzp2_file(input_file, output_file)
        print(f"单文件压缩完成: {input_file} -> {output_file}")

    elif args.decompress:
        input_file, output_file = args.decompress
        decompress_lzp2_file(input_file, output_file)
        print(f"单文件解压完成: {input_file} -> {output_file}")

    elif args.batch_compress:
        *inputs, output_dir = args.batch_compress
        process_batch("c", inputs, output_dir)

    elif args.batch_decompress:
        *inputs, output_dir = args.batch_decompress
        process_batch("d", inputs, output_dir)


if __name__ == "__main__":
    main()
