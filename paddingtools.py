import os
import sys

def pad_file(filepath, target_size):
    """填充单个文件到指定大小"""
    try:
        with open(filepath, 'r+b') as f:
            current_size = os.path.getsize(filepath)
            if current_size >= target_size:
                print(f"[{os.path.basename(filepath)}] 已满足大小，跳过")
                return True
            
            padding = target_size - current_size
            f.seek(0, 2)
            f.write(b'\x00' * padding)
            print(f"[{os.path.basename(filepath)}] 成功填充 {padding} 字节")
            return True

    except Exception as e:
        print(f"[{os.path.basename(filepath)}] 错误：{str(e)}")
        return False

def process_target(path, target_size):
    """处理文件或目录"""
    if os.path.isfile(path):
        pad_file(path, target_size)
    elif os.path.isdir(path):
        print(f"开始处理目录：{path}")
        processed = 0
        success = 0
        
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            if os.path.isfile(filepath):
                processed += 1
                if pad_file(filepath, target_size):
                    success += 1
        
        print(f"处理完成：共 {processed} 个文件，成功 {success} 个")
    else:
        raise ValueError("无效的路径类型")

def main():
    if len(sys.argv) != 3:
        print("使用方法：python pad_file.py <文件/目录路径> <目标大小>")
        print("示例：")
        print("  处理单个文件：python pad_file.py test.bin 1024")
        print("  处理整个目录：python pad_file.py ./data 2048")
        sys.exit(1)

    target_path = sys.argv[1]
    target_size = sys.argv[2]

    try:
        target_size = int(target_size)
        if target_size <= 0:
            raise ValueError
    except ValueError:
        print("错误：目标大小必须为正整数")
        sys.exit(1)

    if not os.path.exists(target_path):
        print(f"错误：路径 '{target_path}' 不存在")
        sys.exit(1)

    try:
        process_target(target_path, target_size)
    except Exception as e:
        print(f"处理过程中发生错误：{str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()