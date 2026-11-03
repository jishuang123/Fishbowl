"""A fast, read-only query of the host's local clock and UTC offset."""
from datetime import datetime


def current_time(_arguments):
    now = datetime.now().astimezone()
    offset = now.strftime('%z')
    offset = offset[:3]+':'+offset[3:]
    weekday = ('星期一','星期二','星期三','星期四','星期五','星期六','星期日')[now.weekday()]
    display = f"本机时间：{now:%Y-%m-%d %H:%M:%S} {weekday}\n时区：{now.tzname()}（UTC{offset}）"
    return {'ok':True, 'local_time':now.isoformat(timespec='seconds'), 'timezone':now.tzname(),
            'utc_offset':offset, 'weekday':weekday, 'unix_timestamp':int(now.timestamp()), 'display':display}


def current_time_plugin():
    from ..tool_registry import ToolPlugin
    return ToolPlugin(
        name='get_current_time', title='查询当前时间',
        description='查询用户电脑当前的本地日期、时间、星期、时区和 UTC 偏移。询问现在几点、今天日期或星期时调用；每次重新查询，不把历史时间当作现在。无需参数。',
        parameters={'type':'object','properties':{},'required':[],'additionalProperties':False},
        handler=current_time)
