import websockets
import json
import nonebot
import re
import random
import src.plugins.chatgpt.presets as presets
from typing import Optional, Callable
from collections import defaultdict
from nonebot import on_message, on_command, logger
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot,MessageSegment,MessageEvent,GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.adapters import Message
from nonebot.params import Arg, CommandArg, ArgPlainText

def strbool(str: str): 
    str = str.strip()
    return str.lower() == 'true' or str == '1'

def strfloat(str):
    return float(str)

new_line = "\n"


uri = "Your own ws proxy server"

presets.init()

member_messages_tokens = defaultdict(lambda: 0)
member_messages = defaultdict(lambda: [])
last_response_user_id = ''

def set_preset_messages(sender_id, preset):
    messages = list(preset["messages"])
    member_messages[sender_id] = messages

def add_response(sender_id, message):
    messages = member_messages[sender_id]
    
    if len(message['content']) > 0: 
        messages.append(message)
        
    if len(messages) > extra_params["max_message_count"]["value"]:
        preserve = extra_params["preserve_message_count"]["value"]
        max = extra_params["max_message_count"]["value"] 
        start = len(messages) - max + preserve
        
        messages = list([messages[0:preserve]] + messages[start:])
        member_messages[sender_id] = messages
 
    return messages
    #return [{"role": m["role"], "content": m["content"]} for m in messages]

def manual_add_response(sender_id, role, content):
    messages = member_messages[sender_id]
    add_response(sender_id, {"role": role, "content": content})

def manual_delete_response(sender_id, count):
    messages = member_messages[sender_id]
    messages = list(messages[:len(messages)-count])
    member_messages[sender_id] = messages

def clear_message(sender_id):
    member_messages[sender_id].clear()
        


head = {
    'max_tokens': 1024,
}


async def proxy(user_id, chat, role='user'):
    global last_response_user_id
    
    data = {
        'head': head,
        'body': add_response(user_id, {"role": role, "content": chat})
    }
    async with websockets.connect(uri) as websocket:
        
        
        
        await websocket.send(json.dumps(data))
        print(f">>> {chat}")

        response = json.loads(await websocket.recv())
        message = response['choices'][0]['message']
        print(f"<<< {message}")
        add_response(user_id, message)
        
        last_response_user_id = user_id
    
    res = f'[{response["usage"]["total_tokens"]}]\n' if extra_params["show_token_count"]["value"] else ''
    res += message['content'].strip('\n')
    return res




role_map = {
    'system': '',
    'user' : '用户: ',
    'assistant': 'ChatGPT: ' 
}

def get_messages_str(messages):
    return '\n\n'.join(map(lambda x: 
        f'{role_map[x["role"]]}{x["content"].strip()}'
    , messages))
    
def get_user_messages(user_id):
    return f'当前你的对话记录如下：({len(member_messages[user_id])}/{extra_params["max_message_count"]["value"]})\n\n' + \
            get_messages_str(member_messages[user_id])

log=on_command("#log",aliases={"#l"},priority=2)
@log.handle()
async def log_func(event: MessageEvent,match: Matcher, args: Message=CommandArg()):
    try:
        user_id = event.get_user_id()
        tosend = get_user_messages(user_id)
        
        await log.send(message=tosend, at_sender=True)
    except Exception as e:
        tosend=f"[ERROR] {str(e)}"
        await log.send(message=tosend)

help_text='\n'.join([
    'ChatGPT bot的使用方式：',
    '- 通过"gpt"或是预置人格名（如:"glados"）开头: 发起新的个人对话',
    '- 通过"so"或"##"开头: 继续之前的个人对话',
    '- 通过 @机器人 可以回复最近一条AI对其他群友的回复',
    '\n编辑对话方式：',
    '- 通过"gpt!"(这会刷新对话),或"##!"来设定指示，以指导ChatGPT认清自己身份，可用于控制ChatGPT的行为。',
    '- 通过"gpt:"(这会刷新对话),或"##:"来设定ChatGPT回复的对话，可用于控制ChatGPT的聊天风格。',
    '- 通过"gpt="(这会刷新对话),或"##="来设定你的对话。',
    '- 通过"##-n" 来删除之前的 n 条对话',
    '（以上4条不会直接得到ChatGPT的回复）',
    '- 仅发送"##"，或是"##<对话>"都可以获得ChatGPT接下来的回应',
    '\n一些常用命令：',
    '- #log (#l): 查看自己与ChatGPT当前的对话记录',
    '- #preset (#p): 列出所有预置的AI人格，或是对个人的预置人格进行操作',
    '- #clear: 强制清空所有人的ChatGPT的当前对话历史',
    '- #params: 查询现在ChatGPT的参数',
    '- #set <参数名> <参数>: 修改ChatGPT的参数',
    '- #help (#?): 展示这段帮助文字',
])


