import struct
import math
from typing import BinaryIO, Tuple, List, Dict
import sys

class LZP2Compressor:
    def __init__(self):
        self.window_size = 0x800  # 滑动窗口大小
        self.max_match_length = 18  # 最大匹配长度
        self.min_match_length = 3   # 最小匹配长度
        
    def compress(self, data: bytes) -> bytes:
        """
        压缩数据为LZP2格式
        """
        compressed = bytearray()
        i = 0
        data_len = len(data)
        
        while i < data_len:
            # 1. 查找最长匹配
            match_offset, match_length = self._find_longest_match(data, i)
            
            # 2. 检查RLE模式（连续相同字符）
            rle_length = self._get_rle_length(data, i)
            
            # 3. 选择最佳压缩模式
            if rle_length >= 4 and rle_length >= match_length:
                # 使用RLE压缩
                compressed.extend(self._encode_rle(rle_length, data[i]))
                i += rle_length
            elif match_length >= self.min_match_length:
                # 使用LZ77引用压缩
                compressed.extend(self._encode_reference(match_offset, match_length))
                i += match_length
            else:
                # 直接存储字节
                gap_end = self._find_gap_end(data, i)
                gap_length = gap_end - i
                
                # 确保gap长度不超过63（因为gap字段只有6位）
                gap_length = min(gap_length, 63)
                
                if gap_length > 0:
                    compressed.append(gap_length)  # gap长度
                    compressed.extend(data[i:i + gap_length])
                    i += gap_length
                else:
                    # 至少移动一个字节
                    compressed.append(1)
                    compressed.append(data[i])
                    i += 1
        
        # 填充到16的倍数
        padding_len = (16 - (len(compressed) % 16)) % 16
        if padding_len > 0:
            compressed.extend(bytes(padding_len))
        
        return bytes(compressed)
    
    def _find_longest_match(self, data: bytes, current_pos: int) -> Tuple[int, int]:
        """
        在滑动窗口中查找最长匹配
        """
        max_length = 0
        best_offset = 0
        
        # 滑动窗口起始位置
        window_start = max(0, current_pos - self.window_size)
        
        # 最小匹配长度
        min_len = self.min_match_length
        
        # 遍历滑动窗口中的位置
        for check_pos in range(window_start, current_pos):
            length = 0
            
            # 计算最大可能匹配长度
            max_possible = min(
                self.max_match_length,
                len(data) - current_pos,
                current_pos - check_pos
            )
            
            # 比较字符
            while (length < max_possible and 
                   data[check_pos + length] == data[current_pos + length]):
                length += 1
            
            # 更新最佳匹配
            if length >= min_len and length > max_length:
                max_length = length
                best_offset = current_pos - check_pos
        
        return best_offset, max_length
    
    def _get_rle_length(self, data: bytes, current_pos: int) -> int:
        """
        获取连续相同字符的长度
        """
        if current_pos >= len(data):
            return 0
            
        value = data[current_pos]
        length = 1
        
        while (current_pos + length < len(data) and 
               data[current_pos + length] == value and 
               length < 0x4003):  # RLE最大长度限制
            length += 1
            
        return length
    
    def _find_gap_end(self, data: bytes, current_pos: int) -> int:
        """
        找到可以直接存储的连续字节的结束位置
        """
        end_pos = current_pos
        while end_pos < len(data):
            # 检查是否可以从这里开始匹配或RLE
            match_offset, match_length = self._find_longest_match(data, end_pos)
            rle_length = self._get_rle_length(data, end_pos)
            
            # 如果找到足够长的匹配或RLE，停止
            if match_length >= self.min_match_length or rle_length >= 4:
                break
            
            # 如果gap长度达到最大，停止
            if end_pos - current_pos >= 63:
                break
                
            end_pos += 1
            
        return end_pos
    
    def _encode_reference(self, offset: int, length: int) -> bytes:
        """
        编码LZ77引用
        格式: [0b1xxxxxxx] [offset_low]
        """
        if offset == 0:
            return bytes([length])  # 实际上不应该发生
        
        # 计算编码长度 (3-18)
        encoded_length = min(length, self.max_match_length)
        
        # 构建第一个字节
        # 位布局: 1(固定) + 4位长度编码 + 3位offset高字节
        first_byte = 0x80  # 设置最高位
        
        # 添加长度编码 (3-18 映射到 0-15)
        length_code = encoded_length - 3
        
        # 设置位3-6
        if length_code & 0x01: first_byte |= 0x08  # 位3
        if length_code & 0x02: first_byte |= 0x10  # 位4
        if length_code & 0x04: first_byte |= 0x20  # 位5
        if length_code & 0x08: first_byte |= 0x40  # 位6
        
        # 添加offset高3位到低3位
        offset_high = (offset - 1) >> 8
        first_byte |= offset_high & 0x07
        
        # 第二个字节是offset的低8位
        offset_low = (offset - 1) & 0xFF
        
        return bytes([first_byte, offset_low])
    
    def _encode_rle(self, length: int, value: int) -> bytes:
        """
        编码RLE
        格式: [0b01xxxxxx] [length_low] [value]
        """
        # 计算存储的长度值 (实际长度 - 4)
        store_length = min(length, 0x4003) - 4
        
        # 第一个字节: 0x40 + 长度的高6位
        first_byte = 0x40 | ((store_length >> 8) & 0x3F)
        
        # 第二个字节: 长度的低8位
        second_byte = store_length & 0xFF
        
        return bytes([first_byte, second_byte, value])

