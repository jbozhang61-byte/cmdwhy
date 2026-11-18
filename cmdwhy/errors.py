"""错误识别：把 stderr / 退出码归一成稳定的错误签名，供检索与知识库复用。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .util import first_line, strip_ansi, truncate

RULES = (
    ("GIT_AUTH", re.compile(r"authentication failed for .*https|fatal: authentication|could not read username|http 401|invalid username or password", re.I)),
    ("SSH", re.compile(r"permission denied \(publickey|host key verification failed|connection closed by remote host|too many authentication failures", re.I)),
    ("K8S", re.compile(r"kubectl|unable to connect to the server|crashloopbackoff|containercreating|forbidden.*(?:pods|services|deployments)|no resources found", re.I)),
    ("DB", re.compile(r"psql|mysql|mariadb|redis|mongodb|mongo|postgres|could not connect to server|too many connections|relation .* does not exist|access denied for user|数据库|データベース|Datenbank|base de données|base de datos|база данных", re.I)),
    ("TLS", re.compile(r"certificate verify failed|x509|ssl error|tls handshake|unknown ca|self[- ]signed certificate|证书验证失败|证书|証明書|Zertifikat|certificat|certificado|сертификат", re.I)),
    ("READONLY", re.compile(r"read-only file system|readonly database|attempt to write a readonly database|只读文件系统|只读数据库", re.I)),
    ("TEST_FAIL", re.compile(r"assertionerror|tests? failed|failed tests?|test suite failed|npm err! test failed|pytest.*failed|测试失败|断言失败|テスト失敗|Test fehlgeschlagen|Échec du test|Prueba fallida", re.I)),
    ("DEPENDENCY", re.compile(r"eresolve|peer dep|dependency conflict|cannot satisfy|conflicting dependencies|requires .* but", re.I)),
    ("YAML", re.compile(r"yaml\.scanner|mapping values are not allowed|expected <block end>|could not find expected ':'", re.I)),
    ("JSON_DECODE", re.compile(r"jsondecodeerror|json\.decoder|unexpected token .* in json|invalid json", re.I)),
    ("COMPOSE", re.compile(r"docker[- ]compose|compose\.ya?ml|service .* failed to build", re.I)),
    ("JAVA", re.compile(r"unsupportedclassversionerror|java_home|no suitable java|maven.*failed|gradle.*failed", re.I)),
    ("RUST", re.compile(r"error\[e\d+\]|cargo (?:build|test|run).*failed|cannot find crate|rustc", re.I)),
    ("GO", re.compile(r"go: .*|missing go\.sum|module .* not found|go mod", re.I)),
    ("PIP668", re.compile(r"externally-managed-environment|pep[ -]?668|break-system-packages", re.I)),
    (
        "DOCKER",
        re.compile(
            r"cannot connect to the docker daemon|docker daemon socket|"
            r"permission denied while trying to connect to the docker daemon|is the docker daemon running",
            re.I,
        ),
    ),
    ("GIT_REJECT", re.compile(r"\[rejected\]|non-fast-forward|failed to push some refs|updates were rejected", re.I)),
    ("GIT_CONFLICT", re.compile(r"merge conflict|automatic merge failed|conflict \(content\)|needs merge", re.I)),
    ("NOT_FOUND", re.compile(r"no such file or directory|file or directory not found|没有那个文件或目录|文件或目录不存在|找不到文件|そのようなファイルやディレクトリはありません|Datei oder Verzeichnis nicht gefunden|Aucun fichier ou dossier de ce type|No existe el archivo o el directorio|Нет такого файла или каталога", re.I)),
    (
        "CMD_NOT_FOUND",
        re.compile(
            r"command not found|: not found\b|is not a git command|unknown command|"
            r"no such command|not installed\.|command not found:|"
            r"命令未找到|未找到命令|找不到命令|不是内部或外部命令|"
            r"コマンドが見つかりません|Befehl nicht gefunden|commande introuvable|"
            r"orden no encontrada|comando no encontrado|команда не найдена",
            re.I,
        ),
    ),
    (
        "PORT",
        re.compile(r"address already in use|eaddrinuse|port \d+ (?:is )?already|bind: address already in use|地址已在使用|端口.*占用|ポート.*使用中|Adresse bereits in Verwendung|port.*déjà utilisé|dirección ya está en uso", re.I),
    ),
    (
        "PERM",
        re.compile(
            r"permission denied|operation not permitted|eacces|access is denied|"
            r"are you root|must be root|only root|requires root|superuser|"
            r"权限不够|权限不足|权限被拒绝|拒绝访问|没有权限|"
            r"許可がありません|権限がありません|アクセスが拒否されました|"
            r"Zugriff verweigert|Keine Berechtigung|Permission non accordée|Permission refusée|"
            r"Accès refusé|Permiso denegado|Acceso denegado|Отказано в доступе|Нет прав",
            re.I,
        ),
    ),
    (
        "AUTH",
        re.compile(
            r"authentication failed|permission denied \(publickey|401 unauthorized|403 forbidden|"
            r"invalid credentials|could not read username|access token|bad credentials|"
            r"认证失败|令牌无效|凭证无效|認証に失敗|"
            r"Authentifizierung fehlgeschlagen|Échec de l'authentification|Error de autenticación|Ошибка аутентификации",
            re.I,
        ),
    ),
    (
        "MODULE",
        re.compile(r"modulenotfounderror|importerror|no module named|cannot find module|module not found|cannot import name|模块未找到|没有名为|找不到模块|モジュールが見つかりません|Modul nicht gefunden|Module introuvable|No se encuentra el módulo", re.I),
    ),
    (
        "BUILD",
        re.compile(
            r"undefined reference|fatal error: .*: no such file|make: \*\*\*|cmake error|gcc: error|"
            r"failed building wheel|error: command .* failed with exit status|linker command failed",
            re.I,
        ),
    ),
    ("DISK", re.compile(r"no space left|disk quota exceeded|read-only file system|insufficient space|inode|磁盘空间不足|设备上没有空间|ディスク容量が不足|Kein Speicherplatz|Aucun espace|No queda espacio|Нет места", re.I)),
    (
        "LOCK",
        re.compile(r"could not get lock|unable to acquire the dpkg frontend lock|dpkg frontend lock|database is locked|another process", re.I),
    ),
    (
        "NET",
        re.compile(
            r"connection refused|network is unreachable|temporary failure in name resolution|"
            r"name or service not known|could not resolve host|connection timed out|timed out|"
            r"connection reset by peer|ssl certificate problem|no route to host|"
            r"连接被拒绝|无法解析主机|名称解析暂时失败|连接超时|"
            r"接続が拒否されました|Verbindung abgelehnt|Name oder Dienst nicht bekannt|"
            r"connexion refusée|conexión rechazada|Соединение отклонено|Не удалось разрешить",
            re.I,
        ),
    ),
    ("SYNTAX", re.compile(r"syntax error|unexpected token|invalid syntax|parse error|unexpected eof|语法错误|意外的标记|構文エラー|Syntaxfehler|Erreur de syntaxe|Error de sintaxis", re.I)),
    ("KILLED", re.compile(r"\bkilled\b|out of memory|oom-kill|cannot allocate memory", re.I)),
    (
        "USAGE",
        re.compile(r"invalid option|unrecognized option|unknown option|usage:|invalid argument|missing required argument", re.I),
    ),
)

EXIT_MAP = {
    126: ("PERM:exec", "退出码 126：文件存在但没有执行权限"),
    127: ("CMD_NOT_FOUND", "退出码 127：命令不存在"),
    130: ("INTERRUPT", "退出码 130：被 Ctrl-C 中断"),
    137: ("KILLED", "退出码 137：被 SIGKILL 终止（常见于内存不足）"),
    143: ("INTERRUPT", "退出码 143：被 SIGTERM 终止"),
    2: ("USAGE", "退出码 2：参数或用法错误"),
}

MISSING_WORD_PATTERNS = (
    re.compile(r"([\w.+-]+): command not found", re.I),
    re.compile(r"bash: ([\w.+-]+): command not found", re.I),
    re.compile(r"zsh: ([\w.+-]+): command not found", re.I),
    re.compile(r"command not found: ([\w.+-]+)", re.I),
    re.compile(r"git: '([\w-]+)' is not a git command", re.I),
    re.compile(r"unknown command '([\w-]+)'", re.I),
    re.compile(r"the program '([\w.+-]+)' is currently not installed", re.I),
    re.compile(r"([\w.+-]+): not found", re.I),
    re.compile(r"([\w.+-]+)[:：]\s*(?:命令未找到|未找到命令|找不到命令|コマンドが見つかりません|Befehl nicht gefunden|commande introuvable|orden no encontrada|comando no encontrado|команда не найдена)", re.I),
    re.compile(r"'([^']+)'\s*不是内部或外部命令", re.I),
)

MODULE_PATTERNS = (
    re.compile(r"no module named '?([\w.]+)'?", re.I),
    re.compile(r"cannot find module '?([\w./@-]+)'?", re.I),
    re.compile(r"没有名为\s*['\"]?([\w.]+)", re.I),
    re.compile(r"モジュール\s*['\"]?([\w.]+)", re.I),
)

PATH_PATTERNS = (
    re.compile(r"'([^']+)': no such file or directory", re.I),
    re.compile(r"([/\w.~-]+): no such file or directory", re.I),
    re.compile(r"cannot (?:access|open|find) '?([^':\s]+)'?", re.I),
    re.compile(r"['\"]?([^'\":：]+)['\"]?\s*[:：]?\s*(?:没有那个文件或目录|文件或目录不存在|そのようなファイルやディレクトリはありません|Datei oder Verzeichnis nicht gefunden|Aucun fichier ou dossier de ce type|No existe el archivo o el directorio|Нет такого файла или каталога)", re.I),
)


@dataclass
class ErrorInfo:
    category: str = "GENERIC"
    signature: str = "GENERIC"
    detail: str = ""
    confidence: str = "low"
    text: str = ""
    exit_code: int = None
    missing_word: str = None
    path: str = None
    module: str = None
    port: str = None
    inferred: bool = False
    note: str = None

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "signature": self.signature,
            "detail": self.detail,
            "confidence": self.confidence,
            "exit_code": self.exit_code,
            "missing_word": self.missing_word,
            "path": self.path,
            "module": self.module,
            "port": self.port,
            "inferred": self.inferred,
            "note": self.note,
        }


def _extract_missing_word(text):
    for pattern in MISSING_WORD_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def _extract_path(text):
    for pattern in PATH_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def _extract_module(text):
    for pattern in MODULE_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def _extract_port(text, cmd):
    match = re.search(r":(\d{2,5})\b", text or "")
    if match:
        return match.group(1)
    match = re.search(r"\bport\s+(\d{2,5})\b", (text or "") + " " + (cmd or ""), re.I)
    return match.group(1) if match else None


def _qualifier(category, text, cmd):
    low = (text or "").lower()
    if category == "DB":
        for name in ("postgres", "mysql", "mariadb", "redis", "mongo"):
            if name in low:
                return name
        return "connection"
    if category == "SSH":
        if "publickey" in low:
            return "publickey"
        if "host key" in low:
            return "hostkey"
        return "connection"
    if category == "GIT_AUTH":
        return "http"
    if category == "K8S":
        if "forbidden" in low:
            return "forbidden"
        if "crashloop" in low or "containercreating" in low:
            return "pod"
        return "connect"
    if category == "TEST_FAIL":
        for name in ("pytest", "npm", "jest", "maven", "gradle", "go test"):
            if name in low:
                return name.replace(" ", "-")
        return "generic"
    if category == "DEPENDENCY":
        for name in ("npm", "pip", "poetry", "cargo", "yarn"):
            if name in low:
                return name
        return "generic"
    if category == "TLS":
        return "certificate"
    if category == "JAVA":
        return "version" if "unsupportedclassversion" in low else "build"
    if category == "RUST":
        return "compile"
    if category == "GO":
        return "module"
    if category == "COMPOSE":
        return "build" if "build" in low else "runtime"
    if category == "PERM":
        if "docker" in low:
            return "docker"
        if "dpkg" in low or "lock" in low:
            return "dpkg-lock"
        if "publickey" in low:
            return "ssh"
        if (cmd or "").strip().startswith("./") or "cannot execute" in low:
            return "exec"
        return "file"
    if category == "AUTH":
        if "publickey" in low:
            return "ssh-key"
        if "401" in low or "403" in low:
            return "http"
        return "credentials"
    if category == "NET":
        if "name resolution" in low or "resolve host" in low or "name or service" in low:
            return "dns"
        if "refused" in low:
            return "refused"
        if "timed out" in low or "timeout" in low:
            return "timeout"
        return "generic"
    if category == "LOCK":
        return "dpkg" if "dpkg" in low or "apt" in low else "generic"
    if category == "GIT_REJECT":
        return "fetch-first" if "fetch first" in low or "non-fast-forward" in low else "generic"
    if category == "DISK":
        if "inode" in low:
            return "inode"
        if "read-only" in low:
            return "readonly"
        return "space"
    if category == "KILLED":
        return "oom" if "memory" in low or "oom" in low else "signal"
    return None


def _detail_line(text):
    fallback = ""
    chosen = ""
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if not fallback:
            fallback = line
        if re.search(r"error|denied|not found|failed|rejected|refused|cannot|exception|traceback|panic|fatal|conflict|错误|失败|拒绝|找不到|エラー|失敗|Fehler|erreur|error|fallo|Ошибка", line, re.I):
            chosen = line
    return truncate(first_line(chosen or fallback, 200), 170)


def classify_text(text, cmd="", exit_code=None) -> ErrorInfo:
    raw = strip_ansi(text or "")
    info = ErrorInfo(text=raw, exit_code=exit_code, confidence="high")
    for category, pattern in RULES:
        if pattern.search(raw):
            info.category = category
            break
    qualifier = _qualifier(info.category, raw, cmd)
    info.signature = info.category + (":" + qualifier if qualifier else "")
    info.detail = _detail_line(raw)
    info.missing_word = _extract_missing_word(raw)
    info.path = _extract_path(raw)
    info.module = _extract_module(raw)
    info.port = _extract_port(raw, cmd)
    return _refine(info, cmd)


def _refine(info, cmd):
    if info.category == "CMD_NOT_FOUND" and info.missing_word:
        info.signature = "CMD_NOT_FOUND:" + info.missing_word
    elif info.category == "MODULE" and info.module:
        info.signature = "MODULE:" + info.module.split(".")[0]
    elif info.category == "PORT" and info.port:
        info.signature = "PORT:" + info.port
    elif info.category == "PERM" and (cmd or "").strip().startswith("./"):
        info.signature = "PERM:exec"
    return info


def classify_event(event) -> ErrorInfo:
    """优先用 hook 捕获的 stderr；没有的话只能靠退出码推断。"""
    if event is None:
        return None
    if event.stderr:
        return classify_text(event.stderr, cmd=event.cmd, exit_code=event.exit_code)
    if event.exit_code is not None and event.exit_code != 0:
        mapped = EXIT_MAP.get(event.exit_code)
        if mapped:
            signature, detail = mapped
            category = signature.split(":", 1)[0]
            info = ErrorInfo(
                category=category,
                signature=signature,
                detail=detail,
                confidence="medium",
                exit_code=event.exit_code,
            )
            if category == "PERM" and not signature.endswith(":exec"):
                info.signature = "PERM"
            return info
        return ErrorInfo(
            category="GENERIC",
            signature="GENERIC",
            detail="退出码 %d（没有捕获到错误输出）" % event.exit_code,
            confidence="low",
            exit_code=event.exit_code,
        )
    return None


def infer_error(category, detail, signature=None, confidence="low", **kwargs) -> ErrorInfo:
    """给"没有退出码但上下文强烈暗示失败"的事件构造一个推测错误。"""
    info = ErrorInfo(
        category=category,
        signature=signature or category,
        detail=detail,
        confidence=confidence,
        inferred=True,
    )
    for key, value in kwargs.items():
        if hasattr(info, key):
            setattr(info, key, value)
    return info


def normalize_error_text(text) -> str:
    """归一化错误文本：去掉路径、时间、数字、引号内容，便于聚类。"""
    value = strip_ansi(text or "").lower()
    value = re.sub(r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}(?:\.\d+)?", "<ts>", value)
    value = re.sub(r"0x[0-9a-f]+", "<hex>", value)
    value = re.sub(r"/[^\s:'\"]+", "<path>", value)
    value = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", value)
    value = re.sub(r"'[^']*'", "'<x>'", value)
    value = re.sub(r'"[^"]*"', '"<x>"', value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:240]


def signature_label(signature: str) -> str:
    if not signature:
        return "未知"
    if ":" not in signature:
        return signature
    head, tail = signature.split(":", 1)
    return "%s（%s）" % (head, tail)
