# Dependency Reference: `pycparser` (3.11)

Comprehensive technical documentation for `pycparser` (pure Python C parser) as installed in Sherlock-V2's virtual environment (`.venv/Lib/site-packages/pycparser`).

---

## 1. Version & Package Architecture

### 1.1 Installed Version & Metadata
- **Package Name**: `pycparser`
- **Installed Version**: `3.11`
- **Author / Maintainer**: Eli Bendersky (`eliben@gmail.com`)
- **License Expression**: `BSD-3-Clause` (`pycparser-3.11.dist-info/METADATA:7`)
- **Python Compatibility**: `Requires-Python: >=3.10` (`pycparser-3.11.dist-info/METADATA:17`)
- **Upstream Repository**: `https://github.com/eliben/pycparser` (`pycparser-3.11.dist-info/METADATA:8`)
- **Top-Level Package String**: `pycparser/__init__.py:11`:
  ```python
  __version__ = "3.11"
  ```
- **Lockfile Resolution (`Sherlock-V2/uv.lock:372-379`)**:
  ```toml
  [[package]]
  name = "pycparser"
  version = "3.11"
  source = { registry = "https://pypi.org/simple" }
  sdist = { url = "https://files.pythonhosted.org/packages/da/a8/c5fdbeee588bb8ada9458774f43adf1bdd30bd59157055142183e769a024/pycparser-3.11.tar.gz", hash = "sha256:d875f09c3507d00e1aba0eecc6dcadc1352f30fff09dc6bff2f1c2935e97c2bc", size = 113796, upload-time = "2026-10-09T12:56:59.539Z" }
  wheels = [
      { url = "https://files.pythonhosted.org/packages/90/11/0e6f11117525ff0eec40ebac3d313376f102df93ca44ad9e893ee85e4f89/pycparser-3.11-py3-none-any.whl", hash = "sha256:51d5a8ba2be0bbe440b99d2112604c95bbbc3c2748a64260186c541e1729cd80", size = 51178, upload-time = "2026-10-09T12:56:58.131Z" },
  ]
  ```
- **External Dependencies**: Zero. `pycparser` is written in 100% pure Python using standard library modules only (`re`, `dataclasses`, `enum`, `subprocess`, `weakref`, `collections.abc`, `typing`).

### 1.2 Package File Layout
Inside `.venv/Lib/site-packages/pycparser/`:
- `__init__.py`: Package entry point; exports `CParser`, `parse_file`, `preprocess_file`, `c_ast`, `c_lexer`, `c_parser`.
- `c_parser.py` (95 KB, 2,752 lines): Hand-written recursive-descent C parser implementing ISO C99 grammar and coordinate tracking.
- `c_lexer.py` (26 KB, 866 lines): Regular-expression-based lexical analyzer emitting `Token` instances, handling `#line` and `#pragma` directives.
- `c_ast.py` (34 KB, 1,380 lines): AST node classes generated from `_c_ast.cfg`. Includes `Node`, `NodeVisitor`, and ~60 concrete syntax tree node definitions.
- `c_generator.py` (22 KB, 680 lines): Reverse AST-to-C source code serializing visitor (`CGenerator`).
- `ast_transforms.py` (6.5 KB, 187 lines): AST post-processing utilities (`fix_switch_cases`, `fix_atomic_specifiers`).
- `_c_ast.cfg` (5.1 KB, 215 lines): Declarative schema defining AST node inheritance, child nodes, and attributes.
- `_ast_gen.py` (11.5 KB, 321 lines): Code generation script that builds `c_ast.py` from `_c_ast.cfg`.

---

## 2. What `pycparser` Does (and Does Not Do)

