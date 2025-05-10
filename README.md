# LZP2-tools

A Python script for unpack and repack LZP2 files of Dynasty Warriors 4 &amp; 5. Tested on PC and PS2 version, original and XL version. 

一款Python脚本，用于解包和打包真·三国无双3&amp;4中的LZP2加密文件，适用于PC&amp;PS2版，本传或猛将传均可。

使用方式/Usage：

单文件解包/single file unpack:

python lzp2.py -d <INPUT> <OUTPUT>  e.g. lzp2.py -d output.lzp2 input.txt

单文件打包/single file repack:

python lzp2.py -c <INPUT> <OUTPUT> 

e.g. lzp2.py -c output.txt input.lzp2

多文件解包/multiple files unpack:

python lzp2.py -bd <INPUTS> <OUTPUT_DIR> 

e.g. lzp2.py -bd file1.txt file2.jpg output_dir/ 

or lzp2.py -bd input_dir/ output_dir/

多文件打包/multiple files repack:

python lzp2.py -bc <INPUTS> <OUTPUT_DIR> 

e.g. lzp2.py -bc file1.lzp2 file2.lzp2 output_dir/ 

or lzp2.py -bc input_dir/ output_dir/

The unpack code is optimized from DW5Tools created by synch12. https://github.com/synch12/DW5Tools

解包代码优化自synch12编写的工具DW5Tools。
