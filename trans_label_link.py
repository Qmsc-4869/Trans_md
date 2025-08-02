import re
import os

def read_file_content(file_path, encoding='utf-8'):
    try:
        with open(file_path, 'r', encoding=encoding) as file:
            content = file.readlines()
        return content
    except Exception as e:
        print(f'Error reading file: {e}')
        return None
    

def label_list(md_path):
    
    md_context = read_file_content(md_path)
    
    pattern = r'^#+ (.+)'
    label_list_ = []

    for line in md_context:
        line: str = line.strip()

        match = re.match(pattern, line)
        if line != '' and match:
            label_list_.append(match.group(1))
    
    return label_list_


def trans_label(en: str):
    en = en.strip().lower()
    return '-'.join(en.split(' '))


def get_label_dict(path_en, path_zh):
    label_en = label_list(path_en)
    label_zh = label_list(path_zh)
    if len(label_en) == len(label_zh):
        return {trans_label(en): zh for en, zh in zip(label_list(path_en), label_list(path_zh))}
    else:
        print('en:', len(label_en))
        print('zh:', len(label_zh))
        print(path_zh.replace("zh_nr", "zh", 1))
        raise
    

def replace_label_with_map(text, pattern, replacement_map):

    def replacer(match):
        en = match.group(1)
        zh = replacement_map.get(en, en)
        return match.group(0).replace(en, zh)

    return re.sub(pattern, replacer, text)


def replace_label_link(path_en, path_zh):
    save_path = path_zh.replace("zh_nr", "zh", 1)
    src_dict = get_label_dict(path_en, path_zh)
    pattern = r'(?:\[.+?\])\(#+(.+?)\)'

    with open(path_zh, 'r', encoding='utf-8') as file:
            context = file.read()
            replace_context = replace_label_with_map(context, pattern, src_dict)
            
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'w+', encoding='utf-8') as file:
                file.write(replace_context)


def get_all_file_paths(folder_name):
    file_paths = []
    
    for root, dirs, files in os.walk(folder_name):
        for file in files:
            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, start=os.getcwd())  # 相对路径
            file_paths.append(relative_path)
    
    return file_paths


if __name__ == '__main__':
    for path_en, path_zh in zip(get_all_file_paths('en'), get_all_file_paths('zh_nr')):
        replace_label_link(path_en, path_zh)