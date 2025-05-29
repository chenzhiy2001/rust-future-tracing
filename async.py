import json
import gdb
import os
import time # BUG: This is system time, not debugee time!

project_root = "."
result=[] # array of strings
result_object=[] # array of objects
# result.append("time   thread_id: [entry/exit] FUNCTION_NAME(FUNCTION_ADDR?PC=0x00000000) depth: 0")
# command for logging at function entry
class FunctionEntryLogger(gdb.Command):
    def __init__(self):
        super().__init__("function_entry_logger", gdb.COMMAND_USER)
        self.func_name = "unknown"
        self.depth = -114514
    def invoke(self, arg, from_tty):
        # arg is the function name
        self.func_name = arg
        thread_id = gdb.selected_thread().ptid[1]
        timestamp = time.time()
        frame = gdb.newest_frame()
        self.addr = frame.pc()
        self.depth = 0
        while frame is not None:
            self.depth += 1
            frame = frame.older()
        # result.append(f"{timestamp:.6f}   {thread_id}: [entry] {self.func_name}({self.addr}) depth: {self.depth}")
        result_object.append(
            {
                "time": timestamp,
                "thread_id": thread_id,
                "entry_exit": "entry",
                "fn_name": self.func_name,
                "addr": self.addr,
                "depth": self.depth
            }
        )

# not used
class FunctionExitLogger(gdb.Command):
    def __init__(self):
        super().__init__("function_exit_logger", gdb.COMMAND_USER)
        self.func_name = "unknown"
        self.depth = -114514
    def invoke(self, arg, from_tty):
        # arg is the function name
        self.func_name = arg
        thread_id = gdb.selected_thread().ptid[1]
        timestamp = time.time()
        frame = gdb.newest_frame()
        self.addr = frame.pc()
        self.depth = 0
        while frame is not None:
            self.depth += 1
            frame = frame.older()
        result.append(f"{timestamp:.6f}   {thread_id}: [exit ] {self.func_name}({self.addr}) depth: {self.depth}")

class FunctionReturnBreakpoint(gdb.FinishBreakpoint):
    def __init__(self, func_name):
        super().__init__()
        self.func_name = func_name
        self.depth = -114514
    def stop (self):
        self.log()
        return False
    def out_of_scope(self):
        self.log()
        return
    def log(self):
        thread_id = gdb.selected_thread().ptid[1]
        timestamp = time.time()
        frame = gdb.newest_frame()
        self.addr = frame.pc()
        self.depth = 0
        while frame is not None:
            self.depth += 1
            frame = frame.older()
        # result.append(f"{timestamp:.6f}   {thread_id}: [exit ] {self.func_name}({self.addr}) depth: {self.depth+1}") # depth + 1 because this is a return breakpoint, you already popped the frame
        result_object.append({
            "time": timestamp,
            "thread_id": thread_id,
            "entry_exit": "exit ",
            "fn_name": self.func_name,
            "addr": self.addr,
            "depth": self.depth+1
        })

class RegisterFunctionReturnBreakpoint(gdb.Command):
    def __init__(self):
        super().__init__("register-function-return-breakpoint", gdb.COMMAND_USER)
        self.func_name = "unknown"
    def invoke(self, arg, from_tty):
        # arg is the function name
        self.func_name = arg
        FunctionReturnBreakpoint(self.func_name)

class DumpAsyncLog(gdb.Command):
    def __init__(self):
        super().__init__("dump_async_log", gdb.COMMAND_USER)
    def invoke(self, arg, from_tty):
        trace_events = []
        for entry in result_object:
            ts = entry["time"]
            ph = "B" if entry["entry_exit"] == "entry" else "E"
            pid = str(entry["thread_id"])
            tid = f" {entry['thread_id']}"
            name = entry["fn_name"]
            args = {"Function address (For recognizing anonymous type)": f"0x{entry['addr']}"}

            trace_event = {
                "ts": ts * 10**7,
                "ph": ph,
                "pid": pid,
                "tid": tid,
                "name": name,
            }

            if ph == "E":
                trace_event["args"] = args

            trace_events.append(trace_event)

        output = {
            "traceEvents": trace_events,
            "displayTimeUnit": "ns"
        }

        with open("output-directjson.json", "w") as json_file:
            json.dump(output, json_file, indent=4)

def get_addr_and_func_name(line:str)->tuple[str, str]:
    parts = line.split()
    if len(parts) >= 2:
        func_addr = "0x"+parts[0]
        func_name = line.strip(parts[0]+" "+parts[1]+" ").strip()
        # strip ".hidden " of func_name if it exists
        print(f"func_name: {func_name}")
        return func_addr, func_name
    print(f"Invalid line format: {line}")
    return None, None

def register_loggers(symbol_file_path):
    with open(symbol_file_path, "r") as f:
        for line in f:
            (func_addr, func_name) = get_addr_and_func_name(line)
            # gdb.execute(f"""
            #     break *{func_addr}
            #     command
            #     silent
            #     function_entry_logger {func_name}
            #     finish
            #     function_exit_logger {func_name}
            #     continue
            #     end
            # """)
            set_by = "func_name"
            if set_by == "func_name":
                gdb.execute("break "+func_name+"\ncommands\nfunction_entry_logger "+func_name+"\nregister-function-return-breakpoint "+func_name+"\ncontinue\nend")
            elif set_by == "func_addr":
                gdb.execute("break *"+func_addr+"\ncommands\nfunction_entry_logger "+func_name+"\nregister-function-return-breakpoint "+func_name+"\ncontinue\nend")
            # looks like you can't embed commands in commands, so using finish does not work
            # gdb.execute("break *"+func_addr+"\ncommands\nsilent\nfunction_entry_logger "+func_name+"\nfinish\nfunction_exit_logger "+func_name+"\ncontinue\nend")

FunctionEntryLogger()
FunctionExitLogger()
RegisterFunctionReturnBreakpoint()
DumpAsyncLog()

register_loggers("async.sym")

