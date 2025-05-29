# 利用 dwarf 信息跟踪异步 Future

## 摘要

本工作通过分析 dwarf 调试信息, 实现不依赖运行时的 Future 跟踪. 

## 1. 概述

### 1.1 背景

Rust 的 async 函数会被编译成实现了 `Future` trait （trait 类似于其他语言的`接口`）结构体. 

### 1.2 目标

通过分析 dwarf 调试信息, 实现不依赖运行时的 Future 跟踪. 

## 2. 方法

### 2.1 示例程序

在 rust 中, 编写 async 函数的方法有 2 种. 第一种是 `async fn`, 第二种是直接实现 `Future` 结构体. 我编写了一个简单的 Rust 程序, 这个 rust 程序中同时使用了两种编写 async 函数的方法, 且没有用到异步运行时:

```rust
struct NumberFuture {
    value: u32,
    processed: bool,
}

async fn add_future(a: u32, b: u32) -> u32 {
    let a_future = NumberFuture::new(a);
    let b_future = NumberFuture::new(b);
    let a_result = a_future.await;
    let b_result = b_future.await;
    a_result + b_result
}

async fn double_future(n: u32) -> u32 {
    let n_future = NumberFuture::new(n);
    let result = n_future.await;
    result * 2
}

async fn compute_result() -> u32 {
    let sum = add_future(5, 3).await;
    double_future(sum).await
}

```

### 2.2 分析工具

- `objdump`: 用于检索 dwarf 调试信息
- `cargo`: 构建工具

## 3. 分析过程和结果

### 3.1 编译程序

首先, 我们编译该示例代码. 我们在 `Cargo.toml` 中加入了 `debug=true` 命令, 使得编译出的二进制文件包含调试信息.

```bash
cargo build --release
```

### 3.2 人工分析 `NumberFuture` 结构体（自己写的 Future）

我用该命令分析 `NumberFuture`:

```bash
objdump -g target/release/async_future_analysis | grep -A 20 "NumberFuture"
```

结果: 

```
<799>   DW_AT_name        : NumberFuture
<79d>   DW_AT_byte_size   : 8
<79e>   DW_AT_accessibility: 3      (private)
<79f>   DW_AT_alignment   : 4
```

这说明 `NumberFuture` 这个结构体是8字节大小, 有 private 等级的可访问性, 4字节对齐.

接下来分析这个结构体的成员.

```
<7a0>: Abbrev Number: 35 (DW_TAG_member)
    <7a1>   DW_AT_name        : value
    <7a5>   DW_AT_type        : <0xfba>
    <7a9>   DW_AT_alignment   : 4
    <7aa>   DW_AT_data_member_location: 0
```

该结构体的名字是`value`, 类型是`u32`（在这里用 `0xfba` 指代）, 4字节对齐, 对于所属结构体的偏移量是0.

```
<7ac>: Abbrev Number: 35 (DW_TAG_member)
    <7ad>   DW_AT_name        : processed
    <7b1>   DW_AT_type        : <0xfc1>
    <7b5>   DW_AT_alignment   : 1
    <7b6>   DW_AT_data_member_location: 4
```

该结构体的名字是`processed`, 类型是`bool`（在这里用 `0xfba` 指代）, 4字节对齐, 对于所属结构体的偏移量是4.

### 3.3 人工分析 `add_future` 结构体（async fn）

用类似命令分析 `add_future`:

```bash
objdump -g target/release/async_future_analysis | grep -A 20 "add_future"
```

结果：

```
<5a0>   DW_AT_name        : add_future
<3><5a4>: Abbrev Number: 8 (DW_TAG_structure_type)
    <5a5>   DW_AT_name        : {async_fn_env#0}
    <5a9>   DW_AT_byte_size   : 32
    <5aa>   DW_AT_alignment   : 4
```

从结果中可以看出, add_future 这个 `async fn` 被编译成叫做`{async_fn_env#0}`的**状态机结构体**. 大小是32字节, 对齐是4字节.

> `NumberFuture` 是最底层的Future所以并没有状态机结构体

这个状态机结构体的细节如下:

```
<4><5ab>: Abbrev Number: 22 (DW_TAG_variant_part)
    <5ac>   DW_AT_discr       : <0x5b0>
<5><5b0>: Abbrev Number: 23 (DW_TAG_member)
    <5b1>   DW_AT_name        : __state
    <5b5>   DW_AT_type        : <0xfb3>
    <5b9>   DW_AT_alignment   : 1
    <5ba>   DW_AT_data_member_location: 12
```

该状态机包含`variant`部分（注：`variant`本来是给Ada语言用的, `rustc`编译器借用`variant`部分存储Future的状态机结构体）. `variant`部分存储了这个状态及所有的状态. 这个`variant`部分是`__state`属性, 这个属性包含了状态机所有的状态. 

## 4. Python 自动分析器实现

> 相关代码全部位于 `future_analyzer/src/main.py` ，直接运行
>
> ```bash
> cargo build                       # 生成调试版二进制
> python3 future_analyzer/src/main.py async_future_analysis/target/debug/async_future_analysis --json
> ```
> 即可得到完整的 JSON 结构。

### 4.1 关键 DWARF 片段示例
下面节选一段 `objdump --dwarf=info` 的输出（来自 `compute_result` 顶级 async-block 的状态机）：

