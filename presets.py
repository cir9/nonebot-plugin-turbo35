

import json
import re
from collections import defaultdict

public_preset_personalities = {}
users_preset_personalities = {}

user_preset_ids = []
preset_indices = defaultdict(lambda: [])

file_path = './src/plugins/chatgpt/'

regex_preset_names: re

def alias_str(preset, name=None):
    alias = preset["alias"]
    if name is not None:
        alias = [name] + alias
     
    return f'({",".join(alias)})' if len(alias) > 0 else ""

def contains_presets(chat):
    match_preset_name = regex_preset_names.search(chat)
    return match_preset_name is not None

def save_preset(user_id, preset_names: list, messages: list):
    if user_id not in users_preset_personalities.keys():
        users_preset_personalities[user_id] = {}
    
    preset_names = list({ x.lower() for x in preset_names })
    user_presets = users_preset_personalities[user_id]
    user_presets[preset_names[0]] = {
        "alias": list(preset_names[1:]),
        "messages": list(messages),
    }
    save_preset_jsons()
    compile_preset_indices()
    
def delete_preset(user_id, preset_names: str):
    if user_id not in users_preset_personalities.keys():
        return 404
    user_presets = users_preset_personalities[user_id] 
    if preset_names not in user_presets.keys():
        return 404
    
    user_presets.pop(preset_names)
    save_preset_jsons()
    compile_preset_indices()
    
    return 200
        
def get_preset_list(user_id):
    return {
        "public": [k + alias_str(v) for k,v in public_preset_personalities.items()],
        "users": user_preset_ids,
        "own": [k + alias_str(v) for k,v in users_preset_personalities[user_id].items()] if user_id in users_preset_personalities else []
    }
    
def load_preset_from_preset_id(creator_id, preset_name):
    try:
        if creator_id == '0':
            return {"status": 200, "creator_id": creator_id, "name": preset_name, "preset": public_preset_personalities[preset_name]}
        return {"status": 200, "creator_id": creator_id, "name": preset_name, "preset": users_preset_personalities[creator_id][preset_name]}
    except Exception as e:
        return {"status": 404}

def load_preset(user_id, preset_id):
    seps = preset_id.split("#")
    
    if len(seps) == 2:
        return load_preset_from_preset_id(seps[1], seps[0])
    
    name = seps[0]
    suggestions = [alias.split("#") for alias in preset_indices[name]]
    if len(suggestions) == 0:
        return {"status": 404}
    
    user_s = [x for x in suggestions if x[1] == user_id]
    if len(user_s) > 1:
        return {"status": 301, "suggestions": [f'{pair[0]}#{pair[1]}' for pair in user_s]}
    elif len(user_s) == 1:
        return load_preset_from_preset_id(user_s[0][1], user_s[0][0])
    
    publics = [x for x in suggestions if x[1] == '0']
    if len(publics) > 0:
        return load_preset_from_preset_id('0', publics[0][0])
    
    others_s = suggestions
    if len(others_s) > 1:
        return {"status": 301, "suggestions": [f'{pair[0]}#{pair[1]}' for pair in others_s]}
    elif len(others_s) == 1:
        return load_preset_from_preset_id(others_s[0][1], others_s[0][0])
    
regex_escape = re.compile(r'([\\\.^$\(\)\[\]*+?.{}|-])')

def compile_preset_indices():
    global regex_preset_names
    
    preset_indices.clear()
    user_preset_ids.clear()
    
    for name, data in public_preset_personalities.items():
        preset_id = f'{name}#0'
        preset_indices[name].append(preset_id)
        for alias in data["alias"]:
            preset_indices[alias].append(preset_id)

    for user_id, preset in users_preset_personalities.items():
        for name, data in preset.items():
            preset_id = f'{name}#{user_id}'
            
            preset_indices[name].append(preset_id)
            for alias in data["alias"]:
                preset_indices[alias].append(preset_id)
              
    
    for user_id, preset in users_preset_personalities.items():
        for name, data in preset.items():
            if len(preset_indices[name]) > 1:
                user_preset_ids.append(f'{name}#{user_id}' + alias_str(data, name))
            else:
                user_preset_ids.append(name + alias_str(data))

    namelist = list(preset_indices.keys())
    namelist.sort(key=lambda x:len(x), reverse=True)
    escaped_namelist = "|".join((regex_escape.sub(r'\\\1', x) for x in namelist))
    regex_raw = f'^({escaped_namelist})([\w\W]*)$'
    print(regex_raw)
    regex_preset_names = re.compile(regex_raw, flags=re.IGNORECASE)
    print(f'Recompiled preset regex and indices: [{", ".join(preset_indices.keys())}]')

def load_preset_jsons():
    global public_preset_personalities
    global users_preset_personalities
    
    with open(file_path + 'presets_public.json', 'r', encoding='utf-8') as f:
        public_preset_personalities = dict(json.load(f))
        
    with open(file_path + 'presets_user.json', 'r', encoding='utf-8') as f:
        users_preset_personalities = dict(json.load(f))
    
def save_preset_jsons(): 
    with open(file_path + 'presets_user.json', 'w', encoding='UTF-8') as f:
        json.dump(users_preset_personalities, f, ensure_ascii=False)

def init():
    load_preset_jsons()
    compile_preset_indices()