def create_lzp2_header(original_size: int, compressed_size: int) -> bytes:
    """
    创建LZP2文件头
    """
    header = bytearray()
    
    # 固定头: "LZP2" + 魔数
    header.extend([0x4C, 0x5A, 0x50, 0x32, 0xAE, 0x47, 0x81, 0x3F])
    
    # 原始文件大小 (小端序)
    header.extend(struct.pack('<I', original_size))
    
    # 压缩数据大小 (小端序)
    header.extend(struct.pack('<I', compressed_size))
    
    return bytes(header)

def compress_lzp2(in_stream: BinaryIO, out_stream: BinaryIO):
    """
    压缩文件为LZP2格式
    """
    # 读取输入文件
    data = in_stream.read()
    original_size = len(data)
    
    # 压缩数据
    compressor = LZP2Compressor()
    compressed_data = compressor.compress(data)
    
    # 计算压缩后大小 (不包括文件头)
    compressed_size = len(compressed_data)
    
    # 确保压缩数据大小是16的倍数
    if compressed_size % 16 != 0:
        padding = 16 - (compressed_size % 16)
        compressed_data += b'\x00' * padding
        compressed_size = len(compressed_data)
    
    # 写入文件头
    header = create_lzp2_header(original_size, compressed_size)
    out_stream.write(header)
    
    # 写入压缩数据
    out_stream.write(compressed_data)

def compress_lzp2_file(in_path: str, out_path: str):
    """
    压缩文件为LZP2格式 (文件接口)
    """
    with open(in_path, 'rb') as in_file:
        with open(out_path, 'wb') as out_file:
            compress_lzp2(in_file, out_file)
    
    # 输出压缩信息
    original_size = os.path.getsize(in_path)
    compressed_size = os.path.getsize(out_path) - 16  # 减去文件头
    ratio = (compressed_size / original_size) * 100 if original_size > 0 else 0
    
    print(f"压缩完成: {in_path} -> {out_path}")
    print(f"原始大小: {original_size} 字节")
    print(f"压缩大小: {compressed_size} 字节 (不包括16字节文件头)")
    print(f"压缩率: {ratio:.2f}%")

def main():
    """
    主函数：命令行接口
    """
    if len(sys.argv) != 3:
        print("使用方法: python lzp2_compress.py <输入文件> <输出文件>")
        print("示例: python lzp2_compress.py input.txt output.lzp2")
        sys.exit(1)
    
    in_path = sys.argv[1]
    out_path = sys.argv[2]
    
    compress_lzp2_file(in_path, out_path)

if __name__ == "__main__":
    import os
    main()