### 2.1 Grammar Support & Parser Architecture
`pycparser` is a parser for the C programming language written entirely in Python.
- **Grammar Standard**: Conforms to ISO/IEC 9899 (C99 standard, Annex A grammar) with select extensions from C11 (e.g. `_Generic`, `_Alignas`, `_Static_assert`, `_Atomic`).
- **Recursive-Descent Engine (pycparser 3.x overhaul)**:
  Historically (in versions 2.x), `pycparser` used PLY (Python Lex-Yacc) and maintained generated LALR(1) transition tables (`lextab.py`, `yacctab.py`). In `pycparser 3.x` (including `3.11`), the parser was rewritten as a hand-crafted recursive-descent parser (`pycparser/c_parser.py:47-109`). Parameters such as `yacc_optimize`, `yacctab`, `lextab`, and `yacc_debug` in `CParser.__init__` (`c_parser.py:59-68`) are retained solely for backward compatibility with older consumers like `cffi`.
- **Lexical Feedback & Type Scoping**:
  Because C grammar is not context-free (the classic "lexer hack" is required to disambiguate whether an identifier like `T * x;` is a pointer declaration or a multiplication expression), `pycparser.c_parser.CParser` coordinates directly with `CLexer` through a scope stack (`c_parser.py:76-84`):
  - `_scope_stack`: A list of dictionaries tracking whether identifiers in the active scope are `typedef` names (`True`) or regular variables/functions (`False`).
  - `_lex_type_lookup_func` (`c_parser.py:166-171`): A callback queried by `CLexer` whenever an identifier is scanned. If `_is_type_in_scope(name)` returns `True`, the token is emitted as `TYPEID` instead of `ID`.
  - Block scopes are opened (`_push_scope`) and closed (`_pop_scope`) on `{` and `}` delimiters via lexer callbacks (`c_parser.py:160-164`).

### 2.2 Lack of a Built-In C Preprocessor
`pycparser` **does NOT include a C preprocessor**:
1. **No Macro Expansion**: Directives such as `#define FOO 42` or `#define MAX(a,b) ...` are not expanded by the parser.
2. **No Header Inclusion**: `#include <stdio.h>` is not resolved or traversed.
3. **No Conditional Compilation**: `#ifdef`, `#ifndef`, `#if`, `#else`, and `#endif` blocks are not evaluated.

If raw C code containing preprocessor directives is passed directly to `CParser.parse()`, the parser will fail with a `ParseError`.

#### How Preprocessing Is Handled:
- **External Preprocessor Invocation (`pycparser/__init__.py:20-53`)**:
  `pycparser.preprocess_file(filename, cpp_path="cpp", cpp_args="")` shells out via Python's standard library:
  ```python
  # pycparser/__init__.py:44
  text = check_output(path_list, universal_newlines=True)
  ```
  It requires an external C preprocessor (`cpp`, `gcc -E`, or `clang -E`) installed on the host operating system.
- **Line & Pragma Handling in Lexer (`pycparser/c_lexer.py:87-92`)**:
  While it cannot expand macros, `CLexer` handles preprocessed `#line` directives emitted by preprocessors:
  - When `# <line> "<filename>"` or `#line <line> "<filename>"` is encountered, `CLexer` adjusts its internal `_lineno` and `_filename` attributes (`c_lexer.py:88-89`).
  - `#pragma` directives are scanned into `PPPRAGMA` and `PPPRAGMASTR` tokens and surfaced in the AST as `c_ast.Pragma` nodes (`c_parser.py:2738-2748`, `c_ast.py:1364-1380`).

---

## 3. How `cffi` Uses `pycparser`

`cffi` is the primary downstream consumer of `pycparser` in the Python ecosystem. In Sherlock-V2, `cffi` relies on `pycparser` inside `.venv/Lib/site-packages/cffi/cparser.py`.

```
+---------------------------------------------------------------------------------------+
|                                    User / Library                                     |
|                       ffi.cdef(""" int curl_easy_perform(void *curl); """)            |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                               cffi.cparser.Parser                                     |
|  1. Cleans comments, resolves #define constants with regex (_preprocess:65-177)      |
|  2. Prepends synthetic typedefs (__dotdotdot__, common types) (cparser.py:323-333)    |
|  3. Acquires thread lock (pycparser is non-thread-safe) (cparser.py:335)              |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                                pycparser.CParser                                      |
|  - Tokenizes with CLexer (tracks typedef scopes)                                      |
|  - Parses recursive-descent translation unit -> c_ast.FileAST                         |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                          cffi AST Walker & Model Generator                            |
|  - Locates __dotdotdot__ separator in ast.ext (cparser.py:400-405)                    |
|  - Iterates ast.ext declarations: Decl, Typedef, Struct, FuncDecl                     |
|  - Converts pycparser AST nodes -> cffi.model.* types (FunctionType, StructType, etc) |
+---------------------------------------------------------------------------------------+
```

