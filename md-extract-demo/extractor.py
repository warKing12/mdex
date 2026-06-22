#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Markdown Content Extractor
==========================

从分散的 Markdown 文件中按规则提取内容，支持：
- 跨目录文件引用解析
- 多层嵌套目录结构
- Mermaid 结构图解析
- 标题容错匹配

GitHub: https://github.com/your-username/md-extract
"""

# ============================================================================
#                           配 置 区
#                     （迁移使用时修改以下内容）
# ============================================================================

# 【必须配置】主入口文件路径
# 说明：这是包含文件引用的主 Markdown 文件
# 格式：可以是绝对路径或相对路径
# 示例：
#   SOURCE_FILE = 'source.md'                     # 相对路径（推荐）
#   SOURCE_FILE = 'D:/my-project/source.md'       # Windows 绝对路径
#   SOURCE_FILE = '/home/user/project/source.md'  # Linux/Mac 绝对路径
SOURCE_FILE = 'source.md'

# 【可选配置】项目根目录
# 说明：所有相对路径的基准目录
# 格式：设为 None 表示自动检测（使用 SOURCE_FILE 所在目录）
# 示例：
#   PROJECT_ROOT = None                           # 自动检测（推荐）
#   PROJECT_ROOT = 'D:/my-project'                # 手动指定
PROJECT_ROOT = None

# 【必须配置】模板文件路径
# 说明：定义提取规则的 YAML 文件
TEMPLATE_FILE = 'template.yaml'

# 【可选配置】输出模板文件路径
# 说明：定义输出格式的 Markdown 模板
# 格式：使用 {{字段名}} 作为占位符
OUTPUT_TEMPLATE_FILE = 'output-template.md'

# 【可选配置】输出文件名
OUTPUT_FILE = 'result.md'

# 【可选配置】诊断信息文件名
DIAGNOSTICS_FILE = 'diagnostics.json'

# 【可选配置】最大递归深度
# 说明：加载嵌套引用文件的最大深度，防止无限循环
MAX_RECURSION_DEPTH = 5

# ============================================================================
#                           核 心 代 码
#                              （无需修改）
# ============================================================================

import os
import re
import json
from pathlib import Path

# 自动检测项目根目录
if PROJECT_ROOT is None:
    _source_path = Path(SOURCE_FILE)
    if _source_path.is_absolute():
        PROJECT_ROOT = _source_path.parent
    else:
        PROJECT_ROOT = Path(__file__).parent
else:
    PROJECT_ROOT = Path(PROJECT_ROOT)

# 计算主入口文件的绝对路径
SOURCE_PATH = PROJECT_ROOT / SOURCE_FILE if not Path(SOURCE_FILE).is_absolute() else Path(SOURCE_FILE)


def normalize_markdown(text):
    """规范化 Markdown 文本"""
    if text.startswith('\ufeff'):
        text = text[1:]
    text = text.replace('\u00a0', ' ')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def normalize_heading(text):
    """规范化标题文本（用于匹配）"""
    result = text
    result = re.sub(r'^#{1,6}\s*', '', result)
    result = re.sub(r'^[一二三四五六七八九十百千万\d]+[.、)）]+', '', result)
    result = re.sub(r'[：:]+$', '', result)
    result = result.lower().strip()
    return result


def get_code_block_ranges(lines):
    """获取所有代码块的范围"""
    ranges = []
    in_block = False
    start = -1
    for i, line in enumerate(lines):
        if line.strip().startswith('```'):
            if not in_block:
                in_block = True
                start = i
            else:
                in_block = False
                ranges.append((start, i))
    if in_block:
        ranges.append((start, len(lines) - 1))
    return ranges


def is_in_code_block(line_index, code_block_ranges):
    """检查某行是否在代码块内"""
    for start, end in code_block_ranges:
        if start <= line_index <= end:
            return True
    return False


def get_heading_level(line):
    """获取标题层级"""
    match = re.match(r'^(#{1,6})\s', line)
    return len(match.group(1)) if match else 0


def get_heading_text(line):
    """获取标题文本"""
    return re.sub(r'^#{1,6}\s*', '', line).strip()


def match_heading(heading_text, patterns):
    """模糊匹配标题"""
    normalized = normalize_heading(heading_text)
    for pattern in patterns:
        pattern_clean = pattern.strip().strip('"').strip("'")
        normalized_pattern = normalize_heading(pattern_clean)
        if normalized_pattern in normalized or normalized in normalized_pattern:
            return True
    return False


def extract_section(lines, start_index, current_level, code_block_ranges):
    """提取章节内容"""
    content = []
    for i in range(start_index + 1, len(lines)):
        if is_in_code_block(i, code_block_ranges):
            continue
        line = lines[i]
        level = get_heading_level(line)
        if level > 0 and level <= current_level:
            break
        content.append(line)
    return '\n'.join(content).strip()


def parse_yaml(content):
    """简单的 YAML 解析器"""
    result = {}
    lines = content.split('\n')
    current_key = None
    for line in lines:
        line = line.rstrip()
        if not line or line.startswith('#'):
            continue
        match = re.match(r'^([^:]+):\s*$', line)
        if match:
            current_key = match.group(1).strip()
            result[current_key] = []
        elif current_key:
            arr_match = re.match(r'^\s+-\s+"([^"]*)"$', line)
            if arr_match:
                result[current_key].append(arr_match.group(1).strip())
            else:
                arr_match2 = re.match(r'^\s+-\s+(.+)$', line)
                if arr_match2:
                    result[current_key].append(arr_match2.group(1).strip())
    return result


def parse_file_references(content):
    """解析文件引用"""
    references = []
    patterns = [
        r'\[([^\]]+\.md)\]',
        r'详见附件：([^\s\[]+\.md)',
        r'详见：([^\s\[]+\.md)',
        r'见：([^\s\[]+\.md)',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, content)
        references.extend(matches)
    return list(set(references))


def resolve_file_path(ref, base_path, root_path):
    """解析引用文件的绝对路径"""
    ref = ref.strip().replace('\\', '/')
    if ref.startswith('../'):
        file_path = (base_path / ref).resolve()
    elif ref.startswith('./'):
        file_path = (base_path / ref.lstrip('./')).resolve()
    elif ref.startswith('/') or (len(ref) > 1 and ref[1] == ':'):
        file_path = Path(ref)
    else:
        candidate1 = (base_path / ref).resolve()
        candidate2 = (root_path / ref).resolve()
        file_path = candidate1 if candidate1.exists() else candidate2
    return file_path


def load_file_content(ref, base_path, root_path):
    """加载引用文件的内容"""
    file_path = resolve_file_path(ref, base_path, root_path)
    if file_path.exists():
        try:
            return file_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f'警告: 无法读取文件 {file_path}: {e}')
            return None
    return None


def load_all_files_recursive(source_content, base_path, root_path, visited=None, depth=0, max_depth=None):
    """递归加载所有引用的文件"""
    if max_depth is None:
        max_depth = MAX_RECURSION_DEPTH
    if visited is None:
        visited = set()
    all_contents = {}
    if depth >= max_depth:
        return all_contents
    references = parse_file_references(source_content)
    for ref in references:
        ref_normalized = ref.replace('\\', '/').lower()
        if ref_normalized in visited:
            continue
        visited.add(ref_normalized)
        content = load_file_content(ref, base_path, root_path)
        if content:
            content = normalize_markdown(content)
            all_contents[ref] = content
            new_file_path = resolve_file_path(ref, base_path, root_path)
            new_base_path = new_file_path.parent
            sub_contents = load_all_files_recursive(
                content, new_base_path, root_path, visited, depth + 1, max_depth
            )
            all_contents.update(sub_contents)
    return all_contents


def parse_mermaid_graph(mermaid_code):
    """解析 Mermaid 图形代码"""
    result = {'type': 'unknown', 'nodes': [], 'edges': [], 'description': ''}
    if not mermaid_code:
        return result
    lines = mermaid_code.strip().split('\n')
    if not lines:
        return result
    first_line = lines[0].strip()
    if 'graph' in first_line or 'flowchart' in first_line:
        result['type'] = 'flowchart'
    elif 'gantt' in first_line:
        result['type'] = 'gantt'
        return result
    node_patterns = [
        r'([A-Za-z\d\u4e00-\u9fa5_]+)\s*\[([^\]]+)\]',
        r'([A-Za-z\d\u4e00-\u9fa5_]+)\s*\(([^\)]+)\)',
    ]
    edge_patterns = [
        (r'([A-Za-z\d\u4e00-\u9fa5_]+)\s*-->\s*([A-Za-z\d\u4e00-\u9fa5_]+)', 'depends_on'),
        (r'([A-Za-z\d\u4e00-\u9fa5_]+)\s*---([A-Za-z\d\u4e00-\u9fa5_]+)', 'connects'),
    ]
    for line in lines[1:]:
        line = line.strip()
        if not line or line.startswith('title') or line.startswith('style'):
            continue
        for pattern in node_patterns:
            match = re.search(pattern, line)
            if match:
                node_id, node_label = match.group(1), match.group(2)
                if node_id not in [n['id'] for n in result['nodes']]:
                    result['nodes'].append({'id': node_id, 'label': node_label})
        for edge_pattern, relation_type in edge_patterns:
            match = re.search(edge_pattern, line)
            if match:
                result['edges'].append({'from': match.group(1), 'to': match.group(2), 'type': relation_type})
    result['description'] = generate_graph_description(result)
    return result


def generate_graph_description(graph):
    """生成图形的自然语言描述"""
    if not graph['nodes'] and not graph['edges']:
        return ''
    desc_parts = []
    if graph['nodes']:
        if len(graph['nodes']) <= 5:
            node_names = '、'.join([n['label'] for n in graph['nodes']])
            desc_parts.append(f'包含 {len(graph["nodes"])} 个组件：{node_names}')
        else:
            in_degree = {n['id']: 0 for n in graph['nodes']}
            out_degree = {n['id']: 0 for n in graph['nodes']}
            for edge in graph['edges']:
                out_degree[edge['from']] = out_degree.get(edge['from'], 0) + 1
                in_degree[edge['to']] = in_degree.get(edge['to'], 0) + 1
            roots = [n['label'] for n in graph['nodes'] if in_degree.get(n['id'], 0) == 0]
            leaves = [n['label'] for n in graph['nodes'] if out_degree.get(n['id'], 0) == 0]
            if roots:
                desc_parts.append(f'顶层：{"、".join(roots[:3])}')
            if leaves:
                desc_parts.append(f'底层：{"、".join(leaves[:3])}')
    if graph['edges']:
        desc_parts.append(f'包含 {len(graph["edges"])} 条关系')
    return '；'.join(desc_parts)


def extract_mermaid_from_content(content):
    """从内容中提取 Mermaid 代码块"""
    mermaid_blocks = []
    lines = content.split('\n')
    in_block = False
    current_block = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            if not in_block:
                if 'mermaid' in stripped:
                    in_block = True
                    current_block = []
            else:
                if current_block:
                    mermaid_blocks.append('\n'.join(current_block))
                in_block = False
                current_block = []
        elif in_block:
            current_block.append(line)
    return mermaid_blocks


def understand_mermaid_as_text(mermaid_code):
    """将 Mermaid 转换为自然语言"""
    graph = parse_mermaid_graph(mermaid_code)
    if not graph['nodes'] and not graph['edges']:
        return ''
    descriptions = []
    type_desc = {'flowchart': '采用层次结构', 'gantt': '甘特图'}
    if graph['type'] in type_desc:
        descriptions.append(type_desc[graph['type']])
    if graph.get('description'):
        descriptions.append(graph['description'])
    return ' '.join(descriptions)


def extract_from_scattered_files(source_content, template, base_path, root_path):
    """从分散的文件中提取内容"""
    all_files = load_all_files_recursive(source_content, base_path, root_path)
    result = {}
    for field_name, patterns in template.items():
        matched_contents = []
        for file_path, content in all_files.items():
            lines = content.split('\n')
            code_block_ranges = get_code_block_ranges(lines)
            for i, line in enumerate(lines):
                if is_in_code_block(i, code_block_ranges):
                    continue
                level = get_heading_level(line)
                if level == 0:
                    continue
                heading_text = get_heading_text(line)
                if match_heading(heading_text, patterns):
                    section_content = extract_section(lines, i, level, code_block_ranges)
                    mermaid_blocks = extract_mermaid_from_content(section_content)
                    if mermaid_blocks:
                        mermaid_desc = [understand_mermaid_as_text(b) for b in mermaid_blocks if understand_mermaid_as_text(b)]
                        if mermaid_desc:
                            section_content = section_content + '\n\n【结构图解读】' + ' '.join(mermaid_desc)
                    matched_contents.append({'file': file_path, 'heading': heading_text, 'content': section_content})
                    break
        if matched_contents:
            combined = ['【来源：{}】\n{}'.format(item['file'], item['content']) for item in matched_contents]
            result[field_name] = '\n\n---\n\n'.join(combined)
        else:
            result[field_name] = ''
    return result, all_files


def fill_template(template_content, data):
    """填充输出模板"""
    result = template_content
    for key, value in data.items():
        placeholder = '{{' + key + '}}'
        result = result.replace(placeholder, value.replace('\n', '<br>') if value else '')
    return result


def get_diagnostics(source_content, template, extracted_data, all_files, root_path):
    """生成诊断信息"""
    diagnostics = {
        'template': template,
        'rootPath': str(root_path),
        'filesLoaded': list(all_files.keys()),
        'fileCount': len(all_files),
        'extractedFields': list(extracted_data.keys()),
        'extractionStatus': {k: 'success' if v else 'not_found' for k, v in extracted_data.items()},
        'timestamp': __import__('datetime').datetime.utcnow().isoformat()
    }
    total_mermaid = 0
    for file_path, content in all_files.items():
        blocks = extract_mermaid_from_content(content)
        if blocks:
            total_mermaid += len(blocks)
    diagnostics['totalMermaidDiagrams'] = total_mermaid
    return diagnostics


def main():
    """主函数"""
    print('=' * 70)
    print('Markdown Content Extractor')
    print('=' * 70)
    print()

    # 检查文件是否存在
    if not SOURCE_PATH.exists():
        print(f'错误: 主入口文件不存在: {SOURCE_PATH}')
        print('请检查配置区的 SOURCE_FILE 设置')
        return None, False

    template_path = PROJECT_ROOT / TEMPLATE_FILE
    if not template_path.exists():
        print(f'错误: 模板文件不存在: {template_path}')
        print('请检查配置区的 TEMPLATE_FILE 设置')
        return None, False

    # 读取主入口文件
    print('1. 读取主入口文件...')
    source_content = SOURCE_PATH.read_text(encoding='utf-8')
    source_content = normalize_markdown(source_content)
    base_path = SOURCE_PATH.parent
    print(f'   主入口: {SOURCE_PATH}')
    print(f'   根目录: {PROJECT_ROOT}')

    # 读取模板
    print('\n2. 读取模板...')
    template_content = template_path.read_text(encoding='utf-8')
    template = parse_yaml(template_content)
    print(f'   提取字段: {", ".join(template.keys())}')

    # 读取输出模板
    print('\n3. 读取输出模板...')
    output_template_path = PROJECT_ROOT / OUTPUT_TEMPLATE_FILE
    if output_template_path.exists():
        output_template = output_template_path.read_text(encoding='utf-8')
    else:
        output_template = '# 提取结果\n\n'
        for field in template.keys():
            output_template += f'## {field}\n\n{{{{{field}}}}}\n\n---\n\n'
        print(f'   未找到输出模板，使用默认格式')

    # 加载引用文件
    print('\n4. 加载引用文件...')
    all_files = load_all_files_recursive(source_content, base_path, PROJECT_ROOT)
    print(f'   已加载 {len(all_files)} 个文件')

    # 提取内容
    print('\n5. 提取内容...')
    extracted_data, all_files = extract_from_scattered_files(source_content, template, base_path, PROJECT_ROOT)

    print('\n提取结果:')
    for key, value in extracted_data.items():
        if value:
            preview = value[:80].replace('\n', ' ')
            print(f'   {key}: {preview}... ({len(value)} 字符)')
        else:
            print(f'   {key}: (未找到)')

    # 生成输出
    print('\n6. 生成输出文件...')
    result_content = fill_template(output_template, extracted_data)
    result_path = PROJECT_ROOT / OUTPUT_FILE
    result_path.write_text(result_content, encoding='utf-8')
    print(f'   结果文件: {result_path}')

    diagnostics = get_diagnostics(source_content, template, extracted_data, all_files, PROJECT_ROOT)
    diagnostics_path = PROJECT_ROOT / DIAGNOSTICS_FILE
    diagnostics_path.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'   诊断文件: {diagnostics_path}')

    # 完成
    print('\n' + '=' * 70)
    all_found = all(v for v in extracted_data.values())
    print(f'状态: {"全部字段提取成功 ✓" if all_found else "部分字段未找到"}')
    print('=' * 70)

    return extracted_data, all_found


if __name__ == '__main__':
    main()