extra_params = {
    'show_token_count': {
        'value': True,
        'parse': strbool,
        'hint': 'token消耗显示'
    },
    'preserve_message_count': {
        'value': 1,
        'parse': strfloat,
        'hint': '指导对话保留条数'
    },
    'max_message_count': {
        'value': 64,
        'parse': strfloat,
        'hint': '对话条数上限'
    }
}


help=on_command("#help",aliases={"#?", "#？"},priority=2)
@help.handle()
async def help_func(match: Matcher, args: Message=CommandArg()):
    try:
        await help.send(message=help_text)
    except Exception as e:
        tosend=f"[ERROR] {str(e)}"
        await help.send(message=tosend)

    
set_param=on_command("#set ",aliases={},priority=2)
@set_param.handle()
async def set_param_func(match: Matcher, args: Message=CommandArg()):
    
    txt_content=args.extract_plain_text().strip(' ')
    args=txt_content.split(' ')
    
    try:
        param_name = args[0]
        value_str = args[1]
        if args[0] in extra_params.keys():
            param = extra_params[param_name]
            value = param["parse"](value_str)
            param["value"] = value
            tosend=f'已将ChatGPT的 {param["hint"]} 修改为 {value}'
        else:
            head[param_name] = float(value_str)
            tosend=f'已将ChatGPT的 {args[0]} 参数修改为 {float(args[1])}'
        
        tosend += "\n\n当前ChatGPT的参数如下:\n" + get_all_params()
        await set_param.send(message=tosend)
    except Exception as e:
        tosend=f"[ERROR] {str(e)}"
        await set_param.send(message=tosend)


def get_all_params():
    val = f'{new_line.join([k + ": " + str(v["value"]) for k,v in extra_params.items()])}\nhead={json.dumps(head)}'
    # print(val)
    return val

param=on_command("#params",aliases={"#param"},priority=2)
@param.handle()
async def print_param_func(match: Matcher, args: Message=CommandArg()):
    try:
        tosend= "当前ChatGPT的参数如下: \n" + get_all_params()
        await param.send(message=tosend)
    except Exception as e:
        tosend=f"[ERROR] {str(e)}"
        await param.send(message=tosend)
       
       
def find_preset(user_id, preset_name):
    preset_data = presets.load_preset(user_id, preset_name)
    status = preset_data["status"]
    
    if status == 404:
        return None, f'找不到预置人格 {preset_name}'
    if status == 301:
        return None, f'存在歧义，请指定预置人格：{", ".join(preset_data["suggestions"])}'
    
    creator_id = preset_data["creator_id"]
    if creator_id == user_id:
        return preset_data, "[你的预置人格] "
    elif creator_id != '0':
        return preset_data, f"[他人的预置人格] " 
    return preset_data, ''
        
