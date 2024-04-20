#!/usr/bin/env python3
import os, subprocess
from ..lib import utils, doc_utils

'''
get per-class-of-function infomation in source of (Linux manual) of libc
    - NAME/SYNOPSIS/DESCRIPTION/RETURN VALUE/NOTES/BUGS
It is similar to the handling for openssl in some way.
TODO: unify the processing as one file?
concern: may have some absent situations.
'''

def doc2text(doc_dir, doc_type):
    doc_files = []
    if doc_type == 'glibc':
        sub_dir = "glibc/share/man/man3"
        extension = '.3'
        command = 'man'
    elif doc_type == 'openssl':
        sub_dir = "openssl"
        extension = '.pod'
        command = 'pod2text'
    else:
        raise ValueError("Unsupported documentation type.")

    doc_path = os.path.join(doc_dir, sub_dir)
    if not os.path.exists(doc_path):
        return []
    
    for dirpath, _, files in os.walk(doc_path):
        for file in files:
            if file.endswith(extension) and not file.endswith('.txt'):
                cur_file = os.path.join(dirpath, file)
                txt_file = cur_file + '.txt'
                if not os.path.exists(txt_file):
                    if command == 'man':
                        cmd = [command, cur_file]
                        with open(txt_file, "w") as f:
                            ret = subprocess.run(cmd, stdout=f)
                            if ret.returncode != 0:
                                raise Exception(f"Failure during running `{command}` for file: {cur_file}")
                    elif command == 'pod2text':
                        cmd = [command, cur_file, txt_file]
                        ret = subprocess.run(cmd, stderr=subprocess.STDOUT)
                        if ret.returncode != 0:
                            raise Exception(f"Failure during running `{command}` for file: {cur_file}")
                doc_files.append(txt_file)
    return doc_files

def update_desc_glibc(content, desc, definitions, content_type):
    # clean text
    content = doc_utils.clean_text(content)
    for para in content.split("\n\n"):
        for key in definitions.keys():
            if key + "()" in para:
                para = para.replace('‐\n', '')
                para = para.replace('\n', ' ')
                if key not in desc:
                    desc[key] = definitions[key]
                    desc[key][content_type] = para
                elif content_type in desc[key]:
                    desc[key][content_type] += '\n' + para
                else:
                    desc[key][content_type] = para
    return desc

def update_desc_openssl(desc, func_name, func_def, para, content_type, expand = None):
    content = para.replace('\n', ' ') if expand == None else \
                    para.replace('\n', ' ').replace("*TYPE*", expand).replace("TYPE", expand)
    if func_name not in desc:
        desc[func_name] = func_def
        desc[func_name][content_type] = content
    elif content_type in desc[func_name]:
        desc[func_name][content_type] += '\n' + content
    else:
        desc[func_name][content_type] = content
    return desc

def get_desc(content, desc, definitions, content_type, expand_def = {}):
    # clean text
    content = doc_utils.clean_text(content)
    for para in content.split("\n\n"):
        if expand_def == {}:
            for func_name in definitions.keys():
                if func_name + "()" in para:
                    func_def = definitions[func_name]
                    desc = update_desc_openssl(desc, func_name, func_def, para, content_type)
        else:
            for def_name in expand_def:
                pre_pos = def_name.index('_TYPE_')
                post_pos = pre_pos + 6
                prefix = def_name[:pre_pos] + "_" if def_name[:pre_pos] != "" else ""
                postfix = "_" + def_name[post_pos:] if def_name[post_pos:] != "" else ""
                if prefix + "*TYPE*" + postfix + "()" in para:
                    for func in expand_def[def_name]:
                        core_pre_pos = len(prefix)
                        core_post_pos = -len(postfix) if len(postfix) != 0 else len(func)
                        core_name = func[core_pre_pos:core_post_pos]
                        func_def = definitions[func]
                        desc = update_desc_openssl(desc, func, func_def, para, content_type, core_name)
    return desc

''' load all the content of a doc file for subsequent processing '''
def load_doc_content(doc_file):
    contents = {}
    cur_item = ""
    doc_lines = doc_utils.read_docfile(doc_file)
    for line in doc_lines:
        if len(line) > 1 and line[0] != " ":
            cur_item = line[:-1]
            contents[cur_item] = ""
            continue
        if cur_item != "":
            if line[0] == '\n':
                contents[cur_item] += '\n'
            else:
                # drop the useless indent
                contents[cur_item] += doc_utils.rm_useless_space(line, end=False)
    return contents