### 3.1 Avoidance of System Preprocessor for `cdef()`
Standard C header files are enormous and contain compiler-specific builtins that break lightweight parsers. `cffi` does not call an external `cpp` or `gcc -E`. Instead, `cffi.cparser` implements its own lightweight preprocessing pass (`cffi/cparser.py:65-177`):
- Strips C block comments (`/* ... */`) and line comments (`// ...`) (`cffi/cparser.py:27-28`).
- Strips Windows calling convention annotations (`__stdcall`, `WINAPI`, `__cdecl`) (`cffi/cparser.py:39-41, 140-142`).
- Rewrites `extern "Python"` callback declarations into synthetic C variables (`cffi/cparser.py:144-147`).
- Captures integer `#define` macros using regex and registers them as integer constants (`cffi/cparser.py:465-479`).

### 3.2 Synthetic Header Injection & Thread Safety Lock
Because `pycparser` requires all types to be known prior to their use in declarations, `cffi` constructs a synthetic source unit before invoking `pycparser`:
```python
# cffi/cparser.py:322-333
csourcelines = []
csourcelines.append('# 1 "<cdef automatic initialization code>"')
for typename in typenames:
    csourcelines.append('typedef int %s;' % typename)
csourcelines.append('typedef int __dotdotdotint__, __dotdotdotfloat__,'
                    ' __dotdotdot__;')
csourcelines.append('# 1 "%s"' % (CDEF_SOURCE_STRING,))
csourcelines.append(csource)
csourcelines.append('')
fullcsource = '\n'.join(csourcelines)
```

Furthermore, because `pycparser.CParser` maintains mutable state in `_scope_stack` and `clex`, it is **not thread-safe**. `cffi` guards parsing with a process-wide thread lock:
```python
# cffi/cparser.py:334-342
if lock is not None:
    lock.acquire()     # pycparser is not thread-safe...
try:
    ast = _get_parser().parse(fullcsource)
except pycparser.c_parser.ParseError as e:
    self.convert_pycparser_error(e, csource)
finally:
    if lock is not None:
        lock.release()
```

### 3.3 AST Conversion to CFFI Type Models
Once `pycparser.CParser.parse()` returns a `c_ast.FileAST`, `cffi` steps through `ast.ext` (`cffi/cparser.py:400-433`):
1. **Preamble Skipping**: It searches for the declaration named `__dotdotdot__` and begins real processing only on subsequent declarations (`cffi/cparser.py:400-405`).
2. **AST Node Dispatching**:
   - `pycparser.c_ast.Decl`: Passed to `_parse_decl(decl)` (`cffi/cparser.py:509-559`). Differentiates `FuncDecl`, `Struct`, `Union`, `Enum`, and global variables/constants.
   - `pycparser.c_ast.Typedef`: Resolves underlying type specifications (`TypeDecl`, `PtrDecl`, `IdentifierType`) and registers the alias (`cffi/cparser.py:414-432`).
   - `pycparser.c_ast.Pragma`: Emits a warning informing the user that pragmas (except `#pragma pack`, which must use the `packed` argument) are ignored (`cffi/cparser.py:433-442`).
   - Other nodes (e.g. `Compound`, executable statements): Raises `CDefError("unexpected <%s>: this construct is valid C but not valid in cdef()")` (`cffi/cparser.py:444-446`).