preset_help_text = '\n'.join([
    "预置人格的操作方式：",
    "- #preset log <预置人格名>: 查看该预置人格所使用的对话记录。可以查看他人的预置人格记录", 
    "- #preset load <预置人格名>: 将该预置人格应用到你当前的对话记录中。可以使用他人的预置人格记录",
    "- #preset save <预置人格名>: 将你当前的对话记录保存为<预置人格名>。开头输入该名称可直接召唤该预置人格",
    "- #preset save <预置人格名> <别称1> ... : 将你当前的对话记录保存为<预置人格名>，且设定其他别称，每次保存都需要重新输入别称。开头输入别称也可召唤该预置人格", 
    '⚠ "#preset save" 会覆盖原有记录，不可撤销。请在保存时输入 #log 确认你当前的对话记录', 
    "- #preset delete <预置人格名>: 删除你个人的该预置人格", 
    '⚠ "#preset delete" 没有确认删除的步骤，将会直接删除预置人格，不可撤销', 
    "\n关于预置人格名：",
    "- 在使用 <预置人格名> 召唤预置人格时，首先会寻找你个人是否拥有该预置人格，然后寻找公共预置人格，最后寻找他人的预置人格。会召唤第一个找到的预置人格", 
    "- 如果只使用 <预置人格名> 可能存在歧义时，可以通过 <预置人格名#作者QQ号> 的形式指定特定的预置人格", 
    "\n预置人格的相关命令：",
    "- #preset list, #preset: 列出所有预置人格", 
    "- #preset help, #preset ?: 显示这条预置人格的帮助", 
    '- 所有 #preset 命令都可以简写成 #p (如 "#p?" 可以显示这条帮助)'
])
    
preset_e=on_command("#presets", aliases={"#preset", "#p"},priority=2)
@preset_e.handle()
async def presets_func(event: MessageEvent,match: Matcher, args: Message=CommandArg()):
    try:
        txt_content=args.extract_plain_text().strip()
        args = [x.lower() for x in txt_content.split()]
        user_id = event.get_user_id()
        command = args[0] if len(args) > 0 else ''
        
        if command in ['', 'list']:
            preset_list = presets.get_preset_list(user_id)
            
            strs = [
                "当前的公共预置AI人格有: \n" + ", ".join(preset_list["public"]),
                "当前所有个人预置AI人格有: \n" + ", ".join(preset_list["users"]),
                "当前你的个人预置AI人格有: \n" + ", ".join(preset_list["own"]),
                '请使用 "<人格名>" 开头的文字让对应人格的AI开始新的对话。\n（如："glados，你是谁？"）',
                '输入 "#preset help" (或"#p?") 获得关于操作预置人格的帮助'
            ]
            tosend = "\n".join(strs)
            await preset_e.send(message=tosend)
            return
        
        
        if command not in ['log', 'load', 'save', 'delete']:
            await preset_e.send(message=preset_help_text)
            return
        elif command == "save":
            if len(args) <= 1:  
                hint = "缺少名称参数，请给你的预设人格起个名字。\n格式: #preset save <预置人格名>"
                await preset_e.send(message=hint)
                return
            
            names = list(args[1:])
            presets.save_preset(user_id, names, member_messages[user_id])
            hint = f'已保存你的预置人格 "{names[0]}"'
            if len(names) > 1:
                hint += f'(别名:{",".join(names[1:])})'
            hint += f'，共计 {len(member_messages[user_id])} 条对话。仍然为你保留着当前的对话记录'
            await preset_e.send(message=hint)
            return

        if len(args) <= 1:  
            hint = "缺少名称参数，请指定预设人格名"
            await preset_e.send(message=hint)
            return
        
        preset_id = args[1].lower()
        preset_data, hint = find_preset(user_id, preset_id)
        if preset_data is None:
            # print(hint)
            await preset_e.send(message=hint)
            return
        
        
        preset = preset_data["preset"]
        messages = preset["messages"]
        name = preset_data["name"]
        creator_id = preset_data["creator_id"]
        if command == 'log':
            await preset_e.send(message=f'{name} 预置人格的对话记录如下：({len(messages)})\n\n{get_messages_str(messages)}')
        elif command == 'load':    
            set_preset_messages(user_id, preset)
            await preset_e.send(message=f'已将 {name} 预置人格应用到你的对话记录。你现在的对话记录如下：({len(messages)})\n\n{get_messages_str(messages)}')
        elif command == 'delete':
            if creator_id == user_id:
                presets.delete_preset(user_id, name)
                await preset_e.send(message=f'已删除你的 {name} 预置人格')
            else:
                await preset_e.send(message=f'你个坏东西，怎么想着删别人的东西')
        
    except Exception as e:
        tosend=f"[ERROR] {str(e)}"
        await preset_e.send(message=tosend)
        
clear=on_command("#clear",aliases={},priority=2)
@clear.handle()
async def clear_func(match: Matcher, args: Message=CommandArg()):
    try:
        member_messages.clear()
        
        tosend= "已强制清空所有对话历史"
        await clear.send(message=tosend)
    except Exception as e:
        tosend=f"[ERROR] {str(e)}"
        await clear.send(message=tosend)