```text
 <3><3134>: Abbrev Number: 28 (DW_TAG_structure_type)
    <3135>   DW_AT_name        : (indirect string, offset: 0x107a42): {async_block_env#0}
    <3139>   DW_AT_byte_size   : 40
    <313a>   DW_AT_alignment   : 4
 <4><313b>: Abbrev Number: 16 (DW_TAG_variant_part)
    <313c>   DW_AT_discr       : <0x3140>
 <5><3140>: Abbrev Number: 37 (DW_TAG_member)
    <3141>   DW_AT_name        : (indirect string, offset: 0x8ac60): __state   # 枚举状态
 <5><314b>: Abbrev Number: 20 (DW_TAG_variant)
    …                               # 这里列出 0/1/2/3 四个状态
 <5><317d>: Abbrev Number: 38 (DW_TAG_member)
    <317e>   DW_AT_name        : (indirect string, offset: 0xa2956): 3         # 状态 3 保存的局部 future
    <3182>   DW_AT_type        : <0x762d>   # → Pin<&mut async_future_analysis::compute_result::{async_fn_env#0}>
```

在这段输出里我们关心的信息有：
1. `DW_TAG_structure_type`       – 说明这是一个结构体 DIE。  
2. `DW_AT_name`                  – 取到真实结构体名（`{async_block_env#0}`）。  
3. `DW_AT_byte_size / alignment` – 结构体大小与对齐。  
4. `DW_TAG_variant_part / DW_TAG_variant` – 由 Rust 编译器借用保存 **状态机的不同状态**。本身并不直接携带类型，但其子节点里会继续出现 `DW_TAG_member`。  
5. `DW_TAG_member`               – 真正保存字段；字段里的 `DW_AT_type` 给出一个 **DIE offset**（如 `0x762d`）指向成员类型。

> 提示：实际依赖信息都出现在 `DW_TAG_member` 的 `DW_AT_type` 中。`variant` 只是一个逻辑分组节点。为了找到子 future，我们必须先进入 `variant_part → variant`，再去解析里面的 member——这正是解析器递归遍历的原因。

### 4.2 代码如何提取这些信息
以下对照 `main.py` 中的函数完成过程：

| 处理步骤 | 代码位置 | 说明 |
|-----------|-----------|------|
| 定位结构体起始行 | `parse_dwarf()` | 用正则 `r"<\d+><[0-9a-f]+>: .*\(DW_TAG_structure_type\)` 捕获；同时记录 *depth* 值（尖括号里的首个数字），以便确定该结构体块的结束位置。 |
| 收集整个结构体块 | `parse_dwarf()` | 自己和后续行加入 `struct_lines`，直到遇到 *depth ≤ 当前 depth* 的下一个 `Abbrev Number` 行。 |
| 解析基本属性 | `_parse_struct_block()` | • 通过 `DW_AT_name` 行取得名字<br>• `DW_AT_byte_size / alignment` 提取大小、对齐<br>• 结构体头行中的第二个尖括号值 `<offset>` 作为 **type_id**，稍后可由字段引用。 |
| 解析成员字段 | `_parse_member_block()` | 对 `DW_TAG_member` 的子块再次搜 `DW_AT_name / DW_AT_type / DW_AT_data_member_location` 等；`DW_AT_type` 里的十六进制偏移就是指向另一 DIE 的 type_id。 |
| 判断是否为 Future 状态机 | `_parse_struct_block()` | 若名字匹配 `async_fn_env|async_block_env|Future`(大小写不敏感) 就标记 `state_machine = True`。 |
| 构建依赖树 | `build_dependency_tree()` + `_resolve_deps_recursive()` | 先把所有 `state_machine` 结构体放入根集合，然后递归根据 *member.type* → *type_id_to_struct* 关系向下查找：遇到子结构体如果本身是 state-machine 就作为依赖；否则继续下钻，直到找到下一个 state-machine。 |
| 处理重名 | `_parse_struct_block()` | 同名的 `{async_fn_env#0}` 可能出现多次；用 `name + '<0x{type_id}>'` 保证字典键唯一。 |
| JSON 输出 | `output_json()` | 把上述解析结果序列化为：`async_functions`, `state_machines`, `dependency_tree` 三大块。 |

### 4.3 运行效果
```bash
$ python3 future_analyzer/src/main.py async_future_analysis/target/debug/async_future_analysis --json | jq -r '.dependency_tree["{async_block_env#0}"]'
[
  "{async_fn_env#0}<0x4b98>",   # compute_result
  "NumberFuture",               # 孤立 NumberFuture（示例）
  "{async_fn_env#0}<0x49b1>",   # add_future
  "{async_fn_env#0}<0x4ae2>"    # double_future
]
```
配合递归显示函数可得到与 `main.rs` 逻辑一致的层级：

```
{async_block_env#0}
└─ compute_result::{async_fn_env#0}
   ├─ add_future::{async_fn_env#0}
   │  ├─ NumberFuture
   │  └─ NumberFuture
   └─ double_future::{async_fn_env#0}
      └─ NumberFuture
```

至此，我们实现了**完全基于 DWARF 调试信息**、不依赖运行时的异步 Future 依赖自动分析工具。