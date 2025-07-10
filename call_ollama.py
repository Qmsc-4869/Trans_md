import ollama
import time
import os
import requests
from ollama import ResponseError
import re
import sys

input_text = """我将给你 PX4 的英文文档，请结合你的知识和给出的文档上下文内容，将英文文档翻译为地道且通顺的中文。
要求:
1. 请翻译中括号里的英文
1. 请勿输出其他任何无关内容和原文中未出现过的字符，你需要按照原文格式翻译后输出，尽可能的翻译可翻译部分。
2. 保留原文中任何的资源链接。
3. 特殊内容不用翻译，例如:WARNING，代码等，但需保留原格式。
4. vehicle请统一翻译为机体，保留英文中特指的专有名词。
5. 如果遇到无法准确翻译的词汇，请直接使用源英文词汇。
6. 请勿在输出内容中出现 ```markdown ```，直接输出内容即可。
示例输入：
# Actuators

This section contains topics about the core actuators used for flight control (ESC/motors, and servos), and how they are assigned to the flight controller outputs, configured, and calibrated.
示例输出：
# 执行器

本节介绍飞行控制中核心执行器(如电调/电机和舵机)的使用方式,包括它们如何分配到飞控输出、如何配置以及如何进行校准。

原文：
{text}
"""

summary_input_text = """我将给你 PX4 的英文文档，请结合你的知识和给出的文档上下文内容，请将中括号里的内容翻译为中文。
要求:
1. 请勿输出其他任何无关内容和原文中未出现过的字符，你需要按照原文格式翻译后输出。
2. 需要将中括号里的英文翻译为中文，尽可能参照大疆、极飞等头部厂商的航空电子设备命名规范，确保行业术语一致性。
3. 保留原文中任何的资源链接。
4. 特殊内容不用翻译，例如:WARNING，代码等，但需保留原格式。
5. vehicle请统一翻译为机体，保留英文中特指的专有名词。
6. 如果遇到无法准确翻译的词汇，请直接使用源英文词汇。
7. 请勿在输出内容中出现 ```markdown ```，直接输出内容即可。

示例输入：

- [Multicopters](frames_multicopter/index.md)
- [Features](features_mc/index.md)
- [Flight Modes](flight_modes_mc/index.md)
- [Position Mode (MC)](flight_modes_mc/position.md)

示例输出：

- [多旋翼](frames_multicopter/index.md)
- [功能特性](features_mc/index.md)
- [飞行模式](flight_modes_mc/index.md)
- [定位模式(多旋翼)](flight_modes_mc/position.md)

原文：
{text}
"""
# 定义 baseurl
BASE_URL = "http://172.20.163.29:11434"  # 可以改为你的实际服务地址

# 创建 Ollama 客户端并指定 baseurl
client = ollama.Client(host=BASE_URL)