at_reply = on_message(rule=to_me(), priority=1, block=False)
@at_reply.handle()
async def at_reply_func(event: GroupMessageEvent, match: Matcher):
    global last_response_user_id
    
    match.stop_propagation()
    txt_content=event.get_plaintext()
    user_id = last_response_user_id if len(last_response_user_id) > 0 else event.get_user_id()
    tosend = await post_request(user_id, txt_content, False)
    await ask.send(message=tosend, at_sender=True)

reply = on_command("so ",aliases={'so,', 'so，', 'So,','##'},priority=5)
@reply.handle()
async def reply_func(event: MessageEvent, match: Matcher, args: Message=CommandArg()):
    user_id = event.get_user_id()
    txt_content = args.extract_plain_text()
    tosend = await post_request(user_id, txt_content, False)
    await ask.send(message=tosend, at_sender=not event.is_tome())
  
ask=on_command("gpt",aliases={'#gpt', 'GPT', '#GPT', 'Gpt'},priority=5)
@ask.handle()
async def ask_func(event: MessageEvent, match: Matcher, args: Message=CommandArg()):
    user_id = event.get_user_id()
    txt_content = args.extract_plain_text()
    tosend = await post_request(user_id, txt_content, True)
    await ask.send(message=tosend, at_sender=not event.is_tome())


regex_preset_name = re.compile(r'^([^#\s、,，.。;；?？!！:：=\-+*/]+(?:#\d+)?)([\w\W]*)$')

preset_ask = on_message(priority=2, block=False)
@preset_ask.handle()
async def preset_ask_func(event: MessageEvent, match: Matcher):
    txt_content=event.get_plaintext()
    if not presets.contains_presets(txt_content):
        return
    match_preset_name = regex_preset_name.search(txt_content)
    if match_preset_name is None:
        return
    
    match.stop_propagation()
    
    user_id = event.get_user_id()
    preset_name = match_preset_name.group(1).lower()
    txt_content = match_preset_name.group(2)

    preset_data, hint = find_preset(user_id, preset_name)
    if preset_data is None:  
        await preset_ask.send(message=hint, at_sender=not event.is_tome())
    
    set_preset_messages(user_id, preset_data["preset"])
    tosend = hint + await post_request(user_id, txt_content, False)
    await preset_ask.send(message=tosend, at_sender=not event.is_tome())


regex_numbers = re.compile(r'^([0-9]+)([\w\W]*)$')


async def post_request(user_id, txt_content, is_new):
    txt_content=txt_content.strip(' ').lstrip(',').lstrip('，')
    
    should_post = True
    
    
    if is_new:
        clear_message(user_id)
    
    if txt_content.startswith('!'):
        txt_content = txt_content.lstrip('!')
        should_post = False
        response_text = "已经记录下system对AI的指导内容"
        manual_add_response(user_id, 'system', txt_content)
    elif txt_content.startswith(':'):    
        txt_content = txt_content.lstrip(':')
        should_post = False
        response_text = "已经记录下AI对你的对话内容"
        manual_add_response(user_id, 'assistant', txt_content)
    elif txt_content.startswith('='):    
        txt_content = txt_content.lstrip('=')
        should_post = False
        manual_add_response(user_id, 'user', txt_content)
        response_text = "已经记录下你对AI的对话内容"
    elif txt_content.startswith('-'):
        removes = 1
        txt_content = txt_content.lstrip('-')
        match_numbers = regex_numbers.search(txt_content)
        if regex_numbers is not None:
            removes = int(match_numbers.group(1))
            txt_content = match_numbers.group(2)
        should_post = False
        response_text = f"已经删除 {removes} 条对话内容"
        manual_delete_response(user_id, removes)
        
    try:
        if (should_post):
            return await proxy(user_id, txt_content, 'user')
        else:
            return f'{response_text}，{get_user_messages(user_id)}\n\n请使用"##"发送记录好的对话，或是直接使用"##<想要发送的内容>"发送下一句向AI的对话。'
    except Exception as e:
        return f"[ERROR] {str(e)}"