import sys
import struct
import os
import argparse
from typing import BinaryIO, Dict, Tuple, List
from pathlib import Path

# -------------------------- 解压模块 --------------------------
def decompress_lzp2(in_stream: BinaryIO, out_path):
    # 原有解压代码保持不变
    bytesIn = in_stream.read()
    
    magic = bytesIn[0:8]
    original_size = struct.unpack('<I', bytesIn[8:12])[0]
    compressed_size = struct.unpack('<I', bytesIn[12:16])[0]
    
    if magic != bytes.fromhex('4C5A5032AE47813F'):
        raise ValueError("Invalid LZP2 file format")
    
    buffer = bytearray()
    iterator = 0x10
    gap = 0
    
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
            buffer.extend(bytesIn[iterator:iterator+copy_len])
            iterator += copy_len
            gap -= copy_len

    with open(out_path, 'wb') as f:
        f.write(buffer[:original_size])

def handle_reference(iterator, buffer, bytesIn):
    # 原有代码保持不变
    if iterator + 1 >= len(bytesIn):
        return 0, iterator
    
    cmd_byte = bytesIn[iterator]
    offset_low = bytesIn[iterator+1]
    
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
    # 原有代码保持不变
    if iterator + 2 >= len(bytesIn):
        return 0, iterator
    
    cmd_byte = bytesIn[iterator]
    count_low = bytesIn[iterator+1]
    value = bytesIn[iterator+2]
    
    count = ((cmd_byte & 0x3F) << 8) | count_low
    count += 4
    
    buffer.extend(bytes([value]) * count)
    return 0, iterator + 3

def decompress_lzp2_file(in_path, out_path):
    # 原有代码保持不变
    with open(in_path, 'rb') as in_file:
        decompress_lzp2(in_file, out_path)

# -------------------------- 压缩模块 --------------------------
def compress_lzp2(input_data: bytes) -> bytes:
    compressed = bytearray()
    compressed.extend(bytes.fromhex('4C5A5032AE47813F'))
    original_size = len(input_data)
    compressed.extend(struct.pack('<I', original_size))
    compressed.extend(b'\x00' * 4)  # Placeholder for compressed size

    output_buffer = bytearray()
    hash_table: Dict[int, List[int]] = {}
    pos = 0

    while pos < len(input_data):
        # 优先检测RLE
        rle_len = get_rle_length(input_data, pos)
        best_len, best_offset = find_best_match(output_buffer, input_data, pos, hash_table)
        
        # 选择RLE或引用中更优的
        if rle_len >= 4 and rle_len >= best_len:
            cmd = 0x40 | ((rle_len - 4) >> 8 & 0x3F)
            low_byte = (rle_len - 4) & 0xFF
            compressed.append(cmd)
            compressed.append(low_byte)
            compressed.append(input_data[pos])
            # 批量更新哈希表
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
            # 批量更新哈希表
            original_len = len(output_buffer)
            for _ in range(best_len):
                ref_pos = original_len - best_offset + _
                if ref_pos < 0 or ref_pos >= original_len:
                    ref_pos = 0
                output_buffer.append(output_buffer[ref_pos])
            update_hash_table_batch(output_buffer, hash_table, original_len, len(output_buffer))
            pos += best_len
        else:
            # 处理字面量，优化为贪心策略
            max_literal_len = min(63, len(input_data) - pos)
            literal_len = 1
            while literal_len < max_literal_len and (pos + literal_len < len(input_data)):
                next_pos = pos + literal_len
                if get_rle_length(input_data, next_pos) >=4 or find_best_match(output_buffer, input_data, next_pos, hash_table)[0] >=3:
                    break
                literal_len +=1
            compressed.append(literal_len)
            compressed.extend(input_data[pos:pos+literal_len])
            original_len = len(output_buffer)
            output_buffer.extend(input_data[pos:pos+literal_len])
            update_hash_table_batch(output_buffer, hash_table, original_len, len(output_buffer))
            pos += literal_len

    # 更新压缩后大小并填充
    total_size = len(compressed) + (16 - (len(compressed) % 16)) % 16
    compressed[12:16] = struct.pack('<I', total_size)
    compressed.extend(b'\x00' * (total_size - len(compressed)))
    return bytes(compressed)

def update_hash_table_batch(buffer: bytearray, hash_table: dict, start_pos: int, end_pos: int):
    """批量更新哈希表，处理从start_pos到end_pos新增的三元组"""
    for i in range(max(start_pos -2, 0), end_pos -2):
        if i +2 >= len(buffer):
            continue
        current_triple = buffer[i:i+3]
        key = (current_triple[0] << 16) | (current_triple[1] << 8) | current_triple[2]
        if key not in hash_table:
            hash_table[key] = []
        candidates = hash_table[key]
        # 维护候选列表，保留最近50个且偏移不超过2048
        candidates.append(i)
        # 过滤无效候选
        valid_candidates = []
        for c in candidates:
            if (len(buffer) - c) <= 2048:
                valid_candidates.append(c)
        # 保留最多50个
        if len(valid_candidates) > 50:
            valid_candidates = valid_candidates[-50:]
        hash_table[key] = valid_candidates

