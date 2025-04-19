import os
import sys
import argparse

def process_single_file(input_path, output_dir, verbose=False):
    """处理单个文件的核心逻辑"""
    try:
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        counter = 1
        
        with open(input_path, 'rb') as f:
            # 读取文件数量
            num_files_bytes = f.read(4)
            num_files = int.from_bytes(num_files_bytes, 'little')

            # 读取所有文件块大小
            sizes = []
            for _ in range(num_files):
                size_bytes = f.read(4)
                size = int.from_bytes(size_bytes, 'little') * 16
                sizes.append(size)

            # 计算文件头填充
            header_size = 4 + 4 * num_files
            padding = (16 - (header_size % 16)) % 16
            f.read(padding)
            
            # 计算偏移量
            offsets = []
            current_offset = header_size + padding
            for size in sizes:
                offsets.append(current_offset)
                current_offset += size

            # 处理每个文件块
            for idx, (offset, size) in enumerate(zip(offsets, sizes)):
                f.seek(offset)
                file_data = f.read(size)
                
                if len(file_data) >= 16 and file_data[:4] == b'GT1G':
                    g1t_size = int.from_bytes(file_data[8:12], 'little')
                    valid_size = min(g1t_size, len(file_data))
                    
                    # 生成带源文件名的输出路径
                    output_filename = f"{base_name}_{counter:04d}.g1t"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    with open(output_path, 'wb') as out_file:
                        out_file.write(file_data[:valid_size])
                    
                    if verbose:
                        print(f"从 {os.path.basename(input_path)} 提取 {output_filename}")
                    counter += 1

            return True
    except Exception as e:
        print(f"处理 {os.path.basename(input_path)} 失败: {str(e)}")
        return False

def batch_process(input_path, output_dir, verbose=False):
    """批量处理入口"""
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    processed_files = 0
    success_count = 0
    
    # 判断输入类型
    if os.path.isfile(input_path):
        # 处理单个文件
        if process_single_file(input_path, output_dir, verbose):
            success_count += 1
        processed_files += 1
    elif os.path.isdir(input_path):
        # 遍历目录下的所有文件
        for filename in os.listdir(input_path):
            file_path = os.path.join(input_path, filename)
            if os.path.isfile(file_path):
                if process_single_file(file_path, output_dir, verbose):
                    success_count += 1
                processed_files += 1
    else:
        raise ValueError("无效的输入路径")

    print(f"\n处理完成！成功处理 {success_count}/{processed_files} 个文件")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="G1T文件批量提取工具",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("input", 
                      help="输入文件或目录路径")
    parser.add_argument("-o", "--output",
                      default="extracted_g1t",
                      help="输出目录（默认：extracted_g1t）")
    parser.add_argument("-v", "--verbose",
                      action="store_true",
                      help="显示详细处理信息")
    
    args = parser.parse_args()

    # 输入路径验证
    if not os.path.exists(args.input):
        print(f"错误：输入路径 '{args.input}' 不存在")
        sys.exit(1)

    print("\n" + "="*50)
    print(f" 批量处理启动")
    print(f" 输入路径: {args.input}")
    print(f" 输出目录: {args.output}")
    print("="*50)
    
    try:
        batch_process(args.input, args.output, args.verbose)
    except Exception as e:
        print(f"\n[错误] {str(e)}")
        sys.exit(1)