''' split each API from each class of documentation '''
def split_api_glibc(doc_file):
    names = []
    definitions = {}
    descriptions = {}
    contents = load_doc_content(doc_file)
    # 1. acquire API's names
    if 'NAME' not in contents:
        return [], {}
    # 2. acquire each API's definition
    if 'SYNOPSIS' not in contents:
        return [], {}
    for synopsis in contents['SYNOPSIS'].split(';\n'):
        # outdated: [type, func_name, arg1, arg2, ..., argn]
        # now: {"func_name": .., "func_type": .., "args_name": .., "args_type": ..}
        definition = doc_utils.get_definition(synopsis)
        if definition['func_name'] == '':
            continue
        if definition['func_name'] not in names:
            names.append(definition['func_name'])
        else:
            continue
        definitions[definition['func_name']] = definition
    # 3. acquire each API's description
    ''' For simplicity, now only concern: 'DESCRIPTION', 'RETURN VALUES'... '''
    if 'DESCRIPTION' in contents:
        descriptions = update_desc_glibc(contents['DESCRIPTION'], descriptions, definitions, "desc")
    if 'RETURN VALUES' in contents:
        descriptions = update_desc_glibc(contents['RETURN VALUES'], descriptions, definitions, "ret_desc")
    if 'RETURN VALUE' in contents:
        descriptions = update_desc_glibc(contents['RETURN VALUE'], descriptions, definitions, "ret_desc")
    return names, descriptions

def split_api_openssl(doc_file):
    expand_def = {}
    names = []
    definitions = {}
    descriptions = {}
    contents = load_doc_content(doc_file)
    # 1. acquire API's names
    if 'NAME' not in contents:
        return [], {}
    names = contents['NAME'].replace('\n', ' ').split(', ')
    if len(names) == 0:
        return [], {}
    if ' ' in names[-1]:
        names[-1] = names[-1].split(' ')[0]
    for i in range(len(names)):
        names[i] = doc_utils.rm_useless_space(names[i])
        if "- " in names[i]:
            names[i] = names[i].replace("- ", "")
    # 2. acquire each API's definition
    if 'SYNOPSIS' not in contents:
        return [], {}
    for synopsis in contents['SYNOPSIS'].split(';\n'):
        # outdated: [type, func_name, arg1, arg2, ..., argn]
        # now: {"func_name": .., "func_type": .., "args_name": .., "args_type": ..}
        definition = doc_utils.get_definition(synopsis)
        func_name = definition['func_name']
        if func_name == '':
            continue
        if func_name not in names:
            pre_pos = 0
            post_pos = len(func_name)
            if "_TYPE_" in func_name:
                pre_pos = func_name.index('_TYPE_')
                post_pos = pre_pos + 6
            elif "TYPE_" in func_name:
                post_pos = 5
            elif "_TYPE" in func_name:
                pre_pos = len(func_name) - 5
            else:
                continue
            prefix = func_name[:pre_pos]
            postfix = func_name[post_pos:]
            expand_def[prefix + "_TYPE_" + postfix] = []
            for name in names:
                name_pre = name[:pre_pos]
                name_post = name[-len(postfix):] if len(postfix) != 0 else ""
                if name_pre == prefix and name_post == postfix:
                    expand_def[prefix + "_TYPE_" + postfix].append(name)
                    new_def = definition.copy()
                    new_def['func_name'] = name
                    definitions[name] = new_def
            # Or meaning that the previous analysis is not COMPLETE?
        else:
            definitions[func_name] = definition
    # 3. acquire each API's description
    ''' For simplicity, now only concern: 'DESCRIPTION', 'RETURN VALUES' '''
    if 'DESCRIPTION' in contents:
        descriptions = get_desc(contents['DESCRIPTION'], descriptions, definitions, "desc", expand_def)
    if 'RETURN VALUES' in contents:
        descriptions = get_desc(contents['RETURN VALUES'], descriptions, definitions, "ret_desc", expand_def)
    return names, descriptions

# doc_dir - the storage directory of data
def handle(doc_dir, outdir, doc_type):
    print("==================================================")
    print(f"====         Preprocessing {doc_type} info        =====")
    ''' initialization '''
    preprocess_dir = os.path.join(outdir, "glibc")
    utils.mkdir(preprocess_dir)
    doc_files = doc2text(doc_dir, doc_type)
    ''' preprocess documentation '''
    total_apis = []
    analyzed_apis = []
    for doc_file in doc_files:
        if doc_type == 'glibc':
            cur_apis, descriptions = split_api_glibc(doc_file)
        elif doc_type == 'openssl':
            cur_apis, descriptions = split_api_openssl(doc_file)
        total_apis += cur_apis
        for func_name in descriptions:
            if func_name not in analyzed_apis:
                analyzed_apis.append(func_name)
                func_feature_file = os.path.join(preprocess_dir, f"{func_name}.json")
                doc_utils.dump_json(func_feature_file, descriptions[func_name])

    print(f"Total number of functions: {len(set(total_apis))}")
    print(f"Success number of functions: {len(analyzed_apis)}")
    print("==================================================")

    return list(set(total_apis))