def get_rle_length(data: bytes, pos: int) -> int:
    if pos >= len(data):
        return 0
    current = data[pos]
    max_end = min(pos + 16387, len(data))
    end = pos +1
    while end < max_end and data[end] == current:
        end +=1
    length = end - pos
    return length if length >=4 else 0

def find_best_match(output_buffer: bytearray, input_data: bytes, pos: int, hash_table: dict) -> Tuple[int, int]:
    max_offset = 2048
    max_len = 18
    if pos +2 >= len(input_data):
        return (0, 0)
    current_triple = input_data[pos:pos+3]
    key = (current_triple[0] << 16) | (current_triple[1] << 8) | current_triple[2]
    candidates = hash_table.get(key, [])[-50:]  # 只检查最近50个候选

    best_len, best_offset = 0, 0
    for candidate in reversed(candidates):  # 逆序检查最近的候选
        if candidate +2 >= len(output_buffer):
            continue
        offset = len(output_buffer) - candidate
        if offset > max_offset:
            continue
        max_possible_len = min(max_len, len(input_data) - pos, len(output_buffer) - candidate)
        # 使用切片比较提高速度
        match_len = 0
        buffer_slice = output_buffer[candidate:candidate+max_possible_len]
        input_slice = input_data[pos:pos+max_possible_len]
        while match_len < len(buffer_slice) and buffer_slice[match_len] == input_slice[match_len]:
            match_len +=1
        if match_len > best_len or (match_len == best_len and offset < best_offset):
            best_len = match_len
            best_offset = offset
            if best_len == max_len:
                break  # 提前终止
    return (best_len, best_offset) if best_offset <= max_offset and best_len >=3 else (0, 0)

def compress_lzp2_file(input_path: str, output_path: str):
    with open(input_path, 'rb') as f:
        data = f.read()
    compressed = compress_lzp2(data)
    with open(output_path, 'wb') as f:
        f.write(compressed)

# -------------------------- 新参数解析逻辑 --------------------------
def parse_arguments():
    """使用argparse处理命令行参数"""
    parser = argparse.ArgumentParser(
        description="LZP2压缩工具 v2.1",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # 模式选择
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-c", "--compress", metavar=("INPUT", "OUTPUT"), nargs=2,
                      help="单文件压缩模式\n示例: lzp2.py -c input.txt output.lzp2")
    group.add_argument("-d", "--decompress", metavar=("INPUT", "OUTPUT"), nargs=2,
                      help="单文件解压模式\n示例: lzp2.py -d input.lzp2 output.txt")
    group.add_argument("-bc", "--batch-compress", metavar=("INPUTS", "OUTPUT_DIR"), nargs='+',
                      help="批量压缩模式\n示例: lzp2.py -bc file1.txt file2.jpg output_dir/")
    group.add_argument("-bd", "--batch-decompress", metavar=("INPUTS", "OUTPUT_DIR"), nargs='+',
                      help="批量解压模式\n示例: lzp2.py -bd file1.lzp2 file2.lzp2 output_dir/")

    return parser.parse_args()

# -------------------------- 增强版批量处理 --------------------------
def process_batch(mode: str, inputs: List[str], output_dir: str):
    """处理批量模式"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    processed = 0
    for input_path in inputs:
        input_file = Path(input_path)
        
        # 处理目录输入
        if input_file.is_dir():
            for root, _, files in os.walk(input_file):
                for file in files:
                    if mode == "d" and not file.endswith(".lzp2"):
                        continue
                    src = Path(root) / file
                    process_single(mode, src, output_path)
                    processed += 1
        else:
            process_single(mode, input_file, output_path)
            processed += 1
    
    print(f"\n操作完成！成功处理 {processed} 个文件")

def process_single(mode: str, input_file: Path, output_dir: Path):
    """处理单个文件"""
    try:
        # 生成输出路径
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

# -------------------------- 主程序逻辑 --------------------------
def main():
    args = parse_arguments()
    
    # 单文件模式
    if args.compress:
        input_file, output_file = args.compress
        compress_lzp2_file(input_file, output_file)
        print(f"单文件压缩完成: {input_file} -> {output_file}")
    
    elif args.decompress:
        input_file, output_file = args.decompress
        decompress_lzp2_file(input_file, output_file)
        print(f"单文件解压完成: {input_file} -> {output_file}")
    
    # 批量压缩模式
    elif args.batch_compress:
        *inputs, output_dir = args.batch_compress
        process_batch("c", inputs, output_dir)
    
    # 批量解压模式
    elif args.batch_decompress:
        *inputs, output_dir = args.batch_decompress
        process_batch("d", inputs, output_dir)

if __name__ == "__main__":
    main()