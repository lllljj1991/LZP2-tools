import sys

def process_tm2_alpha(input_path, output_path):
    # 读取文件内容到bytearray以便修改
    with open(input_path, 'rb') as f:
        data = bytearray(f.read())
    
    # 验证文件头
    if len(data) < 64 or data[0:4] != b'TIM2':
        raise ValueError("Invalid TM2 file format")
    
    # 读取色位数（小端序）
    n = int.from_bytes(data[30:32], byteorder='little')
    if n <= 0:
        raise ValueError("Invalid color depth value")
    
    # 计算调色板位置和大小
    file_size = len(data)
    palette_size = 4 * n
    palette_start = file_size - palette_size
    
    # 验证调色板位置有效性
    if palette_start < 64 or palette_start + palette_size > file_size:
        raise ValueError("Invalid palette position")
    
    # 处理每个调色板项的alpha通道
    for i in range(n):
        alpha_pos = palette_start + i * 4 + 3
        original = data[alpha_pos]
        data[alpha_pos] = (original + 1) // 2  # 向上取整处理
    
    # 写入输出文件
    with open(output_path, 'wb') as f:
        f.write(data)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python tm2_alpha_adjust.py <input.tm2> <output.tm2>")
        sys.exit(1)
    
    try:
        process_tm2_alpha(sys.argv[1], sys.argv[2])
        print("Alpha channel processing completed successfully")
    except Exception as e:
        print(f"Error processing file: {str(e)}")
        sys.exit(1)