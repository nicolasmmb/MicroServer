class _StaticTrie:
    def __init__(self):
        self.root = {"h": None, "c": {}}

    def add(self, prefix: str, handler):
        node = self.root
        for part in self._parts(prefix):
            children = node["c"]
            if part not in children:
                children[part] = {"h": None, "c": {}}
            node = children[part]
        node["h"] = handler

    def match(self, path: str):
        node = self.root
        last_handler = None
        for part in self._parts(path):
            children = node.get("c")
            if part not in children:
                break
            node = children[part]
            if node.get("h"):
                last_handler = node["h"]
        return last_handler

    def _parts(self, path: str) -> list:
        if not path or path == "/":
            return []
        if path[0] == "/":
            path = path[1:]
        if path.endswith("/"):
            path = path[:-1]
        return path.split("/") if path else []


class _RouteTrie:
    def __init__(self):
        self.root = {"h": None, "c": {}, "p": None, "pn": None}

    def add(self, pattern: str, handler):
        node = self.root
        for part in self._parts(pattern):
            if part.startswith("<") and part.endswith(">"):
                param_name = part[1:-1]
                if node.get("p") is None:
                    node["p"] = {"h": None, "c": {}, "p": None, "pn": None}
                node["pn"] = param_name
                node = node["p"]
            else:
                children = node["c"]
                if part not in children:
                    children[part] = {"h": None, "c": {}, "p": None, "pn": None}
                node = children[part]
        node["h"] = handler

    def match(self, path: str):
        node = self.root
        params = {}
        for part in self._parts(path):
            children = node.get("c")
            if part in children:
                node = children[part]
            elif node.get("p") is not None:
                param_name = node.get("pn")
                if param_name is not None:
                    params[param_name] = part
                node = node["p"]
            else:
                return None
        if node.get("h"):
            return node["h"], params
        return None

    def _parts(self, path: str) -> list:
        if not path or path == "/":
            return []
        if path[0] == "/":
            path = path[1:]
        if path.endswith("/"):
            path = path[:-1]
        return path.split("/") if path else []


class RouterInterface:
    """Implementa o padrão Strategy para roteamento."""

    def add(self, method: str, path: str, handler):
        """Registra uma rota dinâmica ou exata."""
        raise NotImplementedError

    def add_static(self, url_path: str, handler):
        """Registra uma rota de arquivos estáticos."""
        raise NotImplementedError

    def match(self, method: str, path: str):
        """Retorna (handler, params) ou (None, None)."""
        raise NotImplementedError


class Router(RouterInterface):
    def __init__(self, not_found_cache_size=50):
        self.route_map = {}
        self.static_routes = []
        self._static_trie = _StaticTrie()
        self._dyn_tries = {}

        # Proteção OOM: Cache limitado
        self._not_found_cache = set()
        self._cache_size = not_found_cache_size

    def add(self, method: str, path: str, handler):
        if "<" in path and ">" in path:
            trie = self._dyn_tries.get(method)
            if trie is None:
                trie = _RouteTrie()
                self._dyn_tries[method] = trie
            trie.add(path, handler)
        else:
            self.route_map[(method, path)] = handler

    def add_static(self, url_path: str, handler):
        self.static_routes.append((url_path, handler))
        self._static_trie.add(url_path, handler)

    def match(self, method: str, path: str):
        # 1. Checagem rápida no cache de 404 (Proteção de CPU)
        if path in self._not_found_cache:
            return None, None

        handler, params = self._internal_match(method, path)
        if handler:
            return handler, params

        # Not found - Adiciona ao cache com proteção de Memória
        if len(self._not_found_cache) >= self._cache_size:
            # Estratégia simples: remove um arbitrário
            try:
                self._not_found_cache.pop()
            except KeyError:
                pass

        self._not_found_cache.add(path)
        return None, None

    def _internal_match(self, method: str, path: str):
        # 2. Exact match
        handler = self.route_map.get((method, path))
        params = {}
        if handler:
            return handler, params

        # 3. Static match
        handler = self._static_trie.match(path)
        if handler:
            return handler, params

        # 4. Dynamic match
        trie = self._dyn_tries.get(method)
        if trie is not None:
            matched = trie.match(path)
            if matched is not None:
                return matched

        return None, None
