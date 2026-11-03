"""Tool protocol fixtures, shared by real HTTP and native UI acceptance scripts."""
from chat_test_server import sse


def tool_parts(name='get_current_time', arguments='{}', identifier='call_clock_1', prefix=''):
    parts = [sse({'content':prefix})] if prefix else []
    parts += [sse({'tool_calls':[{'index':0,'id':identifier,'type':'function',
        'function':{'name':name[:5],'arguments':arguments[:1]}}]}),
        sse({'tool_calls':[{'index':0,'function':{'name':name[5:],'arguments':arguments[1:]}}]}),
        sse(finish='tool_calls'),b'data: [DONE]\n\n']
    return parts


def multiple_tools(count, prefix):
    return [sse({'tool_calls':[{'index':i,'id':f'{prefix}_{i}','type':'function',
        'function':{'name':'get_current_time','arguments':'{}'}} for i in range(count)]}),
        sse(finish='tool_calls'),b'data: [DONE]\n\n']
