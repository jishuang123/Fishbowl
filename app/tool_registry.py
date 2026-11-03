"""A small native plugin interface. Model output can select only registered tools."""
import json
import re
from dataclasses import dataclass
from typing import Callable


def no_arguments(arguments):
    return isinstance(arguments,dict) and not arguments


@dataclass(frozen=True)
class ToolPlugin:
    name: str
    title: str
    description: str
    parameters: dict
    handler: Callable[[dict],dict]
    validate_arguments: Callable[[object],bool] = no_arguments


class ToolRegistry:
    def __init__(self, plugins=()):
        self.plugins = {}
        for plugin in plugins:self.register(plugin)

    def register(self, plugin:ToolPlugin):
        if (not isinstance(plugin.name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}',plugin.name) or
            plugin.name in self.plugins or not isinstance(plugin.title,str) or not 0<len(plugin.title)<=80 or
            not isinstance(plugin.description,str) or not isinstance(plugin.parameters,dict) or
            not callable(plugin.handler) or not callable(plugin.validate_arguments)):
            raise ValueError('Invalid or duplicate tool name')
        self.plugins[plugin.name] = plugin

    def schemas(self):
        return [{'type':'function','function':{'name':p.name,'description':p.description,'parameters':p.parameters}}
                for p in self.plugins.values()]

    def title(self, name):
        plugin = self.plugins.get(name)
        return plugin.title if plugin is not None else '未支持的工具'

    def execute(self, name, argument_text):
        plugin = self.plugins.get(name)
        if plugin is None:
            return {'ok':False,'error':'当前没有这个工具。','display':'当前没有这个工具，未执行操作。'}
        try:
            arguments = json.loads(argument_text)
        except (ValueError,TypeError):
            return {'ok':False,'error':'参数不是有效的 JSON。','display':'工具参数格式错误，未执行操作。'}
        try:
            if not plugin.validate_arguments(arguments):
                return {'ok':False,'error':'工具参数无效。','display':'这个工具不接受这些参数，未执行操作。'}
            result = plugin.handler(arguments)
            if (not isinstance(result,dict) or type(result.get('ok')) is not bool or
                not isinstance(result.get('display'),str) or not result['display'].strip() or
                len(json.dumps(result,ensure_ascii=False))>4000):
                raise ValueError()
            return result
        except Exception:
            # Never expose exception text, local paths, or plugin internals to the model/UI.
            return {'ok':False,'error':'本机工具暂时不可用。','display':'本机工具暂时不可用，请稍后再试。'}


def builtin_tools():
    from .plugins import builtin_plugins
    return ToolRegistry(builtin_plugins())