3. **Type Model Conversion**:
   Translates AST nodes into `cffi.model` objects:
   - `pycparser.c_ast.FuncDecl` -> `cffi.model.RawFunctionType`
   - `pycparser.c_ast.Struct` -> `cffi.model.StructType`
   - `pycparser.c_ast.PtrDecl` -> `cffi.model.PointerType`
   - `pycparser.c_ast.ArrayDecl` -> `cffi.model.ArrayType`
   - `pycparser.c_ast.IdentifierType` -> primitive C types (e.g., `int`, `uint32_t`, `void`).

### 3.4 Isolated Type String Parsing (`parse_type`)
In addition to whole-block `cdef()` processing, `cffi` uses `pycparser` dynamically to parse individual type signatures when types are resolved on the fly:
```python
# cffi/cparser.py:560-569
def parse_type(self, cdecl):
    return self.parse_type_and_quals(cdecl)[0]

def parse_type_and_quals(self, cdecl):
    ast, macros = self._parse('void __dummy(\n%s\n);' % cdecl)[:2]
    assert not macros
    exprnode = ast.ext[-1].type.args.params[0]
    if isinstance(exprnode, pycparser.c_ast.ID):
        raise CDefError("unknown identifier '%s'" % (exprnode.name,))
    return self._get_type_and_quals(exprnode.type)
```
Whenever `ffi.new("char *")`, `ffi.cast("uint32_t", val)`, or `ffi.typeof("struct sockaddr_in *")` is called with an uncached string, `cffi.api.FFI._typeof_locked()` invokes `self._parser.parse_type(cdecl)` (`cffi/api.py:164`), evaluating the declaration via `pycparser`.

---

## 4. Public API Reference

The primary public symbols exported by `pycparser` are defined in `pycparser/__init__.py:10-18`.

### 4.1 Parser Class: `CParser`
- **Location**: `pycparser/c_parser.py:47-109` (aliased in `pycparser/__init__.py:17`)
- **Constructor Signature**:
  ```python
  class CParser:
      def __init__(
          self,
          lex_optimize: bool = True,
          lexer: type[CLexer] = CLexer,
          lextab: str = "pycparser.lextab",
          yacc_optimize: bool = True,
          yacctab: str = "pycparser.yacctab",
          yacc_debug: bool = False,
          taboutputdir: str = "",
      ) -> None
  ```
- **Parsing Method**:
  ```python
  # pycparser/c_parser.py:87-109
  def parse(self, text: str, filename: str = "", debug: bool = False) -> c_ast.FileAST:
      """Parses C code and returns an AST.

      text:
          A string containing the C source code.
      filename:
          Name of the file being parsed (for coordinate error tracking).
      debug:
          Deprecated debug flag (retained for backward compatibility).
      """
  ```
- **Errors**: Raises `pycparser.c_parser.ParseError` (`c_parser.py:43-44`) on syntax errors or invalid declarations, embedding coordinate information (`Coord: file:line:column`).

### 4.2 Top-Level Convenience Functions

#### `parse_file(...)`
- **Location**: `pycparser/__init__.py:55-99`
- **Signature**:
  ```python
  def parse_file(
      filename,
      use_cpp=False,
      cpp_path="cpp",
      cpp_args="",
      parser=None,
      encoding=None,
  ) -> c_ast.FileAST
  ```
- **Behavior**:
  - If `use_cpp=True`, executes `preprocess_file(filename, cpp_path, cpp_args)` first.
  - If `use_cpp=False`, directly reads the file contents with `open(filename, encoding=encoding)`.
  - Instantiates `CParser()` (if no custom parser is supplied) and executes `parser.parse(text, filename)`.

#### `preprocess_file(...)`
- **Location**: `pycparser/__init__.py:20-53`
- **Signature**:
  ```python
  def preprocess_file(filename, cpp_path="cpp", cpp_args="") -> str
  ```
- **Behavior**:
  - Builds argument list: `[cpp_path] + cpp_args + [filename]`.
  - Invokes `subprocess.check_output(path_list, universal_newlines=True)`.
  - Returns the preprocessed string or raises `RuntimeError` if the executable cannot be invoked.

