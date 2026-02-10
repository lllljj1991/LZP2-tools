import os
import sys

def pad_or_truncate_file(filepath, target_size, auto_confirm=False):
    """填充或截断单个文件到指定大小"""
    try:
        current_size = os.path.getsize(filepath)
        
        if current_size == target_size:
            print(f"[{os.path.basename(filepath)}] 文件已满足大小，跳过")
            return True
        
        elif current_size < target_size:
            # 填充模式
            with open(filepath, 'r+b') as f:
                padding = target_size - current_size
                f.seek(0, 2)
                f.write(b'\x00' * padding)
                print(f"[{os.path.basename(filepath)}] 填充 {padding} 字节")
                return True
        
        else:
            # 截断模式：当前大小 > 目标大小
            if not auto_confirm:
                response = input(f"文件 {os.path.basename(filepath)} 当前大小为 {current_size} 字节，"
                               f"目标大小为 {target_size} 字节，\n"
                               f"这将丢弃 {current_size - target_size} 字节数据。确认截断？(y/N): ")
                if response.lower() != 'y':
                    print(f"[{os.path.basename(filepath)}] 用户取消操作")
                    return False
            
            # 执行截断
            with open(filepath, 'r+b') as f:
                f.truncate(target_size)
                print(f"[{os.path.basename(filepath)}] 截断为 {target_size} 字节")
                return True
    
    except Exception as e:
        print(f"[{os.path.basename(filepath)}] 错误：{str(e)}")
        return False

def process_target(path, target_size, auto_confirm=False):
    """处理文件或目录"""
    if os.path.isfile(path):
        pad_or_truncate_file(path, target_size, auto_confirm)
    
    elif os.path.isdir(path):
        print(f"开始处理目录：{path}")
        files_to_process = []
        
        # 收集需要处理的文件
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            if os.path.isfile(filepath):
                files_to_process.append(filepath)
        
        if not files_to_process:
            print("目录中没有找到可处理的文件")
            return
        
        print(f"找到 {len(files_to_process)} 个文件")
        
        # 对于目录，询问是否需要批量确认
        will_truncate_files = []
        for filepath in files_to_process:
            current_size = os.path.getsize(filepath)
            if current_size > target_size:
                will_truncate_files.append((os.path.basename(filepath), current_size))
        
        if will_truncate_files and not auto_confirm:
            print("\n以下文件将被截断（当前大小 > 目标大小）：")
            for filename, size in will_truncate_files:
                print(f"  - {filename}: {size} → {target_size} 字节 (丢弃 {size - target_size} 字节)")
            
            response = input(f"\n确认截断 {len(will_truncate_files)} 个文件？(y/N): ")
            if response.lower() != 'y':
                print("用户取消操作")
                return
        
        # 处理文件
        processed = 0
        success = 0
        for filepath in files_to_process:
            processed += 1
            if pad_or_truncate_file(filepath, target_size, auto_confirm or len(will_truncate_files) > 0):
                success += 1
        
        print(f"处理完成：共 {processed} 个文件，成功 {success} 个")
    
    else:
        raise ValueError("无效的路径类型")

def main():
    # 解析命令行参数
    auto_confirm = False
    args = sys.argv[1:]
    
    # 检查是否有 -y 或 --yes 参数
    if '-y' in args or '--yes' in args:
        auto_confirm = True
        args = [arg for arg in args if arg not in ['-y', '--yes']]
    
    if len(args) != 2:
        print("文件填充/截断工具")
        print("使用方法：python pad_file.py <文件/目录路径> <目标大小> [-y]")
        print("\n参数说明：")
        print("  <文件/目录路径>  单个文件路径或目录路径")
        print("  <目标大小>      目标字节数")
        print("  -y, --yes       自动确认所有操作（危险：可能导致数据丢失）")
        print("\n功能说明：")
        print("  1. 如果文件小于目标大小，填充二进制00")
        print("  2. 如果文件大于目标大小，截断文件（保留前N字节）")
        print("  3. 截断操作需要用户确认（除非使用 -y 参数）")
        print("\n示例：")
        print("  填充单个文件：python pad_file.py test.bin 1024")
        print("  处理整个目录：python pad_file.py ./data 2048")
        print("  自动确认操作：python pad_file.py ./data 512 -y")
        sys.exit(1)
    
    target_path = args[0]
    target_size_arg = args[1]
    
    # 验证目标大小合法性
    try:
        target_size = int(target_size_arg)
        if target_size <= 0:
            raise ValueError("目标大小必须为正整数")
    except ValueError:
        print("错误：目标大小必须为正整数。")
        sys.exit(1)
    
    # 验证路径存在性
    if not os.path.exists(target_path):
        print(f"错误：路径 '{target_path}' 不存在。")
        sys.exit(1)
    
    try:
        process_target(target_path, target_size, auto_confirm)
    except Exception as e:
        print(f"处理过程中发生错误：{str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
