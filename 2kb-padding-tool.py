import sys
import os

BLOCK_SIZE = 2048

def process_file(filename):
    """处理单个文件的核心逻辑"""
    try:
        size = os.path.getsize(filename)
    except Exception as e:
        print(f"\n⚠️ 错误文件 {filename}:")
        print(f"    {str(e)}")
        return False

    remainder = size % BLOCK_SIZE
    if remainder == 0:
        print(f"✓ {filename} 已对齐 (大小 {size} 字节)")
        return True

    padding = BLOCK_SIZE - remainder
    try:
        with open(filename, 'ab') as f:
            f.write(b'\x00' * padding)
        new_size = size + padding
        print(f"★ {filename} 填充成功:")
        print(f"    原大小: {size:>8} 字节")
        print(f"    填充量: {padding:>8} 字节")
        print(f"    新大小: {new_size:>8} 字节 ({new_size // BLOCK_SIZE} 块)")
        return True
    except Exception as e:
        print(f"\n⚠️ 写入失败 {filename}:")
        print(f"    {str(e)}")
        return False

def batch_process(target_path):
    """批量处理目录或单个文件"""
    processed = 0
    success = 0
    failures = []

    if os.path.isfile(target_path):
        # 处理单个文件
        processed += 1
        if process_file(target_path):
            success += 1
        else:
            failures.append(target_path)
    else:
        # 处理目录下所有文件
        print(f"扫描目录: {os.path.abspath(target_path)}")
        for entry in os.listdir(target_path):
            full_path = os.path.join(target_path, entry)
            if os.path.isfile(full_path):
                processed += 1
                if process_file(full_path):
                    success += 1
                else:
                    failures.append(entry)

    # 输出统计信息
    print("\n" + "="*50)
    print(f"处理完成: 总共 {processed} 个文件")
    print(f"✓ 成功: {success}")
    if failures:
        print(f"⚠️ 失败: {len(failures)}")
        print("\n失败文件列表:")
        for f in failures:
            print(f"  - {f}")

def main():
    # 处理命令行参数
    if len(sys.argv) > 2:
        print("使用方法: python pad_file.py [目录或文件路径]")
        print("注意: 未指定路径时处理当前目录")
        sys.exit(1)

    target_path = sys.argv[1] if len(sys.argv) == 2 else "."
    
    if not os.path.exists(target_path):
        print(f"错误路径: {target_path} 不存在")
        sys.exit(1)

    batch_process(target_path)

if __name__ == "__main__":
    main()