### 4.3 AST Representation: `pycparser.c_ast`
- **Base Node (`pycparser/c_ast.py:35-142`)**:
  - Class `Node`: Root class for all AST nodes.
  - Slots: Every node defines explicit `__slots__` including `coord` and `__weakref__`.
  - Methods:
    - `children()`: Returns a sequence of `(child_name, child_node)` tuples.
    - `show(buf=sys.stdout, offset=0, attrnames=False, showemptyattrs=True, nodenames=False, showcoord=False)`: Pretty-prints the syntax tree hierarchy.
    - `__iter__()`: Iterates over direct child nodes.
- **Visitor Pattern (`pycparser/c_ast.py:144-177`)**:
  - Class `NodeVisitor`: Base visitor modeled after Python's `ast.NodeVisitor`.
  - Dispatches dynamically to `visit_<NodeClassName>(node)`. If undefined, defaults to `generic_visit(node)`.
- **Core AST Node Types (`_c_ast.cfg` / `c_ast.py`)**:
  | Node Class | Configuration (`_c_ast.cfg`) | Description |
  | :--- | :--- | :--- |
  | `FileAST` | `[ext**]` | Root node representing a translation unit (list of external declarations). |
  | `Decl` | `[name, quals, align, storage, funcspec, type*, init*, bitsize*]` | Variable, function, or member declaration. |
  | `FuncDef` | `[decl*, param_decls**, body*]` | Function definition with compound body. |
  | `FuncDecl` | `[args*, type*]` | Function signature (parameters and return type). |
  | `TypeDecl` | `[declname, quals, align, type*]` | Base type declaration. |
  | `PtrDecl` | `[quals, type*]` | Pointer type modifier (e.g., `int *`). |
  | `ArrayDecl` | `[type*, dim*, dim_quals]` | Array type modifier (e.g., `char[256]`). |
  | `Struct` | `[name, decls**]` | C `struct` definition or reference. |
  | `Union` | `[name, decls**]` | C `union` definition or reference. |
  | `Enum` | `[name, values*]` | C `enum` definition or reference. |
  | `Typedef` | `[name, quals, storage, type*]` | C `typedef` definition. |
  | `IdentifierType`| `[names]` | Base type specifiers (`["int"]`, `["unsigned", "long"]`). |
  | `Typename` | `[name, quals, align, type*]` | Abstract type name used in casts and `sizeof`. |
  | `Constant` | `[type, value]` | Literal constant (int, char, string, float). |
  | `UnaryOp` / `BinaryOp` | `[op, expr*]` / `[op, left*, right*]` | Operators used in expressions and enum values. |

### 4.4 AST Code Generator: `pycparser.c_generator.CGenerator`
- **Location**: `pycparser/c_generator.py:15-680`
- **Usage**:
  ```python
  from pycparser import c_generator
  generator = c_generator.CGenerator(reduce_parentheses=False)
  c_code = generator.visit(ast)
  ```
- **Behavior**: Traverses `pycparser` AST nodes and reconstructs valid, formatted C source code. Useful for source-to-source transformations and AST rewriting.

---

## 5. Relevance to Sherlock-V2

### 5.1 Dependency Position in Dependency Graph
`pycparser` is strictly an **indirect, transitive sub-dependency** in Sherlock-V2:

```
sherlock-v2 (0.1.0)
 ├── phonsint (0.1.0)
 │    └── curl-cffi (0.16.3)
 │         └── cffi (2.1.1)
 │              └── pycparser (3.11)
 └── user-scanner (1.5.2.3)
      └── curl-cffi (0.16.3)
           └── cffi (2.1.1)
                └── pycparser (3.11)
```

1. Sherlock-V2 depends directly on `phonsint` and `user-scanner` (`pyproject.toml:9-10`).
2. Both libraries depend on `curl-cffi>=0.16.3`.
3. `curl-cffi` specifies `Requires-Dist: cffi>=2.0.0` (`curl_cffi-0.16.3.dist-info/METADATA:20`).
4. `cffi` specifies `Requires-Dist: pycparser; implementation_name != "PyPy"` (`cffi-2.1.1.dist-info/METADATA:27`).

