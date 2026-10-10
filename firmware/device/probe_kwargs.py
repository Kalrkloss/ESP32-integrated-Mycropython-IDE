# probe_kwargs.py -- welche Aufrufformen akzeptiert MicroPython hier?

def f(a=1, b="x"):
    return (a, b)


g = lambda a=1, b=2: a + b


def check(label, fn):
    try:
        print("OK   %-46s -> %s" % (label, fn()))
    except Exception as exc:  # noqa: BLE001
        print("FEHL %-46s -> %s: %s" % (label, type(exc).__name__, exc))


check("def f(a=2)", lambda: f(a=2))
check("def f(**{'a': 3})", lambda: f(**{"a": 3}))
check("def f mit Pflichtargument", lambda: (lambda x: x)(x=1))
check("lambda a=1 g(a=5)", lambda: g(a=5))
check("lambda a=1 g(**{'a':6})", lambda: g(**{"a": 6}))
check("lambda ohne Default (x=1)", lambda: (lambda x: x)(**{"x": 1}))

print("== Modulebene ==")
import mcp_logbuf  # noqa: E402
check("mcp_logbuf.logs(clear=False)", lambda: mcp_logbuf.logs(clear=False))
check("mcp_logbuf.logs()", lambda: mcp_logbuf.logs())

print("== Tool.call mit ** ==")
from mcp_protocol import Tool  # noqa: E402

t = Tool("x", "y",
         {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
         lambda code: "got:" + code)
check("Tool.call({'code': 'abc'})", lambda: t.call({"code": "abc"}))

print("== Bindung im Modul mcp_tools ==")
import mcp_tools  # noqa: E402
tools = {x.name: x for x in mcp_tools.build_tools()}
check("tools['logs'].call({})", lambda: tools["logs"].call({}))
check("tools['screenshot'].call({'scale': 4})", lambda: tools["screenshot"].call({"scale": 4}))
check("tools['files'].call({'action':'df'})", lambda: tools["files"].call({"action": "df"}))

print("probe_kwargs: fertig")