def log_print(message):
    """打印日志并强制刷新输出缓冲区，确保实时显示"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    sys.stdout.flush()  # 强制刷新输出缓冲区


def extract_content_without_thinking(text):
    """提取思考标签之外的内容"""
    # 移除 <think> 标签及其内容
    pattern = r'<think>.*?</think>'
    cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL)
    return cleaned_text


# 翻译summary.md时用于提取标签等级
def get_label_class(contest):
    lines = contest.split('\n')
    label_class = []
    for line in lines:
        if line != "":
            # 计算字符串前有几个空格
            space_counts = 0
            while line[space_counts] == ' ':
                space_counts += 1

            if line[space_counts] == '-':
                label_class.append(space_counts)

    return label_class


def split_summary(markdown_text):
    """分割summary.md文档为多个段落, 返回分割后的段落，和标签等级"""
    label_class = get_label_class(markdown_text)

    lines = markdown_text.split('\n')
    sections = []
    current_section = []
    # 当前段落字符数
    current_char = 0
    # 最大字符数， 当段落字符数超过max_char则分割为一段
    max_char = 1024

    for line in lines:
        line = line.strip()
        if line != "":
            # 分割段落
            if current_char > max_char:
                sections.append('\n'.join(current_section) + '\n')
                current_section = []
                current_char = 0
            current_section.append(line)
            current_char += len(line)

    if current_section:
        sections.append('\n'.join(current_section) + '\n')

    return sections, label_class


def split_markdown_by_headers(markdown_text, is_summary=False):
    """
    按照标题层级分割markdown文本
    - 一级标题(#)与其直接内容(不包括子标题)作为一段
    - 二级标题(##)及其内容(不包括子标题)作为独立段落
    - 三级标题(##)及其内容作为独立段落

    Args:
        markdown_text (str): 输入的markdown文本

    Returns:
        list: 分割后的文本段落列表
    """
    # 判断是否为summary.md
    if is_summary:
        return split_summary(markdown_text)

    lines = markdown_text.split('\n')
    sections = []
    current_section = []

    for line in lines:
        # 如果遇到三级标题，且当前段落不为空，保存当前段落
        if line.startswith('### ') and current_section:
            sections.append('\n'.join(current_section) + '\n')
            current_section = []
        # 如果遇到二级标题，且当前段落不为空，保存当前段落
        elif line.startswith('## ') and current_section:
            sections.append('\n'.join(current_section) + '\n')
            current_section = []
        # 如果遇到一级标题，且当前段落不为空，保存当前段落
        elif line.startswith('# ') and current_section:
            sections.append('\n'.join(current_section) + '\n')
            current_section = []

        # 将当前行添加到当前段落
        current_section.append(line)
    # 添加最后一个段落
    if current_section:
        sections.append('\n'.join(current_section) + '\n')

    return sections, None


def translationOneMd(text, max_retries=10, is_summary=False):
    """翻译单个Markdown文件或文件片段，包含重试机制"""
    if is_summary:
        send_text = summary_input_text.format(text=text)
    else:
        send_text = input_text.format(text=text)
    
    for attempt in range(max_retries):
        try:
            log_print(f"    尝试翻译... (第 {attempt + 1} 次)")
            
            response = client.chat(
                model='qwen3:32b',  # 使用指定的模型
                messages=[
                    {
                        'role': 'user',
                        'content': send_text
                    }
                ]
            )
            
            # 获取原始内容
            raw_content = response['message']['content']
            
            # 提取思考标签之外的内容
            cleaned_content = extract_content_without_thinking(raw_content)
            
            if cleaned_content.strip():  # 确保内容不为空
                log_print(f"    翻译成功！")
                return cleaned_content
            else:
                log_print(f"    翻译内容为空，重试中...")
                continue
                
        except requests.exceptions.ConnectionError as e:
            log_print(f"    连接失败 (第 {attempt + 1} 次): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # 等待2秒后重试
                
        except requests.exceptions.Timeout as e:
            log_print(f"    请求超时 (第 {attempt + 1} 次): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                
        except ResponseError as e:
            log_print(f"    Ollama响应错误 (第 {attempt + 1} 次): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                
        except Exception as e:
            log_print(f"    未知错误 (第 {attempt + 1} 次): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    log_print(f"    翻译失败，达到最大重试次数 ({max_retries})")
    return ""


def translate_long_content(content, is_summary=False):
    """翻译长内容，自动分段处理"""
    if len(content) <= 4000:
        log_print(f"  文件较短({len(content)}字符)，直接翻译")
        # 如果是summary.md,则需提取标签
        if is_summary:
            label_class = get_label_class(content)
            return translationOneMd(content, is_summary=is_summary), label_class
        else:
            return translationOneMd(content), None
    
    log_print(f"  文件较长({len(content)}字符)，进行分段翻译")
    sections, label_class = split_markdown_by_headers(content, is_summary=is_summary)
    log_print(f"  分割为 {len(sections)} 段")
    
    translated_sections = []
    for i, section in enumerate(sections, 1):
        log_print(f"  翻译第 {i}/{len(sections)} 段 ({len(section)}字符)")
        translated = translationOneMd(section, is_summary=is_summary)
        if translated.strip():
            translated_sections.append(translated)
        else:
            log_print(f"  第 {i} 段翻译失败")
            return ""  # 如果有任何一段翻译失败，返回空字符串
    
    # 拼接所有翻译结果
    final_result = ''.join(translated_sections)
    log_print(f"  分段翻译完成，总长度: {len(final_result)}字符")
    return final_result, label_class


def ensure_directory_exists(file_path):
    """确保目录存在，如果不存在则创建"""
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        log_print(f"  创建目录: {directory}")


def normalize_path(path):
    """标准化路径，统一使用正斜杠"""
    return path.replace('\\', '/')


def get_relative_path_key(file_path, base_folder):
    """获取用于比较的相对路径键值"""
    relative_path = os.path.relpath(file_path, base_folder)
    return normalize_path(relative_path)


def add_label_class(translated, label_class):
    '''
    给翻译后的标签添加等级
    '''
    lines = translated.split('\n')
    i = 0
    res_text = []
    for line in lines:
        if line.strip() != '':
            res_text.append(' ' * label_class[i] + line.strip())
            i += 1
    return '\n'.join(res_text)


def process_all_md_files(source_folder, target_folder, files_to_translate=None, is_summary=False):
    """递归处理所有Markdown文件"""
    
    # 确保目标文件夹存在
    if not os.path.exists(target_folder):
        os.makedirs(target_folder, exist_ok=True)
    
    # 如果没有指定要翻译的文件列表，则处理所有文件
    if files_to_translate is None:
        files_to_translate = []
        for root, dirs, files in os.walk(source_folder):
            for filename in files:
                if filename.endswith(".md"):
                    source_file_path = os.path.join(root, filename)
                    relative_path = get_relative_path_key(source_file_path, source_folder)
                    files_to_translate.append(relative_path)
    
    # 统计信息
    total_files = len(files_to_translate)
    success_files = 0
    failed_files = 0
    
    log_print(f"开始翻译 {total_files} 个文件...")
    
    for index, relative_path in enumerate(files_to_translate, 1):
        # 构建源文件路径和目标文件路径
        source_file_path = os.path.join(source_folder, relative_path)
        target_file_path = os.path.join(target_folder, relative_path)
        
        log_print(f"处理文件 [{index}/{total_files}]: {relative_path}")
        
        try:
            # 确保目标目录存在
            ensure_directory_exists(target_file_path)
            
            # 读取源文件
            with open(source_file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            log_print(f"  文件大小: {len(content)} 字符")
            
            # 翻译内容（处理长文档）
            translated, label_class = translate_long_content(content, is_summary)

            # 如果翻译Markdown标签目录
            if is_summary:
                # 恢复标签级别
                translated = add_label_class(translated, label_class)

            # 只有翻译成功时才写入文件
            if translated.strip():
                with open(target_file_path, "w", encoding="utf-8") as f:
                    f.write(translated)
                success_files += 1
                log_print(f"  ✓ 翻译成功并保存: {target_file_path}")
            else:
                failed_files += 1
                log_print(f"  ✗ 翻译失败，跳过创建文件: {relative_path}")
                        
        except Exception as e:
            failed_files += 1
            log_print(f"  ✗ 处理文件时出错: {e}")
            log_print(f"  跳过创建文件: {relative_path}")
    
    # 输出统计信息
    log_print(f"翻译完成!")
    log_print(f"待翻译文件: {total_files}")
    log_print(f"成功翻译: {success_files}")
    log_print(f"失败跳过: {failed_files}")
    log_print(f"成功率: {success_files/total_files*100:.1f}%" if total_files > 0 else "成功率: 0%")


def check_files_exist(source_folder, target_folder):
    """检查哪些文件需要翻译，返回需要翻译的文件列表"""
    need_translation = []  # 需要翻译的文件
    already_translated = []  # 已翻译的文件
    empty_files = []  # 空文件(之前翻译失败的)
    
    log_print("正在检查文件状态...")
    
    # 先收集所有源文件
    source_files = {}
    for root, dirs, files in os.walk(source_folder):
        for filename in files:
            if filename.endswith(".md"):
                source_file_path = os.path.join(root, filename)
                relative_path = get_relative_path_key(source_file_path, source_folder)
                source_files[relative_path] = source_file_path
    
    log_print(f"找到 {len(source_files)} 个源文件")
    
    # 检查目标文件是否存在
    for relative_path, source_file_path in source_files.items():
        target_file_path = os.path.join(target_folder, relative_path)
        
        if not os.path.exists(target_file_path):
            # 目标文件不存在，需要翻译
            need_translation.append(relative_path)
        else:
            # 目标文件存在，检查内容
            try:
                with open(target_file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if not content.strip():
                    # 空文件，需要重新翻译
                    empty_files.append(relative_path)
                    need_translation.append(relative_path)
                else:
                    # 已有内容，跳过翻译
                    already_translated.append(relative_path)
            except Exception as e:
                log_print(f"  读取文件 {target_file_path} 出错: {e}")
                need_translation.append(relative_path)
    
    log_print(f"文件检查结果:")
    log_print(f"总源文件: {len(source_files)}")
    log_print(f"需要翻译: {len(need_translation)}")
    log_print(f"已翻译(跳过): {len(already_translated)}")
    log_print(f"空文件(重新翻译): {len(empty_files)}")
    
    if need_translation:
        log_print(f"需要翻译的文件 (共 {len(need_translation)} 个)")
        if len(need_translation) <= 5:
            for file in need_translation:
                log_print(f"  - {file}")
        else:
            for file in need_translation[:3]:
                log_print(f"  - {file}")
            log_print(f"  ... 还有 {len(need_translation) - 3} 个文件")
    
    return need_translation


def check_large_files(source_folder, threshold=4000):
    """检查超过指定大小的文件"""
    large_files = []
    
    log_print(f"检查大文件 (>{threshold}字符)...")
    
    for root, dirs, files in os.walk(source_folder):
        for filename in files:
            if filename.endswith(".md"):
                file_path = os.path.join(root, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if len(content) > threshold:
                        relative_path = get_relative_path_key(file_path, source_folder)
                        large_files.append((relative_path, len(content)))
                except Exception as e:
                    log_print(f"读取文件 {file_path} 出错: {e}")
    
    if large_files:
        log_print(f"发现 {len(large_files)} 个大文件 (>{threshold}字符):")
        for i, (file_path, size) in enumerate(sorted(large_files, key=lambda x: x[1], reverse=True)):
            if i < 5:  # 只显示前5个最大的文件
                log_print(f"  - {file_path}: {size:,} 字符")
            elif i == 5:
                log_print(f"  ... 还有 {len(large_files) - 5} 个大文件")
                break
        log_print("这些文件将进行分段翻译")
    else:
        log_print("未发现大文件")
    
    return large_files


if __name__ == '__main__':
    '''
    1. 当你需要翻译文档SUMMARY.md文档时，请将修改is_summary=True, 其余文档则is_summary=False, 
    主要原因为翻译不同文档时的分割标准不同，如需定义自己的分割标准请修改 ’split_markdown_by_headers‘ 函数。
    2. 当你有特殊翻译要求时可以修改该文件起始的 'summary_input_text':翻译summary.md的要求, 'input_text':翻译其余文档的要求
    '''
    is_summary = False
    # 需要翻译的文档保存地址
    source_path = r"file"
    # 翻译后文档保存地址
    target_path = r'trans_res'

    log_print(f"开始处理:")
    log_print(f"源路径: {source_path}")
    log_print(f"目标路径: {target_path}")
    
    # 检查源路径是否存在
    if not os.path.exists(source_path):
        log_print(f"错误: 源路径不存在: {source_path}")
        exit(1)
    
    # 检查大文件
    large_files = check_large_files(source_path)
    
    # 检查现有翻译状况
    files_to_translate = check_files_exist(source_path, target_path)
    
    if not files_to_translate:
        log_print("所有文件都已翻译完成！")
    else:
        # 开始翻译
        process_all_md_files(source_path, target_path, files_to_translate, is_summary=is_summary)