### 5.2 Direct Codebase Audit
A complete audit across Sherlock-V2's source code (`src/sherlock_v2/`) confirms:
- **Zero Direct Imports**: Sherlock-V2 never imports `pycparser`, `c_parser`, or `c_ast`.
- **Zero Direct CFFI Calls**: Sherlock-V2 does not call `ffi.cdef()` or define dynamic C bindings.
- **Runtime Execution Decoupling**:
  `curl-cffi` is packaged and distributed using CFFI's **Out-of-line API mode**. In this mode, the C extension module (`curl_cffi._wrapper.pyd`) is pre-compiled at build time. When Sherlock-V2 performs OSINT phone searches (`phonsint`) or username reconnaissance (`user-scanner`), `curl-cffi` imports `_cffi_backend` directly:
  ```python
  # curl_cffi/__init__.py:63-68
  import _cffi_backend
  from ._wrapper import ffi, lib
  ```
  Because the FFI bindings are pre-compiled into `_wrapper.pyd`, `cffi.cdef()` is **never called at runtime**. Consequently, `pycparser` is not imported or loaded into Python process memory during standard Sherlock-V2 application execution.

---

## 6. Cross-Check & Prior Art Audit

- **Comparison with `animepahe-tv` Reference Docs**:
  Cross-checking the documentation directory in `animepahe-tv` (`animepahe-tv/docs/reference/`) reveals references for `dep-cffi.md`, `dep-httpx.md`, `dep-anyio.md`, `dep-flet.md`, etc., but **no documentation for `pycparser` exists in `animepahe-tv`**.
- **Conclusion**: This is an entirely fresh study of `pycparser 3.11`, detailing its internal recursive-descent architecture, absence of a preprocessor, integration with CFFI's declaration compiler, and transitive presence in Sherlock-V2.

---

## 7. Verification & Key Source Citations

| Subject | Source Location | Description |
| :--- | :--- | :--- |
| Version declaration | `pycparser/__init__.py:11` | `__version__ = "3.11"` |
| Package exports | `pycparser/__init__.py:10, 17` | `__all__ = ["c_ast", "c_lexer", "c_parser"]`, `CParser = c_parser.CParser` |
| File parsing API | `pycparser/__init__.py:55-99` | `def parse_file(filename, use_cpp=False, ...)` |
| Preprocessing helper | `pycparser/__init__.py:20-53` | `def preprocess_file(filename, cpp_path="cpp", ...)` invoking `check_output` |
| Recursive-descent parser | `pycparser/c_parser.py:47-109` | `class CParser`, `parse(text, filename)` |
| Lexer coordination & scopes | `pycparser/c_parser.py:76-84, 120-172`| `_scope_stack`, `_is_type_in_scope`, `_lex_type_lookup_func` |
| Lexer implementation | `pycparser/c_lexer.py:23-100` | `class CLexer`, regex rules, `#line` and `#pragma` token stashing |
| AST root & visitor | `pycparser/c_ast.py:35-177` | `class Node`, `class NodeVisitor` |
| C code generator | `pycparser/c_generator.py:15-50` | `class CGenerator`, AST-to-C rendering |
| CFFI parser integration | `cffi/cparser.py:50-54, 307-345` | `_get_parser()`, `Parser._parse()`, thread-locking `ast = _get_parser().parse(...)` |
| CFFI dynamic type parsing | `cffi/cparser.py:560-569` | `Parser.parse_type(cdecl)` via `void __dummy(\n%s\n);` wrapper |
| CFFI AST declaration dispatch | `cffi/cparser.py:408-446, 509-559`| `isinstance(decl, pycparser.c_ast.Decl)`, `FuncDecl`, `Struct`, `Union` |
| Sherlock-V2 lock resolution | `Sherlock-V2/uv.lock:372-379` | `pycparser v3.11` lockfile record |
| Sherlock-V2 dependency path | `Sherlock-V2/uv.lock:27-34, 95-102` | `sherlock-v2` -> `curl-cffi` -> `cffi` -> `pycparser` |
